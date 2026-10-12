"""Rev3.7 in-memory frame creation -> locator -> live JIT *read-only* tests."""
from __future__ import annotations

import copy
import unittest
from unittest import mock

from automation import visual_receipt, visual_route_gate
from tests.test_rev37_runtime_foundation import CURRENT, FRAME

# This contract is deliberately synthetic and not an approved Y700 route.
FIXTURE_CONTRACT = {
    "route_version": 1,
    "route_id": "fixture.visual.readonly.v1",
    "locator_contract_version": "visual-target.v1",
    "max_frame_age_ms": 600,
    "calibration_evidence_accepted": True,
}
PROOF = {
    "state_epoch": FRAME["state_epoch"],
    "revision": FRAME["revision"],
    "observed_boot_id": FRAME["observed_boot_id"],
}
CAPTURE = {
    "source": "SCREENSHOT",
    "observed_boot_id": FRAME["observed_boot_id"],
    "capture_start_boottime_ms": 1000,
    "capture_end_boottime_ms": 1300,
    "display_id": FRAME["display_id"],
    "rotation": FRAME["rotation"],
    "width": FRAME["width"],
    "height": FRAME["height"],
    "foreground": FRAME["foreground"],
}


class ReadOnlyVisionReceiptTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.captured = copy.deepcopy(CAPTURE)
        self.current = copy.deepcopy(CURRENT)
        self.contract = copy.deepcopy(FIXTURE_CONTRACT)
        self.proof = copy.deepcopy(PROOF)
        self.locator_overrides = {}
        self.now = iter((1400, 1450))

    def capture(self):
        self.events.append("CAPTURE")
        return copy.deepcopy(self.captured)

    def locate(self, frame):
        self.events.append("LOCATE")
        return {
            "frame_id": frame["frame_id"],
            "locator_contract_version": "visual-target.v1",
            "target_identity": "fixture_only_button",
            "bounds": [100, 100, 240, 240],
            "ambiguous": False,
            **self.locator_overrides,
        }

    def observe(self):
        self.events.append("LIVE_STATE")
        return copy.deepcopy(self.current)

    def clock(self):
        self.events.append("CLOCK")
        return next(self.now)

    def run_probe(self):
        return visual_receipt.read_only_frame_locator_receipt(
            contract=self.contract,
            semantic_proof=self.proof,
            capture=self.capture,
            locate=self.locate,
            observe_current=self.observe,
            clock_boottime_ms=self.clock,
        )

    def check_blocked(self, code, *, never_captured=False):
        value = self.run_probe()
        self.assertEqual(value["status"], "BLOCKED")
        self.assertEqual(value["error_code"], code)
        self.assertEqual(value["ui_mutation_attempts"], 0)
        self.assertFalse(value["visual_dispatch_allowed"])
        self.assertIs(value["production_gate_passed"], False)
        if never_captured:
            self.assertEqual(self.events, [])

    def test_valid_exact_bound_receipt_remains_non_authoritative(self):
        value = self.run_probe()
        self.assertEqual(value["status"], "VERIFIED_READ_ONLY")
        self.assertEqual(value["frame_age_at_locator_ms"], 400)
        self.assertEqual(value["frame_age_at_hypothetical_dispatch_ms"], 450)
        self.assertEqual(value["capture_latency_ms"], 300)
        self.assertTrue(value["locator_bound"])
        self.assertIs(value["production_gate_passed"], False)
        self.assertIs(value["visual_dispatch_allowed"], False)
        self.assertEqual(self.events, ["CAPTURE", "LOCATE", "CLOCK", "LIVE_STATE", "CLOCK"])
        self.assertFalse(visual_route_gate.is_visual_mutation_accepted())

    def test_issued_candidate_is_schema_exact_and_anchors_capture_start(self):
        row = visual_receipt.candidate_frame_token(
            self.captured, self.proof, self.contract, frame_id="frame-offline-1"
        )
        self.assertEqual(set(row), set(FRAME))
        self.assertEqual(row["captured_boottime_ms"], 1000)
        self.assertEqual(row["max_age_ms"], 600)
        self.assertEqual(row["frame_id"], "frame-offline-1")
        self.assertEqual(row["state_epoch"], self.proof["state_epoch"])

    def test_wrong_locator_frame_is_blocked_before_live_check(self):
        self.locator_overrides["frame_id"] = "frame-old"
        self.check_blocked("LOCATOR_FRAME_MISMATCH")
        self.assertNotIn("LIVE_STATE", self.events)

    def test_frame_age_exceeded_at_hypothetical_dispatch(self):
        self.now = iter((1400, 1601))
        self.check_blocked("FRAME_STALE")

    def test_revision_advance_invalidates_same_frame(self):
        self.current["revision"] = 43
        self.check_blocked("FRAME_REVISION_STALE")

    def test_rotation_changed_during_locator(self):
        self.current["rotation"] = 2
        self.check_blocked("FRAME_ROTATION_CHANGED")

    def test_foreground_changed_during_locator(self):
        self.current["foreground"] = {"package": "com.other", "activity": "Other"}
        self.check_blocked("FRAME_FOREGROUND_DRIFT")

    def test_boot_or_epoch_mismatch(self):
        self.captured["observed_boot_id"] = "changed-boot"
        self.check_blocked("FRAME_BOOT_MISMATCH")
        self.events.clear()
        self.captured["observed_boot_id"] = self.proof["observed_boot_id"]
        self.current["state_epoch"] = "epoch-modified"
        self.check_blocked("FRAME_STALE")

    def test_screen_or_overlay_blocks(self):
        self.current["keyguard_locked"] = True
        self.check_blocked("FRAME_STALE")
        self.current["keyguard_locked"] = False
        self.current["blocking_overlay_present"] = True
        self.events.clear()
        self.now = iter((1400, 1450))
        self.check_blocked("FRAME_STALE")

    def test_empty_or_inaccurate_locator_fails_closed(self):
        self.locator_overrides["bounds"] = [0, 0, 9000, 240]
        self.check_blocked("LOCATOR_AMBIGUOUS")

    def test_uncalibrated_route_blocks_before_capture(self):
        self.contract["calibration_evidence_accepted"] = False
        self.check_blocked("FRAME_AGE_UNCALIBRATED", never_captured=True)

    def test_caller_cannot_increase_freshness_via_capture(self):
        self.captured["max_age_ms"] = 9000
        self.check_blocked("FRAME_UNAVAILABLE")

    def test_capture_cannot_override_revision_or_epoch(self):
        self.captured["revision"] = 43
        self.check_blocked("FRAME_UNAVAILABLE")

    def test_zero_duration_or_future_capture_blocked(self):
        self.captured["capture_end_boottime_ms"] = 1000
        self.check_blocked("FRAME_UNAVAILABLE")

    def test_unexpected_locator_adapter_failure_is_blocked_without_actions(self):
        def broken_locator(frame):
            raise RuntimeError("unavailable process")
        result = visual_receipt.read_only_frame_locator_receipt(
            contract=self.contract, semantic_proof=self.proof,
            capture=self.capture, locate=broken_locator,
            observe_current=self.observe, clock_boottime_ms=self.clock,
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["error_code"], "FRAME_ADAPTER_FAILED")
        self.assertEqual(result["ui_mutation_attempts"], 0)
        self.assertIs(result["production_gate_passed"], False)
        self.assertNotIn("LIVE_STATE", self.events)

    def test_deployment_gate_always_closed_and_advisory_probe_unavailable_if_active(self):
        with mock.patch.object(visual_route_gate, "is_visual_mutation_accepted", return_value=True):
            self.check_blocked("READ_ONLY_PROBE_NOT_ALLOWED_ON_ACTIVE_RELEASE", never_captured=True)


if __name__ == "__main__":
    unittest.main()
