"""Source-only candidates for canonical recovery inspector evidence ordering."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from automation import ui_recovery_inspector as inspector


class RecoveryOrderingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.job = Path(self.tmp.name) / "job-1"
        self.job.mkdir(mode=0o700)
        self.prepared = dict(phase="MUTATION_PREPARED", job_id="job-1",
                             session_id="session-1", action_index=0,
                             action_id="a1", state_epoch="epoch-1",
                             revision_before=3)
        self.committed = dict(phase="MUTATION_COMMITTED", job_id="job-1",
                              session_id="session-1", action_index=0,
                              action_id="a1", state_epoch="epoch-1",
                              revision_before=3, revision_after=4)
        self.write("workflow.json", dict(job_id="job-1", session_id="session-1",
                                          actions=[dict(action_id="a1")]))
        self.write("checkpoint.json", dict(job_id="job-1", session_id="session-1",
                                            last_completed_action_index=-1))
        self.write("state.json", dict(status="RUNNING"))

    def write(self, name, data):
        p = self.job / name
        p.write_text(json.dumps(data))
        os.chmod(p, 0o600)

    def journal(self, rows):
        p = self.job / "journal.jsonl"
        p.write_text("".join(json.dumps(x) + "\n" for x in rows))
        os.chmod(p, 0o600)

    def test_ordered_prepare_commit_remains_non_replayable(self):
        self.journal([self.prepared, self.committed])
        report = inspector.inspect_job(self.job)
        self.assertEqual(report["classification"], "RECONCILE_REQUIRED")
        self.assertFalse(report["automatic_replay_allowed"])

    def test_commit_before_prepare_is_rejected(self):
        self.journal([self.committed, self.prepared])
        with self.assertRaisesRegex(inspector.RecoveryEvidenceError,
                                    "RECOVERY_COMMIT_WITHOUT_PREPARE"):
            inspector.inspect_job(self.job)

    def test_duplicate_prepare_is_rejected(self):
        self.journal([self.prepared, self.prepared])
        with self.assertRaisesRegex(inspector.RecoveryEvidenceError,
                                    "RECOVERY_PREPARED_SEQUENCE_INVALID"):
            inspector.inspect_job(self.job)

    def test_wrong_revision_after_is_rejected(self):
        self.journal([self.prepared, {**self.committed, "revision_after": 8}])
        with self.assertRaisesRegex(inspector.RecoveryEvidenceError,
                                    "RECOVERY_COMMIT_AUTHORITY_MISMATCH"):
            inspector.inspect_job(self.job)

    def test_wrong_action_identity_is_rejected(self):
        self.journal([{**self.prepared, "action_id": "other"}])
        with self.assertRaisesRegex(inspector.RecoveryEvidenceError,
                                    "RECOVERY_MUTATION_ACTION_MISMATCH"):
            inspector.inspect_job(self.job)

    def test_duplicate_json_key_is_rejected(self):
        p = self.job / "journal.jsonl"
        p.write_text('{"phase":"SESSION_START","phase":"MUTATION_PREPARED"}\n')
        os.chmod(p, 0o600)
        with self.assertRaisesRegex(inspector.RecoveryEvidenceError,
                                    "RECOVERY_JOURNAL_INVALID"):
            inspector.inspect_job(self.job)
