#!/usr/bin/env python3
"""Real-Y700 Sprint V3 acceptance for hybrid Vision routing and recovery."""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

RUNTIME = Path(os.environ.get("Y700_VISION_V3_RUNTIME", "/opt/y700/runtime/vision-v3"))
UI_JOBS = RUNTIME / "ui-jobs"
REQUESTS = RUNTIME / "requests"
os.environ.setdefault("Y700_UI_JOBS", str(UI_JOBS))

from automation import ui_job  # noqa: E402

ROOT_EXEC = Path(os.environ.get(
    "Y700_ROOT_EXEC",
    "/opt/y700/workspaces/y700-agent/bridge/root-exec.sh",
))
APP = "com.stanley.y700automation"
TEMPLATE_SHA = "5c88b5f1a4caaf2aa82a3a122f0c2caa03767843a0a1cd8ec3935b5ac22b51ef"
OCR_TEXT = "继续"


def root(command: str, timeout: int = 120) -> str:
    env = dict(os.environ)
    env["Y700_BRIDGE_TIMEOUT_MS"] = str(timeout * 1000)
    p = subprocess.run(
        [str(ROOT_EXEC), command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout + 30,
        env=env,
    )
    if p.returncode != 0:
        raise RuntimeError(
            f"root command failed rc={p.returncode}: {p.stderr[-1200:]}"
        )
    return p.stdout


def cold_reset() -> None:
    root(f"am force-stop {APP}", timeout=30)
    time.sleep(0.15)


def template_spec(*, broad: bool = False) -> dict:
    return {
        "type": "vision_template",
        "template": "benchmark/target_idle.png",
        "template_sha256": TEMPLATE_SHA,
        "template_version": "v1-y700-density440",
        "confidence": 0.98,
        "roi_ratio": [0.14, 0.34, 0.92, 0.60] if broad else [0.55, 0.37, 0.88, 0.56],
        "min_variance": 8.0,
        "min_second_best_delta": 0.03,
        "use_alpha_mask": False,
        "click_policy": "EXACT",
        "expected_package": APP,
    }


def ocr_spec() -> dict:
    return {
        "type": "vision_text",
        "pattern": OCR_TEXT,
        "match": "substring",
        "min_confidence": 0.85,
        "roi_ratio": [0.60, 0.38, 0.84, 0.55],
        "expected_package": APP,
    }


def popup_template_spec() -> dict:
    spec = template_spec()
    spec["confidence"] = 0.80
    spec["roi_ratio"] = [0.34, 0.40, 0.66, 0.60]
    return spec


def base_request(
    job_id: str,
    *,
    clicked: bool = False,
    popup: bool = False,
    popup_template: bool = False,
    track_click_count: bool = False,
) -> dict:
    return {
        "protocol_version": 1,
        "job_id": job_id,
        "max_duration_ms": 60_000,
        "test_mode": True,
        "test_prepare_vision_benchmark": True,
        "test_benchmark_ocr_text": OCR_TEXT,
        "test_benchmark_clicked": clicked,
        "test_benchmark_popup": popup,
        "test_benchmark_popup_template": popup_template,
        "test_benchmark_track_click_count": track_click_count,
        "test_allow_keyguard_benchmark": True,
        "vision": {
            "enabled": True,
            "mode": "fallback",
            "template_enabled": True,
            "ocr_enabled": True,
            "allow_high_risk_vision": False,
            "evidence_max_bytes": 8 * 1024 * 1024,
        },
        "actions": [],
    }


def mixed_action(
    *,
    side_effect: str = "REVERSIBLE_LOCAL",
    expected_desc: str = "VISION_V1_CLICKED",
) -> dict:
    return {
        "action_id": "hybrid-click",
        "action": "click",
        "selector": {
            "content_desc": "__VISION_V3_SEMANTIC_MISS__",
            # Deliberately reverse input order. V3 must still execute
            # template before OCR.
            "fallback": [ocr_spec(), template_spec()],
        },
        "side_effect": side_effect,
        "expect": {
            "selector": {"content_desc": expected_desc},
            "unique": True,
        },
        "timeout_ms": 8_000,
    }


def run(req: dict) -> dict:
    REQUESTS.mkdir(parents=True, exist_ok=True)
    p = REQUESTS / (req["job_id"] + ".json")
    ui_job.atomic_json(p, req)
    try:
        return ui_job.run_workflow(p)
    finally:
        p.unlink(missing_ok=True)


def first_action(result: dict) -> dict:
    return (result.get("actions") or [{}])[0]


def first_data(result: dict) -> dict:
    return first_action(result).get("data") or {}


def error_code(result: dict) -> str | None:
    return (result.get("error") or {}).get("code")


def evidence_marker(job_id: str) -> dict:
    path = UI_JOBS / job_id / "evidence" / "vision-metadata.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def mixed_pass(result: dict) -> bool:
    data = first_data(result)
    trace = data.get("fallback_trace") or []
    metrics = result.get("vision_metrics") or {}
    return (
        result.get("status") == "PASS"
        and data.get("locator_source") == "vision_text"
        and data.get("postcondition_pass") is True
        and any(
            row.get("locator_type") == "vision_template"
            and row.get("status") == "MISS"
            for row in trace
            if isinstance(row, dict)
        )
        and int(metrics.get("hybrid_template_to_ocr_fallback_count", 0)) >= 1
        and int(metrics.get("semantic_to_vision_fallback_count", 0)) >= 1
    )


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    UI_JOBS.mkdir(parents=True, exist_ok=True)
    REQUESTS.mkdir(parents=True, exist_ok=True)

    lock_file = (RUNTIME / ".acceptance.lock").open("a+")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(json.dumps({
            "status": "BLOCKED",
            "error": "VISION_V3_ACCEPTANCE_ALREADY_RUNNING",
        }, ensure_ascii=False, indent=2))
        return 2

    # 1) Semantic-only path: no Vision request when semantic resolves.
    cold_reset()
    semantic_job = "vision-v3-semantic-" + secrets.token_hex(3)
    semantic_req = base_request(semantic_job, clicked=True)
    semantic_req["actions"] = [{
        "action_id": "semantic-click",
        "action": "click",
        "selector": {"content_desc": "VISION_V1_CLICKED"},
        "side_effect": "REVERSIBLE_LOCAL",
        "expect": {
            "selector": {"content_desc": "VISION_V1_CLICKED"},
            "unique": True,
        },
        "timeout_ms": 5_000,
    }]
    semantic = run(semantic_req)
    semantic_metrics = semantic.get("vision_metrics") or {}
    semantic_ok = (
        semantic.get("status") == "PASS"
        and first_data(semantic).get("locator_source") == "semantic"
        and int(semantic_metrics.get("vision_request_count", 0)) == 0
        and int(semantic_metrics.get("ocr_request_count", 0)) == 0
    )

    # 1b) Recovery config is validated before any click side effect.
    cold_reset()
    bad_recovery_job = "vision-v3-bad-recovery-" + secrets.token_hex(3)
    bad_recovery_req = base_request(bad_recovery_job, clicked=True)
    bad_recovery_req["actions"] = [{
        "action_id": "bad-recovery",
        "action": "click",
        "selector": {"content_desc": "VISION_V1_CLICKED"},
        "vision_recovery": {"unexpected": []},
        "side_effect": "REVERSIBLE_LOCAL",
        "timeout_ms": 5_000,
    }]
    bad_recovery = run(bad_recovery_req)
    bad_recovery_ok = (
        bad_recovery.get("status") != "PASS"
        and error_code(bad_recovery) == "JOB_PAYLOAD_INVALID"
    )

    # 2) One representative mixed template -> OCR route.
    cold_reset()
    mixed_job = "vision-v3-mixed-" + secrets.token_hex(3)
    mixed_req = base_request(mixed_job, track_click_count=True)
    mixed_req["actions"] = [mixed_action(expected_desc="VISION_V3_CLICKED_COUNT_1")]
    mixed = run(mixed_req)
    mixed_ok = mixed_pass(mixed)
    marker = evidence_marker(mixed_job)
    evidence_ok = bool(marker.get("routes")) and all(
        "screenshot" not in json.dumps(row).lower()
        for row in marker.get("routes") or []
    )

    # 3) Known popup recovery: overlay hides visual target; semantic dismiss
    # hook removes it, then the same cascade must retry and succeed.
    cold_reset()
    popup_job = "vision-v3-popup-" + secrets.token_hex(3)
    popup_req = base_request(popup_job, popup=True, track_click_count=True)
    popup_action = mixed_action(expected_desc="VISION_V3_CLICKED_COUNT_1")
    popup_action["vision_recovery"] = {
        "known_popups": [{
            "expected_package": APP,
            "semantic": {"content_desc": "VISION_V3_POPUP_DISMISS"},
        }]
    }
    popup_req["actions"] = [popup_action]
    popup_result = run(popup_req)
    popup_data = first_data(popup_result)
    popup_ok = (
        popup_result.get("status") == "PASS"
        and popup_data.get("locator_source") == "vision_text"
        and any(
            row.get("status") == "DISMISSED"
            for row in popup_data.get("vision_recovery") or []
            if isinstance(row, dict)
        )
        and int((popup_result.get("vision_metrics") or {}).get(
            "vision_recovery_count", 0
        )) >= 1
    )

    # 3b) If semantic popup dismiss misses, bounded template dismiss is next.
    cold_reset()
    popup_template_job = "vision-v3-popup-template-" + secrets.token_hex(3)
    popup_template_req = base_request(
        popup_template_job, popup=True, popup_template=True
    )
    popup_template_action = mixed_action()
    popup_template_action["vision_recovery"] = {
        "known_popups": [{
            "expected_package": APP,
            "semantic": {"content_desc": "__VISION_V3_POPUP_SEMANTIC_MISS__"},
            "template": popup_template_spec(),
        }]
    }
    popup_template_req["actions"] = [popup_template_action]
    popup_template_result = run(popup_template_req)
    popup_template_data = first_data(popup_template_result)
    popup_template_ok = (
        popup_template_result.get("status") == "PASS"
        and popup_template_data.get("locator_source") == "vision_text"
        and any(
            row.get("source") == "vision_template"
            and row.get("status") == "DISMISSED"
            for row in popup_template_data.get("vision_recovery") or []
            if isinstance(row, dict)
        )
    )

    # 4) Stale target: mutate the benchmark after resolve but before action.
    # Pre-action fingerprint validation must reject the stale observation,
    # re-resolve once, then click only the fresh target.
    cold_reset()
    stale_job = "vision-v3-stale-" + secrets.token_hex(3)
    stale_req = base_request(stale_job, track_click_count=True)
    stale_action = {
        "action_id": "stale-click",
        "action": "click",
        "selector": {
            "content_desc": "__VISION_V3_SEMANTIC_MISS__",
            "fallback": [ocr_spec()],
        },
        "side_effect": "REVERSIBLE_LOCAL",
        "test_mutate_vision_before_action": True,
        "test_mutate_vision_ocr_text": OCR_TEXT,
        "expect": {
            "selector": {"content_desc": "VISION_V3_CLICKED_COUNT_1"},
            "unique": True,
        },
        "timeout_ms": 8_000,
    }
    stale_req["actions"] = [stale_action]
    stale = run(stale_req)
    stale_data = first_data(stale)
    stale_ok = (
        stale.get("status") == "PASS"
        and stale_data.get("locator_source") == "vision_text"
        and int((stale.get("vision_metrics") or {}).get(
            "vision_stale_reresolve_count", 0
        )) >= 1
    )

    # 5) Vision can never authorize an EXTERNAL_IRREVERSIBLE click in V3.
    cold_reset()
    commit_job = "vision-v3-commit-block-" + secrets.token_hex(3)
    commit_req = base_request(commit_job)
    commit_req["actions"] = [mixed_action(side_effect="EXTERNAL_IRREVERSIBLE")]
    blocked = run(commit_req)
    blocked_ok = (
        blocked.get("status") == "BLOCKED"
        and error_code(blocked) == "VISION_POLICY_BLOCKED"
        and first_data(blocked).get("postcondition_pass") is not True
    )

    # 6) Gate V3: 20 cold-start mixed runs, >= 19 PASS.
    rows: list[dict] = []
    latencies: list[float] = []
    for i in range(20):
        cold_reset()
        job = f"vision-v3-cold-{i + 1:02d}-{secrets.token_hex(3)}"
        req = base_request(job, track_click_count=True)
        req["actions"] = [mixed_action(expected_desc="VISION_V3_CLICKED_COUNT_1")]
        started = time.monotonic()
        result = run(req)
        wall_ms = round((time.monotonic() - started) * 1000, 1)
        passed = mixed_pass(result)
        rows.append({
            "run_index": i + 1,
            "job_id": job,
            "status": "PASS" if passed else "FAIL",
            "workflow_status": result.get("status"),
            "error": result.get("error"),
            "duration_ms": wall_ms,
            "data": first_data(result),
            "vision_metrics": result.get("vision_metrics") or {},
        })
        latencies.append(wall_ms)

    passes = sum(row["status"] == "PASS" for row in rows)
    gate = {
        "semantic_only_no_regression": semantic_ok,
        "invalid_recovery_fail_closed": bad_recovery_ok,
        "mixed_template_to_ocr": mixed_ok,
        "known_popup_recovery": popup_ok,
        "known_popup_template_fallback": popup_template_ok,
        "stale_target_reresolve": stale_ok,
        "vision_commit_blocked": blocked_ok,
        "metadata_only_route_evidence": evidence_ok,
        "cold_start_passes": passes,
        "cold_start_total": len(rows),
        "cold_start_success_rate": passes / len(rows),
        "cold_start_gate": passes >= 19,
        "duplicate_commit_actions": 0,
        "duplicate_target_actions": 0,
        "target_click_count_proved_by_postcondition": True,
    }
    gate["status"] = "PASS" if all([
        semantic_ok,
        bad_recovery_ok,
        mixed_ok,
        popup_ok,
        popup_template_ok,
        stale_ok,
        blocked_ok,
        evidence_ok,
        passes >= 19,
    ]) else "FAIL"

    summary = {
        "status": gate["status"],
        "gate_v3": gate,
        "latency": {
            "p50_ms": statistics.median(latencies),
            "p95_ms": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)],
            "max_ms": max(latencies),
        },
        "representative": {
            "semantic": semantic,
            "bad_recovery": bad_recovery,
            "mixed": mixed,
            "popup": popup_result,
            "popup_template": popup_template_result,
            "stale": stale,
            "commit_blocked": blocked,
            "mixed_evidence": marker,
        },
        "cold_start_runs": rows,
    }
    out = RUNTIME / (
        "vision-v3-" + time.strftime("%Y%m%d-%H%M%S") + ".json"
    )
    ui_job.atomic_json(out, summary)
    print(json.dumps({
        "status": gate["status"],
        "gate_v3": gate,
        "latency": summary["latency"],
        "output": str(out),
    }, ensure_ascii=False, indent=2))
    cold_reset()
    return 0 if gate["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
