#!/usr/bin/env python3
"""Run the Sprint V0 Vision benchmark on the real Y700.

This invokes only the dedicated debug benchmark instrumentation. It does not
enable Vision routing in production AutomationInstrumentedTest workflows.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

ROOT_EXEC = Path(os.environ.get(
    "Y700_ROOT_EXEC",
    "/opt/y700/workspaces/y700-agent/bridge/root-exec.sh",
))
RUNTIME = Path(os.environ.get(
    "Y700_VISION_V0_RUNTIME",
    "/opt/y700/runtime/vision-v0",
))
RUNNER = (
    "com.stanley.y700automation.test/"
    "androidx.test.runner.AndroidJUnitRunner"
)
TEST = (
    "com.stanley.y700automation.vision."
    "VisionV0BenchmarkInstrumentedTest#runVisionV0Benchmark"
)


def extract_report(stdout: str) -> dict:
    prefix = "INSTRUMENTATION_STATUS: vision_v0_json="
    for line in stdout.splitlines():
        if line.startswith(prefix):
            return json.loads(line[len(prefix):])
    raise RuntimeError("vision_v0_json status was not emitted")


def gate(report: dict) -> dict:
    memory = report.get("memory") or {}
    managed_delta = abs(int(memory.get("managed_delta") or 0))
    native_delta = abs(int(memory.get("native_delta") or 0))
    checks = {
        "benchmark_pass": report.get("status") == "PASS",
        "semantic_target_absent": report.get("semantic_target_present") is False,
        "bounded_frames": int(report.get("peak_concurrent_frames") or 999) <= 2,
        "raw_profile_validated": bool((report.get("raw_screencap_profile") or {}).get("profile")),
        "locate_click_postcondition": bool(
            (report.get("locate_click_verify") or {}).get("postcondition_pass")
        ),
        "low_information_guard": bool(
            (report.get("low_information_guard") or {}).get("guard_rejected")
        ),
        "capture_retry_bounded": (
            (report.get("capture_retry") or {}).get("max_retries") == 1
            and (report.get("capture_retry") or {}).get("repeated_failure_fail_closed") is True
        ),
        "rotation_race_zero_click": (
            (report.get("rotation_race") or {}).get("blocked") is True
            and (report.get("rotation_race") or {}).get("click_attempted") is False
        ),
        "stale_target_blocked": bool(
            (report.get("stale_target") or {}).get("blocked")
        ),
        "memory_pressure_fail_closed": bool(
            (report.get("memory_pressure_guard") or {}).get("throttled")
        ),
        # V0 benchmark guardrail, not a frozen production target. This catches
        # runaway retention while allowing one-time OpenCV/runtime caches.
        "post_gc_memory_delta_bounded": (
            managed_delta <= 128 * 1024 * 1024
            and native_delta <= 128 * 1024 * 1024
        ),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "provisional_memory_guard_bytes": 128 * 1024 * 1024,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    if not ROOT_EXEC.is_file():
        raise SystemExit(f"root-exec not found: {ROOT_EXEC}")

    command = (
        f"am force-stop com.stanley.y700automation; "
        f"am instrument -w -r -e class '{TEST}' '{RUNNER}'"
    )
    env = dict(os.environ)
    env["Y700_BRIDGE_TIMEOUT_MS"] = "600000"
    started = time.monotonic()
    proc = subprocess.run(
        [str(ROOT_EXEC), command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=660,
        env=env,
    )
    duration = round(time.monotonic() - started, 3)

    try:
        report = extract_report(proc.stdout)
    finally:
        subprocess.run(
            [str(ROOT_EXEC), "am force-stop com.stanley.y700automation"],
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            env=env,
        )

    result = {
        "executed_at_epoch": time.time(),
        "duration_s": duration,
        "instrumentation_exit_code": proc.returncode,
        "report": report,
        "gate_v0": gate(report),
    }

    RUNTIME.mkdir(parents=True, exist_ok=True)
    out = args.output or RUNTIME / (
        "vision-v0-" + time.strftime("%Y%m%d-%H%M%S") + ".json"
    )
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, out)

    print(json.dumps({
        "status": result["gate_v0"]["status"],
        "duration_s": duration,
        "output": str(out),
        "checks": result["gate_v0"]["checks"],
        "capture_warm_20": report.get("capture_warm_20"),
        "capture_stability_200": report.get("capture_stability_200"),
        "raw_screencap_20": report.get("raw_screencap_20"),
        "template_benchmarks": report.get("template_benchmarks"),
        "memory": report.get("memory"),
    }, ensure_ascii=False, indent=2))
    return 0 if proc.returncode == 0 and result["gate_v0"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
