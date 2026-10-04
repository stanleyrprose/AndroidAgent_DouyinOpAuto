#!/usr/bin/env python3
"""Run the Sprint V0 Vision benchmark on the real Y700.

This invokes only the dedicated debug benchmark instrumentation. It does not
enable Vision routing in production AutomationInstrumentedTest workflows.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import struct
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
RAW_HOST_PATH = "/data/local/y700-agent/runtime/vision-v0/raw-diagnostic/raw.bin"
RAW_LOCAL_PATH = RUNTIME / "raw-diagnostic" / "raw.bin"
RUNNER = (
    "com.stanley.y700automation.test/"
    "androidx.test.runner.AndroidJUnitRunner"
)
TEST = (
    "com.stanley.y700automation.vision."
    "VisionV0BenchmarkInstrumentedTest#runVisionV0Benchmark"
)


_PIXEL_BYTES = {
    1: 4,  # RGBA_8888
    2: 4,  # RGBX_8888
    3: 3,  # RGB_888
    4: 2,  # RGB_565
    5: 4,  # BGRA_8888 on platform variants
}


def _percentiles(samples: list[float]) -> dict:
    if not samples:
        return {}
    values = sorted(samples)

    def q(p: float) -> float:
        if len(values) == 1:
            return values[0]
        pos = p * (len(values) - 1)
        lo = math.floor(pos)
        hi = math.ceil(pos)
        if lo == hi:
            return values[lo]
        f = pos - lo
        return values[lo] * (1.0 - f) + values[hi] * f

    return {
        "count": len(values),
        "p50_ms": q(0.50),
        "p95_ms": q(0.95),
        "min_ms": values[0],
        "max_ms": values[-1],
    }


def _parse_raw_profile(path: Path) -> dict:
    size = path.stat().st_size
    with path.open("rb") as f:
        header = f.read(16)
    if len(header) < 12:
        raise RuntimeError("VISION_UNSUPPORTED_FRAME_FORMAT: header too short")

    candidates = []
    if len(header) >= 16:
        width, height, pixel_format, dataspace = struct.unpack("<IIII", header[:16])
        candidates.append(
            ("ANDROID_4FIELD_Y700_A16", 16, width, height, pixel_format, dataspace)
        )
    width, height, pixel_format = struct.unpack("<III", header[:12])
    candidates.append(("LEGACY_3FIELD", 12, width, height, pixel_format, None))

    for profile, header_bytes, width, height, pixel_format, dataspace in candidates:
        if not (0 < width <= 8192 and 0 < height <= 8192):
            continue
        bpp = _PIXEL_BYTES.get(pixel_format)
        if bpp is None:
            continue
        payload = size - header_bytes
        if payload <= 0 or payload % height != 0:
            continue
        row_bytes = payload // height
        min_row_bytes = width * bpp
        if row_bytes < min_row_bytes or row_bytes > 8192 * 8:
            continue
        if row_bytes * height != payload:
            continue
        return {
            "profile": profile,
            "header_bytes": header_bytes,
            "width": width,
            "height": height,
            "pixel_format": pixel_format,
            "dataspace": dataspace,
            "bytes_per_pixel": bpp,
            "row_bytes": row_bytes,
            "payload_bytes": payload,
            "total_bytes": size,
            "tightly_packed": row_bytes == min_row_bytes,
        }

    raise RuntimeError(
        "VISION_UNSUPPORTED_FRAME_FORMAT: no supported profile "
        f"size={size} first16={header[:16].hex()}"
    )


def _run_root(
    command: str,
    env: dict[str, str],
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT_EXEC), command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=env,
        check=False,
    )


def raw_screencap_benchmark(env: dict[str, str], runs: int = 20) -> dict:
    samples: list[float] = []
    profile = None
    RAW_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(runs):
        command = (
            "mkdir -p /data/local/y700-agent/runtime/vision-v0/raw-diagnostic; "
            "t0=$(date +%s%N); "
            f"screencap > {RAW_HOST_PATH}.tmp; "
            "t1=$(date +%s%N); "
            f"mv {RAW_HOST_PATH}.tmp {RAW_HOST_PATH}; "
            f"chmod 600 {RAW_HOST_PATH}; "
            "echo ELAPSED_NS=$((t1-t0))"
        )
        proc = _run_root(command, env)
        if proc.returncode != 0:
            raise RuntimeError(
                "VISION_CAPTURE_FAILED raw screencap: "
                + (proc.stderr.strip() or proc.stdout.strip())
            )
        timing = next(
            (x for x in proc.stdout.splitlines() if x.startswith("ELAPSED_NS=")),
            None,
        )
        if timing is None:
            raise RuntimeError("VISION_CAPTURE_FAILED raw timing missing")
        samples.append(int(timing.split("=", 1)[1]) / 1_000_000.0)
        if profile is None:
            profile = _parse_raw_profile(RAW_LOCAL_PATH)

    RAW_LOCAL_PATH.unlink(missing_ok=True)
    return {
        "latency": _percentiles(samples),
        "profile": profile,
        "transport": "exec:screencap via existing Bridge/root path",
        "routine_hot_path": False,
    }


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

    env = dict(os.environ)
    env["Y700_BRIDGE_TIMEOUT_MS"] = "600000"

    raw = raw_screencap_benchmark(env)

    command = (
        f"am force-stop com.stanley.y700automation; "
        f"am instrument -w -r -e class '{TEST}' '{RUNNER}'"
    )
    started = time.monotonic()
    proc = subprocess.run(
        [str(ROOT_EXEC), command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=600,
        env=env,
    )
    duration = round(time.monotonic() - started, 3)

    try:
        report = extract_report(proc.stdout)
        report["raw_screencap_20"] = raw["latency"]
        report["raw_screencap_profile"] = raw["profile"]
        report["raw_screencap_transport"] = raw["transport"]
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
    return 0 if result["gate_v0"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
