#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import shutil
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bridge import bridge_client as bridge_v2

os.umask(0o077)

ROOT = Path("/opt/y700")
UI_JOBS = Path(os.environ.get("Y700_UI_JOBS", str(ROOT / "ui-jobs")))
BRIDGE_JOBS = Path(os.environ.get("Y700_BRIDGE_JOBS", str(ROOT / "jobs")))
BRIDGE_RUNTIME = Path(os.environ.get("Y700_RUNTIME", str(ROOT / "runtime")))
BRIDGE_PATHS = bridge_v2.BridgePaths(jobs=BRIDGE_JOBS, runtime=BRIDGE_RUNTIME)
CANCEL_SIGNALS = Path(os.environ.get("Y700_UI_CANCEL_SIGNALS", str(ROOT / "ui-cancel-signals")))
DRIVER_COMPONENT = "com.stanley.y700automation.test/androidx.test.runner.AndroidJUnitRunner"
DRIVER_CLASS = "com.stanley.y700automation.AutomationInstrumentedTest#runWorkflow"
JOB_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
SAFE_ACTIONS = {"health", "observe", "screenshot", "find", "findAll", "assert", "waitFor", "waitStable", "pressBack", "pressHome"}
RESULT_RE = re.compile(r"y700_result_b64=([^\r\n ]+)")
HEARTBEAT_RE = re.compile(r"y700_heartbeat_b64=([^\r\n ]+)")


class UiJobError(RuntimeError):
    pass


def now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat()


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        os.fchmod(f.fileno(), mode)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    fsync_dir(path.parent)


