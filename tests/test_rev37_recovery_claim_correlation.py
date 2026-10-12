"""Unexecuted recovery/Claim correlation regression candidates."""
import unittest
from automation.ui_recovery_inspector import correlate_claim


class RecoveryClaimCorrelationTests(unittest.TestCase):
    def setUp(self):
        self.evidence = {
            "job_id": "job-1", "session_id": "session-1",
            "classification": "TERMINAL_EVIDENCE_PRESENT", "reason_codes": [],
        }
        self.claim = {
            "resource": "android_ui", "claim_id": "claim-1",
            "active_ui_job_id": "job-1", "active_session_id": "session-1",
        }

    def test_matching_claim_does_not_authorize_replay_or_release(self):
        result = correlate_claim(self.evidence, claim=self.claim)
        self.assertEqual(result["classification"], "TERMINAL_EVIDENCE_PRESENT")
        self.assertFalse(result["automatic_replay_allowed"])
        self.assertFalse(result["claim_release_authorized"])

    def test_missing_claim_is_not_positive_stop_proof(self):
        result = correlate_claim(self.evidence, claim=None)
        self.assertIn("CANONICAL_CLAIM_MISSING_OR_RELEASED", result["reason_codes"])
        self.assertFalse(result["mutation_dispatch_allowed"])

    def test_claim_bound_to_other_job_requires_reconcile(self):
        result = correlate_claim(self.evidence, claim={**self.claim, "active_ui_job_id": "job-2"})
        self.assertIn("CANONICAL_CLAIM_JOB_IDENTITY_MISMATCH", result["reason_codes"])

    def test_claim_bound_to_other_session_requires_reconcile(self):
        result = correlate_claim(self.evidence, claim={**self.claim, "active_session_id": "session-2"})
        self.assertIn("CANONICAL_CLAIM_SESSION_IDENTITY_MISMATCH", result["reason_codes"])

    def test_reconcile_claim_remains_blocked(self):
        result = correlate_claim(self.evidence, claim={**self.claim, "reconcile_required": True})
        self.assertIn("CANONICAL_CLAIM_RECONCILE_REQUIRED", result["reason_codes"])
        self.assertEqual(result["classification"], "RECONCILE_REQUIRED")
