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
RUNTIME = Path(
    os.environ.get(
        "Y700_AUTOMATION_ACCEPTANCE_RUNTIME",
        "/opt/y700/runtime/automation-driver",
    )
)
ROOT_EXEC = REPO / "bridge" / "root-exec.sh"

sys.path.insert(0, str(REPO / "automation"))
import ui_job  # noqa: E402


def root_exec(command: str) -> None:
    p = subprocess.run(
        [str(ROOT_EXEC), command],
        text=True,
        capture_output=True,
        timeout=30,
    )
    if p.returncode != 0:
        raise RuntimeError(f"root_exec failed rc={p.returncode}: {p.stderr}")


def main() -> int:
    suffix = secrets.token_hex(3)
    job_id = f"ui-cancel-accept-{suffix}"
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    workflow = RUNTIME / f"{job_id}.json"

    # Observation-only workload long enough to make cancellation at an action
    # boundary deterministic without introducing external side effects.
    req = {
        "protocol_version": 1,
        "job_id": job_id,
        "max_duration_ms": 120000,
        "actions": [
            {
                "action_id": f"stable-{i:02d}",
                "action": "waitStable",
                "timeout_ms": 5000,
            }
            for i in range(50)
        ],
    }
    ui_job.atomic_json(workflow, req)

    root_exec(
        "am force-stop com.android.settings; "
        "am start -a android.settings.SETTINGS >/dev/null"
    )
    time.sleep(0.5)

    env = os.environ.copy()
    proc = subprocess.Popen(
        [sys.executable, str(REPO / "automation" / "ui_job.py"), "run", str(workflow)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    ui_dir = ui_job.UI_JOBS / job_id
    heartbeat = {}
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(
                f"workflow ended before cancellation rc={proc.returncode} "
                f"stdout={out!r} stderr={err!r}"
            )
        heartbeat = ui_job.read_json(ui_dir / "heartbeat.json", {}) or {}
        if heartbeat.get("state") in {"STARTED", "PASS"}:
            break
        time.sleep(0.05)
    else:
        proc.terminate()
        proc.wait(timeout=5)
        raise RuntimeError("no action heartbeat before cancellation deadline")

    cancel_snapshot = ui_job.cancel(job_id, "a7_action_boundary_acceptance")
    out, err = proc.communicate(timeout=60)

    final = ui_job.status(job_id)
    result = final.get("result") or {}
    error = result.get("error") or {}
    actions = result.get("actions") or []
    checkpoint = final.get("checkpoint") or {}

    ok = (
        result.get("status") == "CANCELLED"
        and error.get("code") == "WORKFLOW_CANCELLED"
        and (ui_dir / "cancel.json").is_file()
        and len(actions) < len(req["actions"])
        and checkpoint.get("safe_to_resume") is True
    )
    summary = {
        "status": "PASS" if ok else "FAILED",
        "job_id": job_id,
        "heartbeat_before_cancel": heartbeat,
        "cancel_state": (cancel_snapshot.get("state") or {}).get("status"),
        "final_status": result.get("status"),
        "error_code": error.get("code"),
        "completed_actions": len(actions),
        "requested_actions": len(req["actions"]),
        "safe_to_resume": checkpoint.get("safe_to_resume"),
        "runner_exit_code": proc.returncode,
    }
    if not ok:
        summary["runner_stdout"] = out[-4000:]
        summary["runner_stderr"] = err[-4000:]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    workflow.unlink(missing_ok=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