def atomic_json(path: Path, obj: Any) -> None:
    atomic_write(path, (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode())


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def append_journal(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path, "a", encoding="utf-8") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def ensure_cancel_signal_dir() -> None:
    CANCEL_SIGNALS.mkdir(parents=True, exist_ok=True, mode=0o710)
    os.chown(CANCEL_SIGNALS, 0, 2000)
    os.chmod(CANCEL_SIGNALS, 0o710)


def cancel_signal_path(job_id: str) -> Path:
    return CANCEL_SIGNALS / job_id


def publish_cancel_signal(job_id: str) -> None:
    ensure_cancel_signal_dir()
    atomic_write(cancel_signal_path(job_id), b"", mode=0o600)


def validate_request(req: dict[str, Any]) -> None:
    if req.get("protocol_version") != 1:
        raise UiJobError("PROTOCOL_MISMATCH")
    job = str(req.get("job_id", ""))
    if not JOB_RE.fullmatch(job):
        raise UiJobError("JOB_PAYLOAD_INVALID: invalid job_id")
    actions = req.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 50:
        raise UiJobError("JOB_PAYLOAD_INVALID: actions must contain 1..50 items")
    max_duration = int(req.get("max_duration_ms", 600000))
    if not 1000 <= max_duration <= 600000:
        raise UiJobError("JOB_PAYLOAD_INVALID: max_duration_ms out of range")

    vision = req.get("vision")
    if vision is not None:
        if not isinstance(vision, dict):
            raise UiJobError("JOB_PAYLOAD_INVALID: vision must be an object")
        allowed = {
            "enabled", "mode", "template_enabled", "ocr_enabled",
            "allow_high_risk_vision", "evidence_max_bytes",
        }
        unknown = sorted(set(vision) - allowed)
        if unknown:
            raise UiJobError(
                "JOB_PAYLOAD_INVALID: unsupported vision keys=" + ",".join(unknown)
            )
        if "enabled" in vision and not isinstance(vision["enabled"], bool):
            raise UiJobError("JOB_PAYLOAD_INVALID: vision.enabled must be boolean")
        if "template_enabled" in vision and not isinstance(
            vision["template_enabled"], bool
        ):
            raise UiJobError(
                "JOB_PAYLOAD_INVALID: vision.template_enabled must be boolean"
            )
        if "ocr_enabled" in vision and not isinstance(
            vision["ocr_enabled"], bool
        ):
            raise UiJobError(
                "JOB_PAYLOAD_INVALID: vision.ocr_enabled must be boolean"
            )
        if "allow_high_risk_vision" in vision and not isinstance(
            vision["allow_high_risk_vision"], bool
        ):
            raise UiJobError(
                "JOB_PAYLOAD_INVALID: vision.allow_high_risk_vision must be boolean"
            )
        mode = str(vision.get("mode", "fallback"))
        if mode not in {"off", "benchmark_only", "fallback"}:
            raise UiJobError("JOB_PAYLOAD_INVALID: unsupported vision.mode")
        quota = int(vision.get("evidence_max_bytes", 64 * 1024 * 1024))
        if not 8 * 1024 * 1024 <= quota <= 512 * 1024 * 1024:
            raise UiJobError(
                "JOB_PAYLOAD_INVALID: vision.evidence_max_bytes out of range"
            )


def bridge_submit(command: str, bridge_id: str, timeout_sec: int) -> str:
    try:
        return bridge_v2.submit_root(
            command,
            timeout_ms=max(1000, min(3_600_000, timeout_sec * 1000)),
            job_id=bridge_id,
            paths=BRIDGE_PATHS,
        )
    except bridge_v2.BridgeError as exc:
        raise UiJobError(f"BRIDGE_SUBMIT_FAILED: {exc}") from exc


def decode_markers(text: str, regex: re.Pattern[str]) -> list[dict[str, Any]]:
    rows = []
    for marker in regex.findall(text):
        try:
            rows.append(json.loads(base64.b64decode(marker)))
        except Exception:
            continue
    return rows


def _settle_terminal_bridge_location(
    bridge_id: str,
    snapshot: dict[str, Any],
    bridge: Path,
) -> tuple[dict[str, Any], Path]:
    """Resolve a v2 terminal job from active/ to its immutable archive path.

    host-executor writes result.json before atomically moving the job directory
    into archive/. A status poll can therefore observe a terminal result while
    still returning the soon-to-disappear active/ path. Reading stdout from that
    stale path loses the driver's final structured result marker.
    """
    if snapshot.get("protocol_version") != 2:
        return snapshot, bridge
    for _ in range(20):
        if bridge.parent != BRIDGE_PATHS.active:
            break
        time.sleep(0.05)
        try:
            fresh = bridge_v2.status(bridge_id, paths=BRIDGE_PATHS)
        except bridge_v2.BridgeError:
            continue
        snapshot = fresh
        bridge = Path(fresh["location"])
    return snapshot, bridge


def run_bridge_command(command: str, ui_dir: Path, timeout_sec: int = 660) -> tuple[int, str, str, list[dict[str, Any]]]:
    bridge_id = "uihost-" + ui_dir.name[:64] + "-" + secrets.token_hex(4)
    bridge_submit(command, bridge_id, timeout_sec)
    atomic_json(ui_dir / "bridge.json", {"bridge_job_id": bridge_id, "protocol_version": 2})
    deadline = time.monotonic() + timeout_sec
    seen_heartbeats = 0
    heartbeats: list[dict[str, Any]] = []
    snapshot: dict[str, Any] | None = None
    bridge = BRIDGE_JOBS / "active" / bridge_id

    while True:
        if time.monotonic() >= deadline:
            raise UiJobError("WORKFLOW_TIMEOUT: host bridge did not finish")
        try:
            snapshot = bridge_v2.status(bridge_id, paths=BRIDGE_PATHS)
        except bridge_v2.BridgeError as exc:
            raise UiJobError(f"BRIDGE_STATUS_FAILED: {exc}") from exc
        bridge = Path(snapshot["location"])
        stdout = (bridge / "stdout.log").read_text(encoding="utf-8", errors="replace") if (bridge / "stdout.log").exists() else ""
        current = decode_markers(stdout, HEARTBEAT_RE)
        if len(current) > seen_heartbeats:
            for hb in current[seen_heartbeats:]:
                heartbeats.append(hb)
                atomic_json(ui_dir / "heartbeat.json", {**hb, "updated_at": now_iso()})
                append_journal(ui_dir / "journal.jsonl", {"timestamp": now_iso(), "phase": "HEARTBEAT", **hb})
            seen_heartbeats = len(current)
        if bridge_v2.terminal_status(snapshot):
            break
        time.sleep(0.20)

    snapshot, bridge = _settle_terminal_bridge_location(
        bridge_id, snapshot or {}, bridge
    )

    # The host executor may atomically publish terminal state a few milliseconds
    # before the child's final stdout/stderr buffers are fully visible in the
    # archived job directory. Large structured result markers are especially
    # susceptible. Give terminal logs a bounded drain window before parsing.
    previous_sizes: tuple[int, int] | None = None
    stable_polls = 0
    for _ in range(10):
        out_path = bridge / "stdout.log"
        err_path = bridge / "stderr.log"
        sizes = (
            out_path.stat().st_size if out_path.exists() else 0,
            err_path.stat().st_size if err_path.exists() else 0,
        )
        if sizes == previous_sizes:
            stable_polls += 1
            if stable_polls >= 2:
                break
        else:
            previous_sizes = sizes
            stable_polls = 0
        time.sleep(0.05)

    bridge_result = (snapshot or {}).get("result") or {}
    rc = int(bridge_result.get("exit_code", 1))
    stdout = (bridge / "stdout.log").read_text(encoding="utf-8", errors="replace") if (bridge / "stdout.log").exists() else ""
    stderr = (bridge / "stderr.log").read_text(encoding="utf-8", errors="replace") if (bridge / "stderr.log").exists() else ""

    current = decode_markers(stdout, HEARTBEAT_RE)
    for hb in current[seen_heartbeats:]:
        heartbeats.append(hb)
        atomic_json(ui_dir / "heartbeat.json", {**hb, "updated_at": now_iso()})
        append_journal(ui_dir / "journal.jsonl", {"timestamp": now_iso(), "phase": "HEARTBEAT", **hb})
    return rc, stdout, stderr, heartbeats


def copy_screenshot(path: str, ui_dir: Path, name: str) -> str | None:
    if not path.startswith("/data/user/0/com.stanley.y700automation/files/"):
        return None
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    dest_host = f"/data/local/y700-agent/ui-jobs/{ui_dir.name}/evidence/{safe}"
    command = f"cp {path} {dest_host} && chmod 600 {dest_host}"
    try:
        rc, _, _, _ = run_bridge_command(command, ui_dir, timeout_sec=30)
        if rc == 0:
            return f"evidence/{safe}"
    except Exception:
        return None
    return None


def _compact_xml_tree(path: Path, limit: int = 256) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(path).getroot()
    except Exception:
        return None
    rows: list[dict[str, Any]] = []
    for node in root.iter("node"):
        if len(rows) >= limit:
            break
        attrs = node.attrib
        rows.append({
            "resource_id": attrs.get("resource-id") or None,
            "text": attrs.get("text") or None,
            "content_desc": attrs.get("content-desc") or None,
            "class": attrs.get("class") or None,
            "package": attrs.get("package") or None,
            "clickable": attrs.get("clickable") == "true",
            "enabled": attrs.get("enabled") == "true",
            "selected": attrs.get("selected") == "true",
            "checked": attrs.get("checked") == "true",
            "scrollable": attrs.get("scrollable") == "true",
            "bounds": attrs.get("bounds") or None,
        })
    return {
        "source": "legacy_uiautomator_dump_fallback",
        "node_count": len(rows),
        "truncated": len(list(root.iter("node"))) > len(rows),
        "elements": rows,
    }


def _host_failure_fallback(ui_dir: Path) -> dict[str, Any]:
    """Best-effort evidence when the instrumentation cannot provide it."""
    evidence_dir = ui_dir / "evidence"
    host_dir = f"/data/local/y700-agent/ui-jobs/{ui_dir.name}/evidence"
    screen_host = f"{host_dir}/failure-host.png"
    xml_host = f"{host_dir}/failure-host.xml"
    command = (
        f"mkdir -p {host_dir}; chmod 700 {host_dir}; "
        f"screencap -p {screen_host} >/dev/null 2>&1 || true; "
        f"chmod 600 {screen_host} 2>/dev/null || true; "
        f"uiautomator dump {xml_host} >/dev/null 2>&1 || true; "
        f"chmod 600 {xml_host} 2>/dev/null || true; "
        "dumpsys activity activities | grep -m1 -E 'mResumedActivity|topResumedActivity' || true"
    )
    out: dict[str, Any] = {"source": "host_fallback"}
    try:
        _, stdout, stderr, _ = run_bridge_command(command, ui_dir, timeout_sec=30)
        if stdout.strip():
            out["activity"] = stdout.strip().splitlines()[-1][:2048]
        if stderr.strip():
            out["capture_stderr"] = stderr.strip()[-2048:]
    except Exception as exc:
        out["capture_error"] = f"{type(exc).__name__}: {exc}"
    screen = evidence_dir / "failure-host.png"
    if screen.is_file() and screen.stat().st_size > 0:
        out["screenshot"] = "evidence/failure-host.png"
    tree = _compact_xml_tree(evidence_dir / "failure-host.xml")
    if tree is not None:
        atomic_json(evidence_dir / "failure-tree.json", tree)
        out["compact_ui_tree"] = "evidence/failure-tree.json"
    return out


def export_failure_evidence(
    ui_dir: Path,
    req: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any] | None:
    actions = result.get("actions") or []
    failed_index = next(
        (i for i, row in enumerate(actions) if row.get("status") != "PASS"),
        None,
    )
    action_result = actions[failed_index] if failed_index is not None else {}
    driver = dict(action_result.get("failure_evidence") or {})
    action = (
        req.get("actions", [])[failed_index]
        if failed_index is not None and failed_index < len(req.get("actions", []))
        else {}
    )

    tree = driver.pop("compact_ui_tree", None)
    screenshot = driver.pop("screenshot", None)
    screenshot_rel: str | None = None
    if isinstance(screenshot, dict) and screenshot.get("path"):
        screenshot_rel = copy_screenshot(
            str(screenshot["path"]),
            ui_dir,
            Path(str(screenshot["path"])).name,
        )

    tree_rel: str | None = None
    if isinstance(tree, dict):
        atomic_json(ui_dir / "evidence" / "failure-tree.json", tree)
        tree_rel = "evidence/failure-tree.json"

    fallback: dict[str, Any] = {}
    if screenshot_rel is None or tree_rel is None:
        fallback = _host_failure_fallback(ui_dir)
        screenshot_rel = screenshot_rel or fallback.get("screenshot")
        tree_rel = tree_rel or fallback.get("compact_ui_tree")

    err = action_result.get("error") or result.get("error") or {}
    context = {
        "timestamp": now_iso(),
        "timestamp_ms": driver.get("timestamp_ms"),
        "job_id": req.get("job_id"),
        "session_id": req.get("session_id"),
        "action_index": failed_index,
        "action_id": action.get("action_id"),
        "action": action.get("action"),
        "selector": action.get("selector"),
        "precondition": action.get("precondition"),
        "postcondition": action.get("expect"),
        "error": err,
        "package": driver.get("package"),
        "activity": driver.get("activity") or fallback.get("activity"),
        "screenshot": screenshot_rel,
        "compact_ui_tree": tree_rel,
        "observation_error": driver.get("observation_error"),
        "screenshot_error": driver.get("screenshot_error"),
        "fallback": fallback or None,
    }
    atomic_json(ui_dir / "evidence" / "failure-context.json", context)
    ref = {
        "context": "evidence/failure-context.json",
        "screenshot": screenshot_rel,
        "compact_ui_tree": tree_rel,
    }
    if isinstance(action_result, dict) and action_result:
        action_result["failure_evidence"] = ref
    result["failure_evidence"] = ref
    append_journal(ui_dir / "journal.jsonl", {
        "timestamp": now_iso(),
        "phase": "FAILURE_EVIDENCE_CAPTURED",
        "action_index": failed_index,
        **ref,
    })
    return ref


VISION_TERMINAL_STATES = {"PASS", "FAILED", "BLOCKED", "TIMEOUT", "CANCELLED"}


def _tree_bytes(path: Path) -> int:
    total = 0
    if not path.is_dir():
        return 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except FileNotFoundError:
                pass
    return total


def enforce_vision_evidence_quota(
    max_bytes: int,
    *,
    current_ui_dir: Path,
) -> tuple[int, int]:
    """Evict oldest terminal/unpinned Vision evidence, never durable job state."""
    candidates: list[tuple[float, Path, int]] = []
    total = 0
    if not UI_JOBS.is_dir():
        return 0, 0

    for job_dir in UI_JOBS.iterdir():
        if not job_dir.is_dir():
            continue
        evidence = job_dir / "evidence"
        marker = evidence / "vision-metadata.json"
        if not marker.is_file():
            continue
        size = _tree_bytes(evidence)
        total += size
        if job_dir == current_ui_dir:
            continue
        if (job_dir / ".pinned").exists() or (evidence / ".pinned").exists():
            continue
        state = read_json(job_dir / "state.json", {}) or {}
        status = state.get("status")
        if status not in VISION_TERMINAL_STATES:
            continue
        try:
            age = marker.stat().st_mtime
        except FileNotFoundError:
            continue
        candidates.append((age, job_dir, size))

    evicted = 0
    for _, job_dir, size in sorted(candidates, key=lambda row: row[0]):
        if total <= max_bytes:
            break
        evidence = job_dir / "evidence"
        if not evidence.is_dir():
            continue
        shutil.rmtree(evidence)
        atomic_json(job_dir / "vision-evidence-evicted.json", {
            "evicted_at": now_iso(),
            "bytes_reclaimed": size,
            "reason": "vision_evidence_quota",
        })
        total = max(0, total - size)
        evicted += 1
    return evicted, total


def finalize_vision_evidence(
    ui_dir: Path,
    req: dict[str, Any],
    result: dict[str, Any],
) -> None:
    vision = req.get("vision")
    if not isinstance(vision, dict):
        return
    quota = int(vision.get("evidence_max_bytes", 64 * 1024 * 1024))
    marker = {
        "timestamp": now_iso(),
        "job_id": req.get("job_id"),
        "session_id": req.get("session_id"),
        "status": result.get("status"),
        "policy": result.get("vision_policy") or vision,
        "metrics": result.get("vision_metrics") or {},
    }
    atomic_json(ui_dir / "evidence" / "vision-metadata.json", marker)
    evicted, retained = enforce_vision_evidence_quota(
        quota, current_ui_dir=ui_dir
    )
    metrics = result.setdefault("vision_metrics", {})
    metrics["vision_evidence_eviction_count"] = (
        int(metrics.get("vision_evidence_eviction_count", 0)) + evicted
    )
    result["vision_evidence"] = {
        "metadata": "evidence/vision-metadata.json",
        "quota_bytes": quota,
        "retained_bytes_observed": retained,
        "evicted_job_count": evicted,
    }


def write_checkpoint(ui_dir: Path, req: dict[str, Any], completed_index: int, safe: bool) -> None:
    actions = req["actions"]
    last = actions[completed_index] if completed_index >= 0 else None
    next_index = completed_index + 1
    atomic_json(ui_dir / "checkpoint.json", {
        "job_id": req["job_id"],
        "session_id": req.get("session_id"),
        "checkpoint_id": f"cp-{max(0, completed_index):04d}",
        "last_completed_action_id": (last or {}).get("action_id") if last else None,
        "last_completed_action_index": completed_index,
        "next_action_index": next_index if next_index < len(actions) else None,
        "safe_to_resume": safe,
        "updated_at": now_iso(),
    })


def run_workflow(path: Path) -> dict[str, Any]:
    req = read_json(path)
    if not isinstance(req, dict):
        raise UiJobError("JOB_PAYLOAD_INVALID")
    validate_request(req)
    job_id = req["job_id"]
    req.setdefault("session_id", f"{job_id}-{secrets.token_hex(6)}")
    req.setdefault("max_duration_ms", 600000)

    UI_JOBS.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(UI_JOBS, 0o700)
    ui_dir = UI_JOBS / job_id
    ensure_cancel_signal_dir()
    cancel_signal_path(job_id).unlink(missing_ok=True)
    if ui_dir.exists():
        existing = read_json(ui_dir / "result.json")
        if existing:
            return existing
        raise UiJobError("JOB_CLAIM_CONFLICT: existing incomplete job")

    ui_dir.mkdir(mode=0o700)
    (ui_dir / "evidence").mkdir(mode=0o700)
    (ui_dir / ".claim").mkdir(mode=0o700)
    atomic_json(ui_dir / "workflow.json", req)
    atomic_json(ui_dir / "state.json", {"status": "RUNNING", "updated_at": now_iso()})
    write_checkpoint(ui_dir, req, -1, True)
    append_journal(ui_dir / "journal.jsonl", {
        "timestamp": now_iso(), "phase": "SESSION_START",
        "job_id": job_id, "session_id": req["session_id"],
    })

    payload = base64.b64encode(json.dumps(req, separators=(",", ":")).encode()).decode()
    timeout_sec = min(620, max(30, int(req["max_duration_ms"] / 1000) + 20))
    command = (
        f"toybox timeout {timeout_sec} "
        f"/data/local/y700-agent/workspaces/y700-agent/bridge/android-runtime-env.sh "
        f"/system/bin/su 2000 -c "
        f"'/system/bin/am instrument -w -r -e request_b64 {payload} "
        f"-e class {DRIVER_CLASS} {DRIVER_COMPONENT}'"
    )

    started = time.monotonic()
    rc, stdout, stderr, heartbeats = run_bridge_command(command, ui_dir, timeout_sec=timeout_sec + 20)
    atomic_write(ui_dir / "instrumentation.out", stdout.encode())
    atomic_write(ui_dir / "instrumentation.err", stderr.encode())

    markers = decode_markers(stdout, RESULT_RE)
    if markers:
        result = markers[-1]
    else:
        last = heartbeats[-1] if heartbeats else None
        completed = int(last.get("action_index", -1)) if last and last.get("state") == "PASS" else -1
        action = req["actions"][completed] if completed >= 0 else {}
        safe = action.get("action") in SAFE_ACTIONS
        result = {
            "status": "FAILED",
            "job_id": job_id,
            "session_id": req["session_id"],
            "driver_version": "unknown",
            "protocol_version": 1,
            "actions": [],
            "error": {
                "code": "DRIVER_CRASHED",
                "message": f"instrumentation exited rc={rc} without structured result",
                "retryable": safe,
            },
        }
        write_checkpoint(ui_dir, req, completed, safe)
        append_journal(ui_dir / "journal.jsonl", {
            "timestamp": now_iso(), "phase": "SESSION_CRASH",
            "exit_code": rc, "safe_to_resume": safe,
        })

    completed_index = -1
    all_safe = True
    for i, action_result in enumerate(result.get("actions", [])):
        status = action_result.get("status")
        action = req["actions"][i] if i < len(req["actions"]) else {}
        side_effect = action.get("side_effect", "OBSERVE_ONLY" if action.get("action") in SAFE_ACTIONS else "REVERSIBLE_LOCAL")
        safe = status == "PASS" and side_effect in {"OBSERVE_ONLY", "REVERSIBLE_LOCAL", "IDEMPOTENT"}
        append_journal(ui_dir / "journal.jsonl", {
            "timestamp": now_iso(),
            "phase": "POSTCONDITION_PASS" if status == "PASS" else "ACTION_FAILED",
            "action_index": i,
            "action_id": action.get("action_id"),
            "action": action.get("action"),
            "side_effect": side_effect,
            "status": status,
            "safe_checkpoint": safe,
        })
        if status == "PASS":
            completed_index = i
            all_safe = all_safe and safe
        else:
            all_safe = False
            break

        data = action_result.get("data") or {}
        screenshot_path = data.get("path")
        if screenshot_path:
            copied = copy_screenshot(screenshot_path, ui_dir, Path(screenshot_path).name)
            if copied:
                data["evidence_path"] = copied

    if result.get("status") == "PASS":
        write_checkpoint(ui_dir, req, completed_index, all_safe)
    elif markers:
        safe = True if completed_index < 0 else all_safe
        write_checkpoint(ui_dir, req, completed_index, safe)

    if result.get("status") not in {"PASS", "CANCELLED"}:
        try:
            export_failure_evidence(ui_dir, req, result)
        except Exception as exc:
            append_journal(ui_dir / "journal.jsonl", {
                "timestamp": now_iso(),
                "phase": "FAILURE_EVIDENCE_CAPTURE_FAILED",
                "error": f"{type(exc).__name__}: {exc}",
            })

    result["host_duration_ms"] = round((time.monotonic() - started) * 1000, 1)
    result["host_exit_code"] = rc
    if isinstance(req.get("vision"), dict):
        finalize_vision_evidence(ui_dir, req, result)
    atomic_json(ui_dir / "result.json", result)
    atomic_json(ui_dir / "state.json", {"status": result.get("status", "FAILED"), "updated_at": now_iso()})
    append_journal(ui_dir / "journal.jsonl", {
        "timestamp": now_iso(), "phase": "SESSION_END",
        "status": result.get("status"), "exit_code": rc,
    })
    return result


def status(job_id: str) -> dict[str, Any]:
    if not JOB_RE.fullmatch(job_id):
        raise UiJobError("invalid job id")
    d = UI_JOBS / job_id
    if not d.exists():
        raise UiJobError("job not found")
    return {
        "state": read_json(d / "state.json", {}),
        "heartbeat": read_json(d / "heartbeat.json", {}),
        "checkpoint": read_json(d / "checkpoint.json", {}),
        "result": read_json(d / "result.json"),
    }


def cancel(job_id: str, reason: str = "user_requested") -> dict[str, Any]:
    if not JOB_RE.fullmatch(job_id):
        raise UiJobError("invalid job id")
    d = UI_JOBS / job_id
    if not d.is_dir():
        raise UiJobError("job not found")
    existing = read_json(d / "result.json")
    if existing:
        return status(job_id)
    payload = {"requested_at": now_iso(), "requested_by": "controller", "reason": reason[:256]}
    atomic_json(d / "cancel.json", payload)
    publish_cancel_signal(job_id)
    append_journal(d / "journal.jsonl", {"timestamp": now_iso(), "phase": "CANCEL_REQUESTED", **payload})
    atomic_json(d / "state.json", {"status": "CANCELLING", "updated_at": now_iso()})
    return status(job_id)


def main() -> int:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("run")
    p.add_argument("workflow")
    p = sp.add_parser("status")
    p.add_argument("job_id")
    p = sp.add_parser("cancel")
    p.add_argument("job_id")
    p.add_argument("--reason", default="user_requested")
    args = ap.parse_args()

    try:
        if args.cmd == "run":
            out = run_workflow(Path(args.workflow))
        elif args.cmd == "cancel":
            out = cancel(args.job_id, args.reason)
        else:
            out = status(args.job_id)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if (out.get("status") == "PASS" if args.cmd == "run" else True) else 1
    except UiJobError as e:
        print(json.dumps({"status": "BLOCKED", "error": str(e)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
