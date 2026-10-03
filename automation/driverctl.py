#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.umask(0o077)

REPO = Path("/opt/y700/workspaces/y700-agent")
UI_JOBS = Path("/opt/y700/ui-jobs")
RUNTIME = Path("/opt/y700/runtime/automation-driver")
ROOT_EXEC = REPO / "bridge" / "root-exec.sh"

sys.path.insert(0, str(REPO / "automation"))
import ui_job  # noqa: E402


def root_exec(command: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT_EXEC), command],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def mode(path: Path) -> str | None:
    if not path.exists():
        return None
    return oct(stat.S_IMODE(path.stat().st_mode))[2:]


def root_facts() -> dict[str, Any]:
    cmd = r'''
echo "SECTION battery"
dumpsys battery | grep -E 'level:|temperature:|status:' | head -10
echo "SECTION power"
dumpsys power | grep -E 'mWakefulness=|Display Power' | head -10
echo "SECTION thermal"
dumpsys thermalservice 2>/dev/null | grep -E 'Thermal Status|Status:' | head -10
echo "SECTION disk"
df -k /data | tail -1
echo "SECTION memory"
grep -E 'MemTotal|MemAvailable' /proc/meminfo
echo "SECTION instrumentation"
pm list instrumentation | grep com.stanley.y700automation || true
echo "SECTION ime"
settings get secure default_input_method
'''
    p = root_exec(cmd)
    return {
        "exit_code": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr,
    }


def parse_root_facts(raw: dict[str, Any]) -> dict[str, Any]:
    sections: dict[str, list[str]] = {}
    cur = None
    for line in raw.get("stdout", "").splitlines():
        if line.startswith("SECTION "):
            cur = line.split(" ", 1)[1].strip()
            sections[cur] = []
        elif cur:
            sections[cur].append(line.strip())

    battery_level = None
    battery_temp_c = None
    for line in sections.get("battery", []):
        if line.startswith("level:"):
            try:
                battery_level = int(line.split(":", 1)[1].strip())
            except Exception:
                pass
        elif line.startswith("temperature:"):
            try:
                battery_temp_c = int(line.split(":", 1)[1].strip()) / 10.0
            except Exception:
                pass

    mem_total_kb = None
    mem_available_kb = None
    for line in sections.get("memory", []):
        if line.startswith("MemTotal:"):
            try:
                mem_total_kb = int(line.split()[1])
            except Exception:
                pass
        elif line.startswith("MemAvailable:"):
            try:
                mem_available_kb = int(line.split()[1])
            except Exception:
                pass

    disk = None
    if sections.get("disk"):
        parts = sections["disk"][0].split()
        if len(parts) >= 6:
            disk = {
                "filesystem": parts[0],
                "blocks_kb": int(parts[1]),
                "used_kb": int(parts[2]),
                "available_kb": int(parts[3]),
                "use_percent": parts[4],
                "mount": parts[5],
            }

    return {
        "root_bridge_exit_code": raw.get("exit_code"),
        "battery_percent": battery_level,
        "battery_temperature_c": battery_temp_c,
        "memory_total_mb": round(mem_total_kb / 1024, 1) if mem_total_kb else None,
        "memory_available_mb": round(mem_available_kb / 1024, 1) if mem_available_kb else None,
        "disk": disk,
        "power_raw": sections.get("power", []),
        "thermal_raw": sections.get("thermal", []),
        "instrumentation_registered": bool(sections.get("instrumentation")),
        "ime": sections.get("ime", [None])[0] if sections.get("ime") else None,
        "root_bridge_stderr": raw.get("stderr") or None,
    }


def run_health_workflow() -> dict[str, Any]:
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    job_id = f"driver-health-{int(time.time())}"
    workflow_path = RUNTIME / f"{job_id}.json"
    request = {
        "protocol_version": 1,
        "job_id": job_id,
        "max_duration_ms": 30000,
        "actions": [{"action_id": "health", "action": "health"}],
    }
    ui_job.atomic_json(workflow_path, request)
    try:
        result = ui_job.run_workflow(workflow_path)
    finally:
        workflow_path.unlink(missing_ok=True)
    return result


