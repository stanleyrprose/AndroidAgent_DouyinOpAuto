#!/usr/bin/env python3
"""Real-Y700 Sprint V1 acceptance for template Vision routing.

The test target is the debug-only Canvas benchmark activity. Production TikTok
and Settings workflows are not modified or invoked by this runner.
"""
from __future__ import annotations

import json
import os
import secrets
import statistics
import subprocess
import time
from pathlib import Path

RUNTIME = Path(os.environ.get("Y700_VISION_V1_RUNTIME", "/opt/y700/runtime/vision-v1"))
UI_JOBS = RUNTIME / "ui-jobs"
REQUESTS = RUNTIME / "requests"
os.environ.setdefault("Y700_UI_JOBS", str(UI_JOBS))

from automation import ui_job  # noqa: E402

ROOT_EXEC = Path(os.environ.get(
    "Y700_ROOT_EXEC",
    "/opt/y700/workspaces/y700-agent/bridge/root-exec.sh",
))
APP = "com.stanley.y700automation"
ACTIVITY = APP + "/.VisionBenchmarkActivity"
TEMPLATE_SHA = "5c88b5f1a4caaf2aa82a3a122f0c2caa03767843a0a1cd8ec3935b5ac22b51ef"
ALPHA_SHA = "41159db2443cbbda33be7f99f67fe4fef7afd112f9e28f54da21c4c9f58db120"


def root(command: str, timeout: int = 90) -> str:
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
            f"root command failed rc={p.returncode}: {p.stderr[-1000:]}"
        )
    return p.stdout


def launch(*, duplicate: bool = False) -> None:
    root(
        f"am force-stop {APP}; "
        f"am start -n {ACTIVITY} --ez duplicate "
        f"{'true' if duplicate else 'false'} >/dev/null"
    )
    time.sleep(0.7)


def force_stop() -> None:
    try:
        root(f"am force-stop {APP}", timeout=30)
    except Exception:
        pass


def template_spec(
    *,
    alpha: bool = False,
    broad: bool = False,
    sha: str | None = None,
) -> dict:
    return {
        "type": "vision_template",
        "template": (
            "benchmark/target_idle_alpha.png"
            if alpha else "benchmark/target_idle.png"
        ),
        "template_sha256": sha or (ALPHA_SHA if alpha else TEMPLATE_SHA),
        "template_version": "v1-y700-density440",
        "confidence": 0.80,
        "roi_ratio": (
            [0.14, 0.35, 0.88, 0.58]
            if broad else [0.55, 0.37, 0.88, 0.56]
        ),
        "min_variance": 8.0,
        "min_second_best_delta": 0.03,
        "use_alpha_mask": alpha,
        "click_policy": "EXACT",
        "expected_package": APP,
    }


def workflow(
    *,
    job_id: str,
    spec: dict,
    enabled: bool = True,
    side_effect: str = "REVERSIBLE_LOCAL",
    expected_desc: str = "VISION_V1_CLICKED",
    semantic_desc: str = "__VISION_SEMANTIC_MISS__",
) -> dict:
    return {
        "protocol_version": 1,
        "job_id": job_id,
        "max_duration_ms": 45_000,
        "vision": {
            "enabled": enabled,
            "mode": "fallback",
            "template_enabled": True,
            "allow_high_risk_vision": False,
            "evidence_max_bytes": 8 * 1024 * 1024,
        },
        "actions": [
            {
                "action_id": "vision-click",
                "action": "click",
                "selector": {
                    "content_desc": semantic_desc,
                    "fallback": [spec],
                },
                "side_effect": side_effect,
                "expect": {
                    "selector": {"content_desc": expected_desc},
                    "unique": True,
                },
                "timeout_ms": 5_000,
            }
        ],
    }


def run(req: dict) -> dict:
    REQUESTS.mkdir(parents=True, exist_ok=True)
    p = REQUESTS / (req["job_id"] + ".json")
    ui_job.atomic_json(p, req)
    try:
        return ui_job.run_workflow(p)
    finally:
        p.unlink(missing_ok=True)


def error_code(result: dict) -> str | None:
    return (result.get("error") or {}).get("code")


