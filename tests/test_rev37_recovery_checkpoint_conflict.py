"""Static-only recovery contradiction candidates; intentionally not run."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from automation import ui_recovery_inspector as recovery


class RecoveryCheckpointConflictTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "job-1"
        self.root.mkdir(mode=0o700)
        self.guard = {"resource": "android_ui", "claim_id": "claim-1", "owner_id": "legacy:1"}
        self.write("workflow.json", {"job_id": "job-1", "session_id": "s1",
                                     "resource_guard": self.guard,
                                     "actions": [{"action_id": "a1"}]})
        self.write("state.json", {"status": "RUNNING"})
        self.write("checkpoint.json", {"job_id": "job-1", "session_id": "s1",
                                       "last_completed_action_index": -1})
        self.prepared = {"phase": "MUTATION_PREPARED", "job_id": "job-1",
                         "session_id": "s1", "action_index": 0,
                         "action_id": "a1", "state_epoch": "e1", "revision_before": 1}
        self.committed = {"phase": "MUTATION_COMMITTED", "job_id": "job-1",
                          "session_id": "s1", "action_index": 0,
                          "action_id": "a1", "state_epoch": "e1",
                          "revision_before": 1, "revision_after": 2}

    def write(self, name, data):
        p = self.root / name
        p.write_text(json.dumps(data))
        os.chmod(p, 0o600)

    def journal(self, rows):
        p = self.root / "journal.jsonl"
        p.write_text("".join(json.dumps(row) + "\n" for row in rows))
        os.chmod(p, 0o600)

    def test_checkpoint_crosses_prepared_mutation(self):
        self.write("checkpoint.json", {"job_id": "job-1", "session_id": "s1",
                                       "last_completed_action_index": 0,
                                       "last_completed_action_id": "a1"})
        self.journal([self.prepared])
        report = recovery.inspect_job(self.root, claim=self.guard)
        self.assertIn("CHECKPOINT_CROSSES_UNRESOLVED_MUTATION", report["reason_codes"])
        self.assertFalse(report["automatic_replay_allowed"])

    def test_checkpoint_behind_commit_is_diagnostic(self):
        self.journal([self.prepared, self.committed])
        report = recovery.inspect_job(self.root, claim=self.guard)
        self.assertIn("CHECKPOINT_BEHIND_COMMITTED_MUTATION", report["reason_codes"])
        self.assertFalse(report["claim_release_authorized"])

    def test_claim_bound_to_other_session_fails_closed(self):
        self.journal([self.prepared])
        report = recovery.inspect_job(self.root, claim={**self.guard,
                                                       "active_session_id": "s2"})
        self.assertIn("CANONICAL_CLAIM_IDENTITY_MISMATCH", report["reason_codes"])
