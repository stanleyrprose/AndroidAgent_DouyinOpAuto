"""Strict parsing: JUnit PASS alone must not pass a locked TikTok locator."""
import importlib.util
import json
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/v07/run-y700-create-readonly.py"
spec = importlib.util.spec_from_file_location("y700_readonly_receipt", SCRIPT)
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

BASE = {
    "probe": "rev37-tiktok-create-cross-frame-readonly-v1",
    "target_identity": "TIKTOK_CREATE_ACCESSIBILITY_ANCHOR",
    "dg3_status": "OPEN",
    "action_attempts": 0,
    **{key: False for key in probe.REQUIRED_FALSE},
}
GOOD = {
    **BASE,
    "status": "READ_ONLY_CROSS_FRAME_TARGET_LOCATED",
    **{key: True for key in probe.REQUIRED_TRUE},
    "reference_capture_ms": 420,
    "target_capture_ms": 450,
    "locator_latency_ms": 23,
    "frame_age_at_locator_ms": 500,
    "frame_age_at_observation_ms": 550,
    "capture_to_capture_start_ms": 475,
}


def transcript(receipt, *, junit_ok=True):
    body = [
        "INSTRUMENTATION_STATUS: numtests=1",
        "INSTRUMENTATION_STATUS: test=readOnlyTikTokCreateCrossFrameLocator",
        "INSTRUMENTATION_STATUS: rev37_frame_receipt_json=" + json.dumps(receipt),
    ]
    if junit_ok:
        body.extend(["OK (1 test)", "INSTRUMENTATION_CODE: -1"])
    return "\n".join(body) + "\n"


class CrossFrameReceiptParserTests(unittest.TestCase):
    def test_valid_receipt_is_readonly_never_production_pass(self):
        result = probe.verify_receipt(transcript(GOOD))
        self.assertEqual(result["status"], "VERIFIED_READ_ONLY")
        self.assertEqual(result["frame_age_at_observation_ms"], 550)
        self.assertIs(result["production_gate_passed"], False)
        self.assertIs(result["visual_dispatch_allowed"], False)
        self.assertEqual(result["ui_mutation_attempts"], 0)

    def test_junit_pass_with_locked_device_is_blocked(self):
        value = {**BASE, "status": "READ_ONLY_FOREGROUND_OR_LOCKED"}
        verdict = probe.verify_receipt(transcript(value))
        self.assertEqual(verdict["status"], "BLOCKED")
        self.assertEqual(verdict["reason"], "READ_ONLY_FOREGROUND_OR_LOCKED")

    def test_ambiguity_fails_readonly(self):
        value = {**BASE, "status": "READ_ONLY_CROSS_FRAME_LOCATOR_BLOCKED"}
        self.assertEqual(probe.verify_receipt(transcript(value))["status"], "BLOCKED")

    def test_dg3_caller_claims_cannot_override(self):
        value = {**GOOD, "production_dg3_passed": True}
        with self.assertRaisesRegex(probe.ReceiptError, "NON_AUTHORITATIVE_GUARD_INVALID"):
            probe.verify_receipt(transcript(value))

    def test_missing_boot_identity_rejected_even_when_status_claims_success(self):
        value = {**GOOD, "boot_id_consistent": False}
        with self.assertRaisesRegex(probe.ReceiptError, "CROSS_FRAME_EVIDENCE_INCONSISTENT"):
            probe.verify_receipt(transcript(value))

    def test_missing_junit_success_rejected(self):
        with self.assertRaisesRegex(probe.ReceiptError, "INSTRUMENTATION_NOT_VERIFIED"):
            probe.verify_receipt(transcript(GOOD, junit_ok=False))

    def test_duplicate_json_rejected(self):
        raw = transcript(GOOD)
        with self.assertRaisesRegex(probe.ReceiptError, "RECEIPT_COUNT_INVALID"):
            probe.verify_receipt(raw + "INSTRUMENTATION_STATUS: rev37_frame_receipt_json={}\n")

    def test_negative_age_rejected(self):
        value = {**GOOD, "target_capture_ms": -1}
        with self.assertRaisesRegex(probe.ReceiptError, "CROSS_FRAME_TIMING_INVALID"):
            probe.verify_receipt(transcript(value))

    def test_nonmonotonic_age_rejected(self):
        value = {**GOOD, "frame_age_at_observation_ms": 480}
        with self.assertRaisesRegex(probe.ReceiptError, "CROSS_FRAME_CLOCK_ORDER_INVALID"):
            probe.verify_receipt(transcript(value))

    def test_unknown_status_rejected(self):
        value = {**BASE, "status": "PASS"}
        with self.assertRaisesRegex(probe.ReceiptError, "RECEIPT_STATUS_UNKNOWN"):
            probe.verify_receipt(transcript(value))

    def test_nonzero_action_attempts_rejected(self):
        value = {**GOOD, "action_attempts": 1}
        with self.assertRaisesRegex(probe.ReceiptError, "NON_AUTHORITATIVE_GUARD_INVALID"):
            probe.verify_receipt(transcript(value))


if __name__ == "__main__":
    unittest.main()
