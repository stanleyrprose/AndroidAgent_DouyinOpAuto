#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(os.environ.get("Y700_ACCEPTANCE_REPO", "/opt/y700/workspaces/y700-agent"))
RUNTIME = Path(os.environ.get(
    "Y700_AUTOMATION_ACCEPTANCE_RUNTIME",
    "/opt/y700/runtime/observation-failure-acceptance",
))
ROOT_EXEC = REPO / "bridge" / "root-exec.sh"
sys.path.insert(0, str(REPO / "automation"))
import ui_job  # noqa: E402


def root_exec(command: str) -> None:
    p = subprocess.run([str(ROOT_EXEC), command], text=True, capture_output=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError(f"root_exec failed rc={p.returncode}: {p.stderr}")


def run(req: dict) -> tuple[dict, Path]:
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = RUNTIME / f"{req['job_id']}.json"
    ui_job.atomic_json(path, req)
    try:
        result = ui_job.run_workflow(path)
    finally:
        path.unlink(missing_ok=True)
    return result, ui_job.UI_JOBS / req["job_id"]


def action(result: dict) -> dict:
    rows = result.get("actions") or []
    if len(rows) != 1:
        raise AssertionError(f"expected one action result, got {len(rows)}")
    return rows[0]


def main() -> int:
    suffix = secrets.token_hex(3)
    root_exec("am force-stop com.android.settings; am start -a android.settings.SETTINGS >/dev/null")
    time.sleep(0.5)

    recovered, _ = run({
        "protocol_version": 1,
        "job_id": f"observe-recover-{suffix}",
        "test_mode": True,
        "test_observe_failures": 2,
        "max_duration_ms": 30000,
        "actions": [{
            "action_id": "observe",
            "action": "observe",
            "retry": 2,
            "retry_backoff_ms": [100, 100],
        }],
    })
    one = action(recovered)
    if recovered.get("status") != "PASS":
        raise AssertionError(f"observation recovery did not PASS: {recovered}")
    if one.get("attempts") != 3:
        raise AssertionError(f"expected 3 attempts: {one}")
    if one.get("recovery") != ["LEVEL_0_REOBSERVE", "LEVEL_1_WAIT_STABLE"]:
        raise AssertionError(f"unexpected recovery ladder: {one.get('recovery')}")

    blocked, blocked_dir = run({
        "protocol_version": 1,
        "job_id": f"observe-blocked-{suffix}",
        "test_mode": True,
        "test_observe_failures": 3,
        "max_duration_ms": 30000,
        "actions": [{
            "action_id": "observe",
            "action": "observe",
            "retry": 2,
            "retry_backoff_ms": [100, 100],
        }],
    })
    b = action(blocked)
    if blocked.get("status") != "BLOCKED":
        raise AssertionError(f"expected BLOCKED: {blocked}")
    if (b.get("error") or {}).get("code") != "UI_OBSERVATION_FAILED":
        raise AssertionError(f"unexpected observation error: {b}")
    expected = ["LEVEL_0_REOBSERVE", "LEVEL_1_WAIT_STABLE", "LEVEL_7_BLOCKED_EVIDENCE"]
    if b.get("recovery") != expected:
        raise AssertionError(f"unexpected blocked ladder: {b.get('recovery')}")

    context_path = blocked_dir / "evidence" / "failure-context.json"
    tree_path = blocked_dir / "evidence" / "failure-tree.json"
    if not context_path.is_file() or not tree_path.is_file():
        raise AssertionError("failure context/tree evidence missing")
    context = json.loads(context_path.read_text(encoding="utf-8"))
    required = {
        "timestamp", "action", "selector", "postcondition", "error",
        "package", "activity", "screenshot", "compact_ui_tree",
    }
    missing = sorted(k for k in required if k not in context)
    if missing:
        raise AssertionError(f"failure context missing fields: {missing}")
    shot = context.get("screenshot")
    if not shot or not (blocked_dir / shot).is_file():
        raise AssertionError(f"failure screenshot missing: {shot}")
    if context.get("compact_ui_tree") != "evidence/failure-tree.json":
        raise AssertionError(f"unexpected tree reference: {context}")
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    if not isinstance(tree.get("elements"), list):
        raise AssertionError("failure tree elements missing")

    print(json.dumps({
        "status": "PASS",
        "observation_recovery": {
            "attempts": one.get("attempts"),
            "ladder": one.get("recovery"),
        },
        "observation_blocked": {
            "status": blocked.get("status"),
            "ladder": b.get("recovery"),
            "error": b.get("error"),
        },
        "failure_evidence": {
            "context": str(context_path),
            "tree": str(tree_path),
            "screenshot": str(blocked_dir / shot),
            "required_fields_present": True,
        },
        "normal_tiktok_path_modified": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
