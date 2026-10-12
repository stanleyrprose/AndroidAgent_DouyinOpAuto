#!/usr/bin/env python3
"""Y700 Android read-only capture timing, never a D-G3 production acceptance.

Uses existing Host Bridge, never stores or transmits screenshot pixel bytes.
Android /proc/uptime is used as a monotonic elapsed-boot timing proxy; its
precision and image pipeline differ from instrumentation's CLOCK_BOOTTIME.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROOT_EXEC = ROOT / "bridge" / "root-exec.sh"
SAMPLE = re.compile(r"^SAMPLE ([0-9]+) ([0-9]+\.[0-9]+) ([0-9]+\.[0-9]+) ([0-9]+)$")


class CaptureProbeError(RuntimeError):
    pass


def percentile_nearest(values: list[int], percentile: float) -> int:
    values = sorted(values)
    return values[max(0, math.ceil(percentile * len(values)) - 1)]


def parse_probe_output(stdout: str, count: int) -> list[int]:
    lines = stdout.strip().splitlines()
    if len(lines) != count:
        raise CaptureProbeError("CAPTURE_PROBE_SAMPLE_COUNT_MISMATCH")
    durations = []
    last_end: float | None = None
    for expected, line in enumerate(lines):
        m = SAMPLE.fullmatch(line.strip())
        if m is None or int(m.group(1)) != expected or int(m.group(4)) != 0:
            raise CaptureProbeError("CAPTURE_PROBE_SAMPLE_INVALID")
        start, end = float(m.group(2)), float(m.group(3))
        if not math.isfinite(start) or not math.isfinite(end) or end < start or start < 0:
            raise CaptureProbeError("CAPTURE_PROBE_CLOCK_INVALID")
        if last_end is not None and start < last_end:
            raise CaptureProbeError("CAPTURE_PROBE_CLOCK_REVERSED")
        duration = round((end - start) * 1000)
        if duration <= 0:
            raise CaptureProbeError("CAPTURE_PROBE_CLOCK_PRECISION")
        durations.append(duration)
        last_end = end
    return durations


def build_android_probe(count: int) -> str:
    if type(count) is not int or count < 3 or count > 30:
        raise CaptureProbeError("CAPTURE_PROBE_SAMPLE_LIMIT")
    # Every screencap is read-only. Pixels stream to /dev/null in the device
    # process; stdout includes numeric timings only. Do not write screenshots.
    return (
        "boot=$(cat /proc/sys/kernel/random/boot_id); "
        "test -n \"$boot\" || exit 43; "
        "i=0; "
        f"while [ \"$i\" -lt {count} ]; do "
        "read start unused < /proc/uptime; "
        "/system/bin/screencap -p >/dev/null; rc=$?; "
        "read finish unused < /proc/uptime; "
        "current=$(cat /proc/sys/kernel/random/boot_id); "
        "if [ \"$boot\" != \"$current\" ]; then echo BOOT_CHANGED; exit 42; fi; "
        'printf "SAMPLE %s %s %s %s\\n" "$i" "$start" "$finish" "$rc"; '
        'i=$((i+1)); done'
    )


def run_probe(count: int) -> dict:
    command = build_android_probe(count)
    result = subprocess.run(
        ["bash", str(ROOT_EXEC), command],
        capture_output=True, text=True, timeout=90, check=False,
    )
    if result.returncode != 0:
        raise CaptureProbeError(f"CAPTURE_PROBE_HOST_FAILED: rc={result.returncode}")
    durations = parse_probe_output(result.stdout, count)
    return {
        "status": "MEASURED_READ_ONLY",
        "scope": "ANDROID_SCREENCAP_ONLY",
        "production_gate_passed": False,
        "dg3_status": "OPEN",
        "sample_count": len(durations),
        "timing_clock": "ANDROID_PROC_UPTIME_BOOT_ELAPSED_PROXY",
        "precision_note": "centisecond device clock; not instrumentation CLOCK_BOOTTIME",
        "pixel_retention": "NONE",
        "ui_mutation_attempts": 0,
        "capture_ms": {
            "min": min(durations),
            "median": round(statistics.median(durations), 1),
            "p95_nearest_rank": percentile_nearest(durations, 0.95),
            "p99_nearest_rank": percentile_nearest(durations, 0.99),
            "max": max(durations),
        },
        "locator_latency_ms": "NOT_MEASURED",
        "frame_age_at_dispatch_ms": "NOT_MEASURED",
        "max_frame_age_ms_calibrated": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Read-only Android frame timing, no capture persistence")
    p.add_argument("--samples", type=int, default=20)
    args = p.parse_args()
    try:
        result = run_probe(args.samples)
    except (CaptureProbeError, subprocess.TimeoutExpired, OSError) as exc:
        print(json.dumps({
            "status": "FAILED",
            "dg3_status": "OPEN",
            "production_gate_passed": False,
            "error_code": str(exc).split(":", 1)[0],
        }, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
