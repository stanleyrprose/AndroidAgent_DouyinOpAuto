"""Source-only regression candidates for PREPARED mutation claim retention.

These tests are intentionally not run during the implementation-only gate.
"""
import unittest
from unittest.mock import patch

from automation import ui_job


class PreparedClaimFenceTests(unittest.TestCase):
    def setUp(self):
        self.guard = {
            "resource": "android_ui",
            "claim_id": "claim-test",
            "owner_id": "legacy:test",
        }
        self.uncertain = {
            "status": "RECONCILE_REQUIRED",
            "job_id": "ui-job",
            "session_id": "ui-session",
            "error": {"code": "POST_DISPATCH_DURABILITY_UNAVAILABLE", "retryable": False},
        }

    def test_prepared_uncertainty_marks_claim_and_sets_retention(self):
        with patch.object(ui_job.resource_arbiter, "mark_reconcile_required") as mark:
            result = ui_job.fence_prepared_reconciliation(
                self.uncertain, mutation_prepared=True, resource_guard=self.guard,
            )
        mark.assert_called_once_with(
            self.guard,
            reason="PREPARED_MUTATION_OUTCOME_OR_DURABILITY_UNCERTAIN",
        )
        self.assertTrue(result["retain_resource_claim"])
        self.assertEqual(result["status"], "RECONCILE_REQUIRED")
        self.assertIs(result["error"]["retryable"], False)

    def test_unprepared_reconciliation_does_not_mark_claim(self):
        with patch.object(ui_job.resource_arbiter, "mark_reconcile_required") as mark:
            result = ui_job.fence_prepared_reconciliation(
                self.uncertain, mutation_prepared=False, resource_guard=None,
            )
        self.assertIs(result, self.uncertain)
        mark.assert_not_called()

    def test_prepared_success_does_not_mark_claim(self):
        passed = {"status": "PASS"}
        with patch.object(ui_job.resource_arbiter, "mark_reconcile_required") as mark:
            result = ui_job.fence_prepared_reconciliation(
                passed, mutation_prepared=True, resource_guard=self.guard,
            )
        self.assertIs(result, passed)
        mark.assert_not_called()

    def test_missing_guard_fails_closed(self):
        with self.assertRaisesRegex(ui_job.UiJobError, "RECONCILE_CLAIM_GUARD_UNAVAILABLE"):
            ui_job.fence_prepared_reconciliation(
                self.uncertain, mutation_prepared=True, resource_guard=None,
            )

    def test_mark_failure_never_publishes_false_retention(self):
        with patch.object(ui_job.resource_arbiter, "mark_reconcile_required",
                          side_effect=OSError("durable claim unavailable")):
            with self.assertRaises(OSError):
                ui_job.fence_prepared_reconciliation(
                    self.uncertain, mutation_prepared=True,
                    resource_guard=self.guard,
                )


if __name__ == "__main__":
    unittest.main()
