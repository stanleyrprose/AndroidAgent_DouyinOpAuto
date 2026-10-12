"""Source-only recovery Claim correlation regression candidates."""
import unittest
from unittest.mock import patch

from automation import ui_job, ui_recovery_inspector


class RecoveryClaimCorrelationTests(unittest.TestCase):
    def setUp(self):
        self.evidence = {
            "job_id": "job-1", "classification": "TERMINAL_EVIDENCE_PRESENT",
            "reason_codes": [], "automatic_replay_allowed": False,
            "claim_release_authorized": False,
            "mutation_dispatch_allowed": False,
        }

    def test_missing_claim_requires_reconciliation(self):
        result = ui_recovery_inspector.correlate_claim(self.evidence, claim=None)
        self.assertEqual(result["classification"], "RECONCILE_REQUIRED")
        self.assertIn("CANONICAL_CLAIM_MISSING_OR_RELEASED", result["reason_codes"])
        self.assertFalse(result["automatic_replay_allowed"])

    def test_claim_reconcile_flag_is_not_silent_success(self):
        claim = {"resource": "android_ui", "claim_id": "claim-1",
                 "reconcile_required": True}
        result = ui_recovery_inspector.correlate_claim(self.evidence, claim=claim)
        self.assertIn("CANONICAL_CLAIM_RECONCILE_REQUIRED", result["reason_codes"])
        self.assertFalse(result["claim_release_authorized"])

    def test_invalid_claim_fails_closed(self):
        result = ui_recovery_inspector.correlate_claim(
            self.evidence, claim={"resource": "other", "claim_id": "claim-1"},
        )
        self.assertIn("CANONICAL_CLAIM_INVALID", result["reason_codes"])

    def test_inspection_calls_actual_inspector_api(self):
        with patch.object(ui_job.ui_recovery_inspector, "inspect_job",
                          return_value=self.evidence) as inspect, \
             patch.object(ui_job.resource_arbiter, "read_claim", return_value=None), \
             patch.object(ui_job, "UI_JOBS") as jobs:
            result = ui_job.inspect_recovery("job-1")
        inspect.assert_called_once()
        self.assertEqual(result["classification"], "RECONCILE_REQUIRED")

    def test_inspector_failure_returns_closed_receipt(self):
        with patch.object(ui_job.ui_recovery_inspector, "inspect_job",
                          side_effect=ui_recovery_inspector.RecoveryEvidenceError("broken")):
            result = ui_job.inspect_recovery("job-1")
        self.assertFalse(result["automatic_replay_allowed"])
        self.assertFalse(result["mutation_dispatch_allowed"])
