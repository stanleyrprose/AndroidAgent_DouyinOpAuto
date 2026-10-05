from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOSE = ROOT / "scripts" / "close-y700-publication.sh"
START = ROOT / "scripts" / "start-publication-closure.sh"


class PublicationClosureTests(unittest.TestCase):
    def test_closure_has_no_publish_capability(self) -> None:
        text = CLOSE.read_text()
        self.assertIn("reconcile-public-async.sh", text)
        self.assertIn("PUBLISHED_VERIFIED", text)
        self.assertIn("RECONCILE_REQUIRED", text)
        self.assertNotIn("approve-public-commit.sh", text)
        self.assertNotIn("publish-async.sh", text)
        self.assertNotIn("publish_job.py", text)

    def test_published_status_finalizes_and_notifies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            runtime = td / "runtime"
            job = "dy-1"
            (runtime / "jobs" / job).mkdir(parents=True)

            remote = td / "remote.sh"
            remote.write_text('#!/bin/bash\necho \'{"status":"PUBLISHED"}\'\n', encoding="utf-8")
            remote.chmod(0o755)

            pipeline_log = td / "pipeline.log"
            pipeline = td / "pipeline.sh"
            pipeline.write_text(f'#!/bin/bash\nprintf "%s\\n" "$*" >> "{pipeline_log}"\n', encoding="utf-8")
            pipeline.chmod(0o755)

            notify = td / "notify.sh"
            notify.write_text('#!/bin/bash\necho \'{"sent":true,"state":"PUBLISHED_VERIFIED","job_id":"dy-1","reason":null}\'\n', encoding="utf-8")
            notify.chmod(0o755)

            env = os.environ.copy()
            env.update({
                "Y700_PIPE_RUNTIME_ROOT": str(runtime),
                "Y700_REMOTE_RUNNER": str(remote),
                "Y700_PIPELINE_CMD": str(pipeline),
                "Y700_TG_NOTIFY": str(notify),
                "Y700_CLOSE_TIMEOUT_SEC": "5",
                "Y700_CLOSE_POLL_SEC": "0.1",
            })
            p = subprocess.run([str(CLOSE), job], env=env, text=True, capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            closure = json.loads((runtime / "jobs" / job / "telegram-closure.json").read_text())
            self.assertEqual(closure["status"], "PUBLISHED_VERIFIED")
            self.assertTrue(closure["notification"]["sent"])
            self.assertIn("finalize dy-1 --verified", pipeline_log.read_text())

    def test_start_wrapper_is_detached_and_idempotent_by_pid(self) -> None:
        text = START.read_text()
        self.assertIn("nohup bash", text)
        self.assertIn("ALREADY_RUNNING", text)
        self.assertIn("PUBLICATION_CLOSURE", text)


if __name__ == "__main__":
    unittest.main()
