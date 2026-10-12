"""Source-only regression candidates; not run during implementation gate."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from automation.ui_recovery_inspector_v37 import (
    inspect_ui_job, RecoveryEvidenceUnavailable,
)


class RecoveryInspectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "job-1"
        self.root.mkdir(mode=0o700)
        self.workflow = {
            "job_id": "job-1", "session_id": "session-1",
            "actions": [{"action_id": "a1", "action": "pressHome"}],
        }
        self.checkpoint = {
            "job_id": "job-1", "session_id": "session-1",
            "last_completed_action_index": -1, "last_completed_action_id": None,
            "safe_to_resume": True,
        }
        self.prepared = {
            "phase": "MUTATION_PREPARED", "job_id": "job-1",
            "session_id": "session-1", "action_index": 0, "action_id": "a1",
            "state_epoch": "epoch-" + "a" * 32, "revision_before": 3,
        }
        self.write("workflow.json", self.workflow)
        self.write("checkpoint.json", self.checkpoint)
        self.journal([{"phase": "SESSION_START"}])

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value))
        os.chmod(path, 0o600)

    def journal(self, rows):
        path = self.root / "journal.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        os.chmod(path, 0o600)

    def test_missing_result_never_authorizes_replay(self):
        outcome = inspect_ui_job(self.root)
        self.assertIn("RESULT_MISSING", outcome["reason_codes"])
        self.assertFalse(outcome["safe_to_resume"])
        self.assertFalse(outcome["replay_allowed"])

    def test_prepared_without_commit_is_unresolved(self):
        self.journal([{"phase": "SESSION_START"}, self.prepared])
        outcome = inspect_ui_job(self.root)
        self.assertEqual(outcome["unresolved_action_indices"], [0])
        self.assertIn("PREPARED_MUTATION_UNRESOLVED", outcome["reason_codes"])

    def test_committed_journal_does_not_authorize_replay(self):
        commit = {
            "phase": "MUTATION_COMMITTED", "job_id": "job-1",
            "session_id": "session-1", "action_index": 0,
            "action_id": "a1", "state_epoch": self.prepared["state_epoch"],
            "revision_before": 3, "revision_after": 4,
        }
        self.journal([self.prepared, commit])
        outcome = inspect_ui_job(self.root)
        self.assertEqual(outcome["committed_action_indices"], [0])
        self.assertEqual(outcome["unresolved_action_indices"], [])
        self.assertFalse(outcome["replay_allowed"])

    def test_corrupt_tail_fails_closed(self):
        (self.root / "journal.jsonl").write_bytes(b'{"phase":"SESSION_START"}')
        with self.assertRaises(RecoveryEvidenceUnavailable):
            inspect_ui_job(self.root)

    def test_symlinked_journal_rejected(self):
        journal = self.root / "journal.jsonl"
        journal.unlink()
        journal.symlink_to(self.root / "workflow.json")
        with self.assertRaises((RecoveryEvidenceUnavailable, OSError)):
            inspect_ui_job(self.root)

    def test_commit_revision_mismatch_rejected(self):
        self.journal([self.prepared, {
            "phase": "MUTATION_COMMITTED", "job_id": "job-1",
            "session_id": "session-1", "action_index": 0,
            "action_id": "a1", "state_epoch": self.prepared["state_epoch"],
            "revision_before": 3, "revision_after": 7,
        }])
        with self.assertRaisesRegex(RecoveryEvidenceUnavailable, "RECOVERY_COMMIT_AUTHORITY_MISMATCH"):
            inspect_ui_job(self.root)

    def test_checkpoint_identity_mismatch_rejected(self):
        self.checkpoint["session_id"] = "other-session"
        self.write("checkpoint.json", self.checkpoint)
        with self.assertRaisesRegex(RecoveryEvidenceUnavailable, "RECOVERY_CHECKPOINT_IDENTITY_MISMATCH"):
            inspect_ui_job(self.root)


if __name__ == "__main__":
    unittest.main()
