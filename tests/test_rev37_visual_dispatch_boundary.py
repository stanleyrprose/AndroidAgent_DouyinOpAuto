"""Rev3.7 Sprint 1A mutation dispatch safety boundary tests (no real UI)."""
from __future__ import annotations

import copy
import unittest
from unittest import mock

from automation import ui_core_v2 as core
from tests.test_rev37_runtime_foundation import CURRENT, FRAME, LOCATOR

PROOF = {
    "state_epoch": "epoch-1",
    "revision": 42,
    "observed_boot_id": "boot-abc",
    "fingerprint_version": "semantic-v1",
    "fingerprint_profile_id": "semantic-v1.foreground-base.v1",
    "state_hash": "test-state-hash",
}
GUARD = {"resource": "android_ui", "claim_id": "claim-test", "owner_id": "legacy:test"}
ACTION = {
    "action_id": "tap-1",
    "action": "click",
    "side_effect": "REVERSIBLE_LOCAL",
    "selector": {
        "text": "Close",
        "fallback": [{"type": "vision_template", "template": "common/close.png"}],
    },
}


class VisualDispatchBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.actions = []
        self.req = {
            "protocol_version": 2,
            "job_id": "visual-dispatch-gate",
            "session_id": "test-session",
            "resource_guard": GUARD,
            "state_guard": {"mode": "AUTO"},
            "actions": [copy.deepcopy(ACTION)],
        }

    @staticmethod
    def trusted_evidence(action, proof):
        return {
            "dg3_accepted": True,
            "route_id": "ui.vision-assisted.v1",
            "frame": copy.deepcopy(FRAME),
            "locator": copy.deepcopy(LOCATOR),
            "current": copy.deepcopy(CURRENT),
            "state_token_revision": 42,
            "route_max_frame_age_ms": 1200,
            "now_boottime_ms": 1500,
            "locator_contract_version": "visual-target.v1",
            "capture_latency_ms": 100,
            "locator_latency_ms": 75,
            "frame_age_at_locator_ms": 300,
            "recapture_count": 0,
        }

    def fake_driver(self, actions, label):
        self.actions.extend(actions)
        self.events.append("DRIVER_DISPATCH")
        return {"status": "PASS", "actions": [{
            "status": "PASS", "action_id": actions[0].get("action_id"),
            "action": actions[0]["action"],
            "data": {"postcondition_passed": True, "postcondition_kind": "ACK"},
        }]}

    def run_core(self, provider=None):
        def journal(row):
            self.events.append(row["phase"])
        with (
            mock.patch.object(core.resource_arbiter, "assert_guard", return_value={
                "claim_id": GUARD["claim_id"], "claim_generation": 1
            }),
            mock.patch.object(core, "validate_state_guard", return_value=PROOF),
            mock.patch.object(core.state_integrity, "advance_revision", return_value=(42, 43)),
        ):
            return core.run(
                self.req,
                driver_run=self.fake_driver,
                activity_read=lambda _: "com.example/.Main",
                journal_append=journal,
                checkpoint_write=lambda index, safe: None,
                cancel_check=lambda: False,
                now_iso=lambda: "2026-10-08T00:00:00+00:00",
                visual_evidence_provider=provider,
            )

    def check_blocked(self, expected, provider=None):
        result = self.run_core(provider)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["error"]["code"], expected)
        self.assertEqual(result["action_attempts"], 0)
        self.assertEqual(self.actions, [])
        self.assertNotIn("MUTATION_PREPARED", self.events)
        self.assertNotIn("DRIVER_DISPATCH", self.events)
        self.assertIn("VISUAL_DISPATCH_BLOCKED", self.events)

    def test_default_no_provider_blocks_vision_fallback_even_with_caller_claim(self):
        self.req["actions"][0]["frame_guard"] = self.trusted_evidence(ACTION, PROOF)
        self.req["actions"][0]["dg3_accepted"] = True
        self.check_blocked("VISION_ROUTE_GATE_CLOSED")

    def test_direct_visual_selector_also_blocks(self):
        self.req["actions"][0]["selector"] = {
            "type": "vision_text", "pattern": "Close"
        }
        self.check_blocked("VISION_ROUTE_GATE_CLOSED")

    def test_route_flag_without_locator_also_blocks(self):
        self.req["actions"][0]["selector"] = {"text": "Close"}
        self.req["actions"][0]["route_class"] = "VISION_ASSISTED_UI"
        self.check_blocked("VISION_ROUTE_GATE_CLOSED")

    def test_visual_popup_recovery_has_no_semantic_bypass(self):
        self.req["actions"][0]["selector"] = {"text": "Close"}
        self.req["actions"][0]["vision_recovery"] = {
            "known_popups": [{"expected_package": "com.example",
                              "template": {"type": "vision_template", "template": "popup.png"}}]
        }
        self.check_blocked("VISION_ROUTE_GATE_CLOSED")

    def test_visual_popup_recovery_empty_still_fails_closed(self):
        self.req["actions"][0]["selector"] = {"text": "Close"}
        self.req["actions"][0]["vision_recovery"] = {}
        self.check_blocked("VISION_ROUTE_GATE_CLOSED")

    def test_stale_frame_no_prepared_and_zero_attempt(self):
        def stale(action, proof):
            return {**self.trusted_evidence(action, proof), "now_boottime_ms": 2300}
        self.check_blocked("FRAME_STALE", provider=stale)

    def test_rotation_drift_no_prepared_and_zero_attempt(self):
        def rotation(action, proof):
            value = self.trusted_evidence(action, proof)
            value["current"]["rotation"] = 2
            return value
        self.check_blocked("FRAME_ROTATION_CHANGED", provider=rotation)

    def test_locator_from_another_frame_no_prepared(self):
        def old_locator(action, proof):
            value = self.trusted_evidence(action, proof)
            value["locator"]["frame_id"] = "frame-from-old-screenshot"
            return value
        self.check_blocked("LOCATOR_FRAME_MISMATCH", provider=old_locator)

    def test_revision_changed_since_semantic_guard_blocks(self):
        def stale_revision(action, proof):
            value = self.trusted_evidence(action, proof)
            value["current"]["revision"] = 43
            return value
        self.check_blocked("FRAME_REVISION_STALE", provider=stale_revision)

    def test_high_risk_visual_action_is_denied_even_with_provider(self):
        self.req["actions"][0]["side_effect"] = "EXTERNAL_IRREVERSIBLE"
        self.check_blocked("VISION_IRREVERSIBLE_DENIED", provider=self.trusted_evidence)

    def test_proof_boot_drift_blocks_before_any_attempt(self):
        def stale_boot(action, proof):
            value = self.trusted_evidence(action, proof)
            value["frame"]["observed_boot_id"] = "boot-other"
            value["current"]["boot_id"] = "boot-other"
            return value
        self.check_blocked("FRAME_BOOT_MISMATCH", provider=stale_boot)

    def test_proof_epoch_drift_blocks_before_any_attempt(self):
        def stale_epoch(action, proof):
            value = self.trusted_evidence(action, proof)
            value["frame"]["state_epoch"] = "epoch-other"
            value["current"]["state_epoch"] = "epoch-other"
            return value
        self.check_blocked("FRAME_STALE", provider=stale_epoch)

    def test_provider_dg3_gate_cannot_be_set_by_workflow(self):
        def disabled(action, proof):
            value = self.trusted_evidence(action, proof)
            value["dg3_accepted"] = False
            return value
        self.req["dg3_accepted"] = True
        self.check_blocked("VISION_ROUTE_GATE_CLOSED", provider=disabled)

    def test_trusted_fresh_evidence_runs_only_after_journal_and_guard(self):
        result = self.run_core(self.trusted_evidence)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(self.actions), 1)
        self.assertLess(self.events.index("FRAME_FRESHNESS_VERIFIED"),
                        self.events.index("MUTATION_PREPARED"))
        self.assertLess(self.events.index("MUTATION_PREPARED"),
                        self.events.index("DRIVER_DISPATCH"))

    def test_plain_semantic_action_is_unaffected_by_visual_gate(self):
        self.req["actions"][0]["selector"] = {"text": "Close"}
        result = self.run_core()
        self.assertEqual(result["status"], "PASS")
        self.assertNotIn("FRAME_FRESHNESS_VERIFIED", self.events)
        self.assertEqual(len(self.actions), 1)

    def test_proof_revision_must_match_evidence(self):
        def stale_proof(action, proof):
            value = self.trusted_evidence(action, proof)
            value["state_token_revision"] = 41
            return value
        self.check_blocked("FRAME_REVISION_STALE", provider=stale_proof)


if __name__ == "__main__":
    unittest.main()