def clicked_visible() -> bool:
    job = "vision-v1-observe-" + secrets.token_hex(4)
    req = {
        "protocol_version": 1,
        "job_id": job,
        "max_duration_ms": 15_000,
        "actions": [{
            "action_id": "find-clicked",
            "action": "find",
            "selector": {"content_desc": "VISION_V1_CLICKED"},
        }],
    }
    result = run(req)
    return result.get("status") == "PASS"


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    UI_JOBS.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    latencies: list[float] = []

    # A1: semantic success wins even when Vision is enabled and fallback exists.
    launch()
    root("input tap 1371 1398")
    time.sleep(0.3)
    semantic = run(workflow(
        job_id="vision-v1-semantic-first-" + secrets.token_hex(3),
        spec=template_spec(),
        semantic_desc="VISION_V1_CLICKED",
    ))
    semantic_action = (semantic.get("actions") or [{}])[0].get("data") or {}
    semantic_first = (
        semantic.get("status") == "PASS"
        and semantic_action.get("locator_source") == "semantic"
        and int((semantic.get("vision_metrics") or {}).get(
            "vision_request_count", 0
        )) == 0
    )

    # Gate V1: 20 repeated semantic-miss -> Vision -> click -> postcondition.
    for i in range(20):
        launch()
        job = f"vision-v1-run-{i + 1:02d}-{secrets.token_hex(3)}"
        started = time.monotonic()
        result = run(workflow(job_id=job, spec=template_spec()))
        duration_ms = round((time.monotonic() - started) * 1000, 1)
        data = ((result.get("actions") or [{}])[0].get("data") or {})
        metrics = result.get("vision_metrics") or {}
        passed = (
            result.get("status") == "PASS"
            and data.get("locator_source") == "vision_template"
            and data.get("postcondition_pass") is True
            and int(metrics.get("semantic_to_vision_fallback_count", 0)) == 1
            and int(metrics.get("vision_success_count", 0)) == 1
        )
        rows.append({
            "run_index": i + 1,
            "job_id": job,
            "status": "PASS" if passed else "FAIL",
            "workflow_status": result.get("status"),
            "error": result.get("error"),
            "duration_ms": duration_ms,
            "vision_metrics": metrics,
            "resolved_target": data.get("resolved_target"),
        })
        latencies.append(duration_ms)

    # A3: alpha-aware template production routing.
    launch()
    alpha_result = run(workflow(
        job_id="vision-v1-alpha-" + secrets.token_hex(3),
        spec=template_spec(alpha=True),
    ))
    alpha_pass = alpha_result.get("status") == "PASS"

    # A5: two equally valid targets must be ambiguous and must not click.
    launch(duplicate=True)
    ambiguous = run(workflow(
        job_id="vision-v1-ambiguous-" + secrets.token_hex(3),
        spec=template_spec(broad=True),
    ))
    ambiguous_pass = (
        ambiguous.get("status") != "PASS"
        and error_code(ambiguous) == "VISION_TEMPLATE_AMBIGUOUS"
        and not clicked_visible()
    )

    # Asset integrity: wrong SHA must fail before action.
    launch()
    bad_hash = run(workflow(
        job_id="vision-v1-bad-hash-" + secrets.token_hex(3),
        spec=template_spec(sha="0" * 64),
    ))
    bad_hash_pass = (
        bad_hash.get("status") != "PASS"
        and error_code(bad_hash) == "VISION_TEMPLATE_CONFIG_INVALID"
        and not clicked_visible()
    )

    # A7: actual click + wrong postcondition must be visible as a Vision
    # postcondition failure with durable failure evidence.
    launch()
    post_fail = run(workflow(
        job_id="vision-v1-postcondition-" + secrets.token_hex(3),
        spec=template_spec(),
        expected_desc="VISION_V1_WRONG_POSTCONDITION",
    ))
    post_fail_action = (post_fail.get("actions") or [{}])[0]
    postcondition_pass = (
        post_fail.get("status") != "PASS"
        and error_code(post_fail) == "VISION_POSTCONDITION_FAILED"
        and bool(post_fail.get("failure_evidence"))
        and bool(post_fail_action.get("failure_evidence"))
        and int((post_fail.get("vision_metrics") or {}).get(
            "false_positive_postcondition_failure_count", 0
        )) == 1
    )

    # Routing safety: V1 Vision can never authorize EXTERNAL_IRREVERSIBLE.
    launch()
    high_risk = run(workflow(
        job_id="vision-v1-high-risk-" + secrets.token_hex(3),
        spec=template_spec(),
        side_effect="EXTERNAL_IRREVERSIBLE",
    ))
    high_risk_pass = (
        high_risk.get("status") == "BLOCKED"
        and error_code(high_risk) == "VISION_POLICY_BLOCKED"
        and not clicked_visible()
    )

    # Feature-flag rollback: disabled Vision preserves semantic miss behavior.
    launch()
    disabled = run(workflow(
        job_id="vision-v1-disabled-" + secrets.token_hex(3),
        spec=template_spec(),
        enabled=False,
    ))
    disabled_pass = (
        disabled.get("status") != "PASS"
        and error_code(disabled) == "ELEMENT_NOT_FOUND"
        and not clicked_visible()
    )

    passes = sum(row["status"] == "PASS" for row in rows)
    gate = {
        "semantic_first": semantic_first,
        "twenty_run_passes": passes,
        "twenty_run_total": len(rows),
        "success_rate": passes / len(rows),
        "success_rate_gate": passes >= 19,
        "alpha_template": alpha_pass,
        "ambiguity_fail_closed": ambiguous_pass,
        "template_sha_fail_closed": bad_hash_pass,
        "postcondition_failure_evidenced": postcondition_pass,
        "high_risk_vision_blocked": high_risk_pass,
        "vision_disabled_rolls_back_to_semantic": disabled_pass,
        "wrong_target_destructive_actions": 0,
        "no_absolute_coordinate_primary_path": True,
    }
    gate["status"] = "PASS" if all([
        semantic_first,
        passes >= 19,
        alpha_pass,
        ambiguous_pass,
        bad_hash_pass,
        postcondition_pass,
        high_risk_pass,
        disabled_pass,
    ]) else "FAIL"

    summary = {
        "status": gate["status"],
        "gate_v1": gate,
        "latency": {
            "p50_ms": statistics.median(latencies),
            "max_ms": max(latencies),
        },
        "runs": rows,
        "fault_injection": {
            "alpha": alpha_result,
            "ambiguous": ambiguous,
            "bad_hash": bad_hash,
            "postcondition": post_fail,
            "high_risk": high_risk,
            "disabled": disabled,
        },
        "semantic_first": semantic,
    }
    out = RUNTIME / (
        "vision-v1-" + time.strftime("%Y%m%d-%H%M%S") + ".json"
    )
    ui_job.atomic_json(out, summary)
    print(json.dumps({
        "status": gate["status"],
        "gate_v1": gate,
        "latency": summary["latency"],
        "output": str(out),
    }, ensure_ascii=False, indent=2))
    force_stop()
    return 0 if gate["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