def cmd_health() -> int:
    driver = run_health_workflow()
    action = (driver.get("actions") or [{}])[0]
    driver_data = action.get("data") or {}
    host = parse_root_facts(root_facts())

    overall = "HEALTHY"
    reasons: list[str] = []
    if driver.get("status") != "PASS":
        overall = "DEGRADED"
        reasons.append("DRIVER_WORKFLOW_FAILED")
    if not driver_data.get("uiautomator_ready"):
        overall = "DEGRADED"
        reasons.append("UIAUTOMATOR_NOT_READY")
    if not host.get("instrumentation_registered"):
        overall = "DEGRADED"
        reasons.append("INSTRUMENTATION_NOT_REGISTERED")
    if host.get("root_bridge_exit_code") != 0:
        overall = "DEGRADED"
        reasons.append("ROOT_BRIDGE_FAILED")
    if host.get("battery_temperature_c") is not None and host["battery_temperature_c"] >= 45:
        overall = "DEGRADED"
        reasons.append("THERMAL_HIGH")

    out = {
        "status": overall,
        "reasons": reasons,
        "driver": driver_data,
        "runtime": host,
        "checked_at": datetime.now(timezone.utc).astimezone().isoformat(),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if overall == "HEALTHY" else 1


def cmd_permission_check() -> int:
    checks: list[dict[str, Any]] = []
    UI_JOBS.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(UI_JOBS, 0o700)
    checks.append({
        "name": "ui_jobs_root",
        "path": str(UI_JOBS),
        "mode": mode(UI_JOBS),
        "pass": mode(UI_JOBS) == "700",
    })

    probe = UI_JOBS / f".permission-probe-{os.getpid()}"
    probe.mkdir(mode=0o700)
    f = probe / "probe.json"
    ui_job.atomic_json(f, {"ok": True})
    checks.append({
        "name": "ui_job_file",
        "path": str(f),
        "mode": mode(f),
        "pass": mode(f) == "600",
    })
    shutil.rmtree(probe)

    history = Path("/opt/y700/runtime/job-history")
    latest = None
    if history.exists():
        dirs = [p for p in history.iterdir() if p.is_dir()]
        if dirs:
            latest = max(dirs, key=lambda p: p.stat().st_mtime)
            checks.append({
                "name": "bridge_history_dir",
                "path": str(latest),
                "mode": mode(latest),
                "pass": mode(latest) == "700",
            })
            for name in ("request.json", "result.json", "state.json"):
                p = latest / name
                if p.exists():
                    checks.append({
                        "name": f"bridge_{name}",
                        "path": str(p),
                        "mode": mode(p),
                        "pass": mode(p) == "600",
                    })

    passed = all(x["pass"] for x in checks)
    out = {"status": "PASS" if passed else "FAILED", "checks": checks}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if passed else 1


def heartbeat_age(job_dir: Path) -> float | None:
    p = job_dir / "heartbeat.json"
    if not p.exists():
        return None
    return max(0.0, time.time() - p.stat().st_mtime)


def cmd_reset_driver(job_id: str | None, force: bool) -> int:
    target = UI_JOBS / job_id if job_id else None
    reconcile_required = False

    if target and not target.exists():
        print(json.dumps({"status": "BLOCKED", "error": "job not found"}, ensure_ascii=False))
        return 2

    if target:
        state = ui_job.read_json(target / "state.json", {}) or {}
        checkpoint = ui_job.read_json(target / "checkpoint.json", {}) or {}
        age = heartbeat_age(target)

        if state.get("status") == "RUNNING" and age is not None and age < 10 and not force:
            print(json.dumps({
                "status": "BLOCKED",
                "error": "DRIVER_SESSION_STILL_HEALTHY",
                "heartbeat_age_sec": round(age, 2),
            }, ensure_ascii=False, indent=2))
            return 2

        reconcile_required = checkpoint.get("safe_to_resume") is False

    command = (
        "am force-stop com.stanley.y700automation.test 2>/dev/null || true; "
        "am force-stop com.stanley.y700automation 2>/dev/null || true; "
        "echo DRIVER_RESET"
    )
    p = root_exec(command)
    if p.returncode != 0:
        print(json.dumps({
            "status": "FAILED",
            "error": "DRIVER_RESTART_FAILED",
            "stderr": p.stderr,
        }, ensure_ascii=False, indent=2))
        return 1

    if target:
        ui_job.atomic_json(target / "recovery.json", {
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
            "action": "RESET_DRIVER",
            "result": "PASS",
            "reconcile_required": reconcile_required,
        })
        ui_job.atomic_json(target / "state.json", {
            "status": "BLOCKED" if reconcile_required else "FAILED",
            "reason": "RECONCILE_REQUIRED" if reconcile_required else "DRIVER_RESET",
            "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        })

    print(json.dumps({
        "status": "RECONCILE_REQUIRED" if reconcile_required else "PASS",
        "driver_reset": True,
        "job_id": job_id,
        "workflow_replayed": False,
    }, ensure_ascii=False, indent=2))
    return 3 if reconcile_required else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("health")
    sp.add_parser("permission-check")
    p = sp.add_parser("reset-driver")
    p.add_argument("--job-id")
    p.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.cmd == "health":
        return cmd_health()
    if args.cmd == "permission-check":
        return cmd_permission_check()
    return cmd_reset_driver(args.job_id, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
