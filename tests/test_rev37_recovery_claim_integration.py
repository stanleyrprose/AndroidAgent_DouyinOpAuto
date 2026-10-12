"""Unexecuted recovery-inspector/Claim integration regression candidates."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from automation import ui_job, ui_recovery_inspector


class RecoveryClaimIntegrationTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.job = Path(tmp.name) / "job-1"
        self.job.mkdir(mode=0o700)
        self.guard = {"resource": "android_ui", "claim_id": "claim-1", "owner_id": "legacy:1"}
        self.write("workflow.json", {"job_id": "job-1", "session_id": "session-1",
                                     "resource_guard": self.guard,
                                     "actions": [{"action_id": "a1"}]})
        self.write("state.json", {"status": "RUNNING"})
        self.write("checkpoint.json", {"job_id": "job-1", "session_id": "session-1",
                                       "last_completed_action_index": -1})
        row = {"phase": "MUTATION_PREPARED", "job_id": "job-1",
               "session_id": "session-1", "action_index": 0,
               "action_id": "a1", "revision_before": 1, "state_epoch": "epoch-1"}
        path = self.job / "journal.jsonl"
        path.write_text(json.dumps(row) + "\n")
        os.chmod(path, 0o600)

    def write(self, name, value):
        path = self.job / name
        path.write_text(json.dumps(value))
        os.chmod(path, 0o600)

    def test_matching_claim_still_does_not_authorize_replay(self):
        report = ui_recovery_inspector.inspect_job(self.job, claim=self.guard)
        self.assertEqual(report["classification"], "RECONCILE_REQUIRED")
        self.assertFalse(report["automatic_replay_allowed"])
        self.assertFalse(report["claim_release_authorized"])

    def test_missing_claim_is_not_free_resource(self):
        report = ui_recovery_inspector.inspect_job(self.job, claim=None)
        self.assertIn("CANONICAL_CLAIM_UNVERIFIED", report["reason_codes"])

    def test_different_claim_is_not_equivalent(self):
        report = ui_recovery_inspector.inspect_job(
            self.job, claim={**self.guard, "claim_id": "claim-2"})
        self.assertIn("CANONICAL_CLAIM_IDENTITY_MISMATCH", report["reason_codes"])

    def test_reconcile_mark_is_reported(self):
        report = ui_recovery_inspector.inspect_job(
            self.job, claim={**self.guard, "reconcile_required": True})
        self.assertIn("CANONICAL_CLAIM_RECONCILE_REQUIRED", report["reason_codes"])

    def test_cli_inspection_uses_actual_inspector_and_claim(self):
        with patch.object(ui_job, "UI_JOBS", self.job.parent), patch.object(
                ui_job.resource_arbiter, "read_claim", return_value=self.guard):
            report = ui_job.inspect_recovery("job-1")
        self.assertEqual(report["classification"], "RECONCILE_REQUIRED")
        self.assertEqual(report["unresolved_action_indices"], [0])

    def test_corrupt_claim_returns_non_replayable_diagnostic(self):
        with patch.object(ui_job, "UI_JOBS", self.job.parent), patch.object(
                ui_job.resource_arbiter, "read_claim",
                side_effect=ui_job.resource_arbiter.ResourceError("claim corrupt")):
            report = ui_job.inspect_recovery("job-1")
        self.assertEqual(report["classification"], "RECONCILE_REQUIRED")
        self.assertFalse(report["automatic_replay_allowed"])
