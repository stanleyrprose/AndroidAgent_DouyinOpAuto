#!/usr/bin/env python3
"""Strict, zero-input Y700 TikTok Create cross-frame read-only probe.

Runs ONLY the isolated instrumentation method, never the mutating benchmark.
Android JUnit OK is NOT a locator acceptance: exact structured receipt must
independently prove all read-only flags. D-G3 production status is always OPEN.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ROOT_EXEC = ROOT / "bridge" / "root-exec.sh"
PROBE_CLASS = (
    "com.stanley.y700automation.vision."
    "Rev37ReadOnlyFrameReceiptInstrumentedTest#readOnlyTikTokCreateCrossFrameLocator"
)
INSTRUMENTATION = (
    "com.stanley.y700automation.dg3probe.test/"
    "androidx.test.runner.AndroidJUnitRunner"
)
COMMAND = f"am instrument -w -r -e class {PROBE_CLASS} {INSTRUMENTATION}"
RECEIPT_MARKER = "INSTRUMENTATION_STATUS: rev37_frame_receipt_json="
KNOWN_STATUS = frozenset({
    "READ_ONLY_CROSS_FRAME_TARGET_LOCATED",
    "READ_ONLY_FOREGROUND_OR_LOCKED",
    "READ_ONLY_SEMANTIC_TARGET_UNAVAILABLE",
    "READ_ONLY_TARGET_GEOMETRY_UNAVAILABLE",
    "READ_ONLY_REFERENCE_LOW_INFORMATION",
    "READ_ONLY_CROSS_FRAME_LOCATOR_BLOCKED",
    "READ_ONLY_CROSS_FRAME_CONTEXT_NOT_VERIFIED",
    "READ_ONLY_CROSS_FRAME_UNAVAILABLE",
    "READ_ONLY_UNAVAILABLE",
})
REQUIRED_TRUE = (
    "cross_frame_locator_attempted",
    "distinct_frame_generations", "locator_exact_frame_id",
    "semantic_target_consistent", "boot_id_readable",
    "boot_id_consistent", "screen_interactive", "keyguard_unlocked",
    "package_unchanged", "rotation_unchanged", "geometry_unchanged",
)
REQUIRED_FALSE = (
    "production_dg3_passed", "visual_dispatch_allowed",
    "pixel_persisted", "reference_template_persisted",
    "frame_token_authoritative", "semantic_epoch_revision_verified",
    "foreground_activity_verified", "blocking_overlay_verified",
    "route_age_calibrated",
)


class ReceiptError(ValueError):
    pass


def verify_receipt(raw: str) -> dict[str, Any]:
    """Structured read-only verdict with no pixels or app identity in output."""
    lines = raw.splitlines()
    receipts = [line[len(RECEIPT_MARKER):] for line in lines
                if line.startswith(RECEIPT_MARKER)]
    if len(receipts) != 1:
        raise ReceiptError("RECEIPT_COUNT_INVALID")
    if (
        "INSTRUMENTATION_STATUS: test=readOnlyTikTokCreateCrossFrameLocator" not in lines
        or "INSTRUMENTATION_STATUS: numtests=1" not in lines
        or "INSTRUMENTATION_CODE: -1" not in lines
        or not re.search(r"(?m)^OK \(1 test\)$", raw)
    ):
        raise ReceiptError("INSTRUMENTATION_NOT_VERIFIED")
    try:
        receipt = json.loads(receipts[0])
    except (TypeError, json.JSONDecodeError) as exc:
        raise ReceiptError("RECEIPT_JSON_INVALID") from exc
    if not isinstance(receipt, dict):
        raise ReceiptError("RECEIPT_JSON_INVALID")
    if (
        receipt.get("probe") != "rev37-tiktok-create-cross-frame-readonly-v1"
        or receipt.get("target_identity") != "TIKTOK_CREATE_ACCESSIBILITY_ANCHOR"
        or receipt.get("dg3_status") != "OPEN"
        or type(receipt.get("action_attempts")) is not int
        or receipt["action_attempts"] != 0
        or any(receipt.get(k) is not False for k in REQUIRED_FALSE)
    ):
        raise ReceiptError("NON_AUTHORITATIVE_GUARD_INVALID")
    status = receipt.get("status")
    if status not in KNOWN_STATUS:
        raise ReceiptError("RECEIPT_STATUS_UNKNOWN")
    result = {
        "status": "BLOCKED",
        "reason": status,
        "scope": "REAL_PIXEL_TIKTOK_CREATE_CROSS_FRAME_READ_ONLY",
        "dg3_status": "OPEN",
        "production_gate_passed": False,
        "visual_dispatch_allowed": False,
        "ui_mutation_attempts": 0,
    }
    if status != "READ_ONLY_CROSS_FRAME_TARGET_LOCATED":
        return result
    if any(receipt.get(k) is not True for k in REQUIRED_TRUE):
        raise ReceiptError("CROSS_FRAME_EVIDENCE_INCONSISTENT")
    for key in (
        "reference_capture_ms", "target_capture_ms", "locator_latency_ms",
        "frame_age_at_locator_ms", "frame_age_at_observation_ms",
        "capture_to_capture_start_ms",
    ):
        value = receipt.get(key)
        if type(value) is not int or value < 0:
            raise ReceiptError("CROSS_FRAME_TIMING_INVALID")
        result[key] = value
    if result["frame_age_at_observation_ms"] < result["frame_age_at_locator_ms"]:
        raise ReceiptError("CROSS_FRAME_CLOCK_ORDER_INVALID")
    result.update(status="VERIFIED_READ_ONLY", reason="READ_ONLY_CROSS_FRAME_TARGET_LOCATED")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Y700 read-only TikTok Create locator; no UI input")
    parser.add_argument("--input-path", type=Path, help="Parse existing instrumentation transcript offline")
    args = parser.parse_args()
    try:
        if args.input_path is not None:
            raw = args.input_path.read_text(encoding="utf-8")
        else:
            result = subprocess.run(
                ["bash", str(ROOT_EXEC), COMMAND],
                capture_output=True, text=True, timeout=90, check=False,
            )
            if result.returncode != 0:
                raise ReceiptError("ANDROID_READ_ONLY_PROBE_FAILED")
            raw = result.stdout
        verdict = verify_receipt(raw)
        print(json.dumps(verdict, sort_keys=True))
        return 0 if verdict["status"] == "VERIFIED_READ_ONLY" else 2
    except (ReceiptError, OSError, subprocess.TimeoutExpired):
        print(json.dumps({
            "status": "BLOCKED", "reason": "PROBE_OR_RECEIPT_INVALID",
            "dg3_status": "OPEN", "production_gate_passed": False,
            "visual_dispatch_allowed": False, "ui_mutation_attempts": 0,
        }, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
