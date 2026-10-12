#!/usr/bin/env python3
"""Rev3.7 D-G3 Y700 *read-only* frame/context drift probe.

It captures screenshot pixels only into Android /dev/null, obtains foreground,
rotation, display geometry, boot, screen and limited keyguard observations on
both sides of capture. Never produces an authoritative frame token, locator,
live JIT approval or any Android input action. No raw app identity is printed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ROOT_EXEC = ROOT / "bridge" / "root-exec.sh"

BOOT = re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27,36}$", re.IGNORECASE)
UPTIME = re.compile(r"^([0-9]+)\.([0-9]{1,})\s+[0-9.]+$")
ROTATION = re.compile(r"mDisplayRotation=ROTATION_(0|90|180|270)")
DISPLAY = re.compile(r"\bcur=([0-9]+)x([0-9]+)\b")
FOREGROUND = re.compile(r"\bu[0-9]+\s+([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)\s+t[0-9]+\b")
PHASES = ("PRE", "POST")
REQUIRED = ("BOOT", "UPTIME", "WINDOW", "ROTATION", "FOREGROUND", "WAKE", "INPUT_RESTRICTED")


class ContextProbeError(ValueError):
    pass


def context_commands(tag: str) -> str:
    return (
        f'printf "PHASE={tag}\\n"; '
        'printf "BOOT="; cat /proc/sys/kernel/random/boot_id; '
        'printf "UPTIME="; cat /proc/uptime; '
        'printf "WINDOW="; dumpsys window displays | grep -m1 -E '
        '"init=[0-9]+x[0-9]+.*cur=[0-9]+x[0-9]+"; '
        'printf "ROTATION="; dumpsys window displays | grep -m1 -o -E '
        '"mDisplayRotation=ROTATION_(0|90|180|270)"; '
        'printf "FOREGROUND="; dumpsys activity activities | grep -m1 -E '
        '"topResumedActivity=ActivityRecord|mResumedActivity=ActivityRecord"; '
        'printf "WAKE="; dumpsys power | grep -m1 -o -E '
        '"mWakefulness=[A-Za-z]+"; '
        'printf "INPUT_RESTRICTED="; dumpsys window policy | grep -m1 -o -E '
        '"mInputRestricted=(true|false)"; '
    )


def android_read_only_command() -> str:
    return (
        context_commands("PRE")
        + 'printf "CAPTURE_START="; cat /proc/uptime; '
        + '/system/bin/screencap -p >/dev/null; rc=$?; '
        + 'printf "CAPTURE_END="; cat /proc/uptime; '
        + 'printf "CAPTURE_RC=%s\\n" "$rc"; '
        + context_commands("POST")
    )


def _uptime_ms(raw: str) -> int:
    m = UPTIME.fullmatch(raw.strip())
    if m is None:
        raise ContextProbeError("UPTIME_UNAVAILABLE")
    whole, fraction = m.groups()
    return int(whole) * 1000 + int((fraction + "000")[:3])


def parse_context_probe(raw: str) -> dict[str, Any]:
    phases: dict[str, dict[str, str]] = {}
    global_rows: dict[str, str] = {}
    active: str | None = None
    for line in raw.splitlines():
        if line.startswith("PHASE="):
            phase = line.partition("=")[2]
            if phase not in PHASES or phase in phases:
                raise ContextProbeError("CONTEXT_PHASE_INVALID")
            active = phase
            phases[phase] = {}
            continue
        key, sep, value = line.partition("=")
        if not sep or not value.strip():
            raise ContextProbeError("CONTEXT_FIELD_INVALID")
        where = global_rows if key.startswith("CAPTURE_") else phases.get(active or "")
        if where is None or key in where:
            raise ContextProbeError("CONTEXT_FIELD_DUPLICATE")
        where[key] = value.strip()
    if set(phases) != set(PHASES) or set(global_rows) != {"CAPTURE_START", "CAPTURE_END", "CAPTURE_RC"}:
        raise ContextProbeError("CONTEXT_MISSING")
    if global_rows["CAPTURE_RC"] != "0":
        raise ContextProbeError("ANDROID_CAPTURE_FAILED")

    parsed: dict[str, dict[str, Any]] = {}
    for tag in PHASES:
        values = phases[tag]
        if set(values) != set(REQUIRED):
            raise ContextProbeError("CONTEXT_MISSING")
        boot = values["BOOT"]
        rotation = ROTATION.fullmatch(values["ROTATION"])
        display = DISPLAY.search(values["WINDOW"])
        foreground = FOREGROUND.search(values["FOREGROUND"])
        wake = values["WAKE"]
        restricted = values["INPUT_RESTRICTED"]
        if (not BOOT.fullmatch(boot) or rotation is None or display is None
            or foreground is None or wake not in {"mWakefulness=Awake", "mWakefulness=Asleep", "mWakefulness=Dozing"}
            or restricted not in {"mInputRestricted=true", "mInputRestricted=false"}):
            raise ContextProbeError("CONTEXT_UNVERIFIABLE")
        width, height = (int(v) for v in display.groups())
        if not (width > 0 and height > 0):
            raise ContextProbeError("DISPLAY_UNAVAILABLE")
        parsed[tag] = {
            "boot": boot,
            "uptime_ms": _uptime_ms(values["UPTIME"]),
            "rotation": int(rotation.group(1)) // 90,
            "display_geometry": (width, height),
            "foreground": foreground.groups(),
            "wake": wake,
            "input_restricted": restricted,
        }

    start = _uptime_ms(global_rows["CAPTURE_START"])
    end = _uptime_ms(global_rows["CAPTURE_END"])
    pre, post = parsed["PRE"], parsed["POST"]
    if not (pre["uptime_ms"] <= start < end <= post["uptime_ms"]):
        raise ContextProbeError("CONTEXT_CLOCK_ORDER_INVALID")
    if pre["boot"] != post["boot"]:
        raise ContextProbeError("FRAME_BOOT_MISMATCH")
    diffs = [
        key for key in ("rotation", "display_geometry", "foreground", "wake", "input_restricted")
        if pre[key] != post[key]
    ]
    # Never reveal current Android foreground identity to logs or CI reports.
    return {
        "status": "OBSERVED_READ_ONLY",
        "scope": "CAPTURE_PLUS_PRE_POST_CONTEXT",
        "production_gate_passed": False,
        "dg3_status": "OPEN",
        "frame_token_issued": False,
        "locator_attempted": False,
        "visual_dispatch_allowed": False,
        "ui_mutation_attempts": 0,
        "pixel_retention": "NONE",
        "timing_clock": "ANDROID_PROC_UPTIME_PROXY",
        "capture_ms": end - start,
        "post_capture_context_ms": post["uptime_ms"] - end,
        "pre_capture_context_ms": start - pre["uptime_ms"],
        "context_stable": not diffs,
        "context_drift_fields": diffs,
        "screen_interactive_pre": pre["wake"] == "mWakefulness=Awake",
        "screen_interactive_post": post["wake"] == "mWakefulness=Awake",
        "keyguard_unlocked_verified": False,
        "state_epoch_revision_observed": False,
        "frame_age_at_locator_ms": "NOT_MEASURED",
        "frame_age_at_dispatch_ms": "NOT_MEASURED",
        "max_frame_age_ms_calibrated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Y700 read-only screenshot context drift, no pixel retention")
    parser.parse_args()
    try:
        cmd = android_read_only_command()
        result = subprocess.run(
            ["bash", str(ROOT_EXEC), cmd], capture_output=True, text=True,
            timeout=75, check=False,
        )
        if result.returncode:
            raise ContextProbeError("BRIDGE_CONTEXT_CAPTURE_FAILED")
        summary = parse_context_probe(result.stdout)
    except (ContextProbeError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({
            "status": "FAILED", "dg3_status": "OPEN",
            "production_gate_passed": False,
            "ui_mutation_attempts": 0,
            "error_code": str(exc).split(":")[0],
        }, sort_keys=True))
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
