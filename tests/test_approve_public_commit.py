from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "approve-public-commit.sh"


class ApprovePublicCommitTests(unittest.TestCase):
    def _env(self, td: Path) -> dict[str, str]:
        ready = td / "ready"
        published = td / "published"
        runs = td / "runs"
        state = td / "publisher.json"
        for p in (ready, published, runs):
            p.mkdir(parents=True, exist_ok=True)
        fake = td / "publish-async.sh"
        fake.write_text('#!/bin/bash\nprintf \'{"status":"STARTED","job_id":"%s","commit":true}\\n\' "$1"\n', encoding="utf-8")
        fake.chmod(0o755)
        env = os.environ.copy()
        env.update({
            "Y700_READY_ROOT": str(ready),
            "Y700_PUBLISHED_ROOT": str(published),
            "Y700_PUBLISH_RUN_ROOT": str(runs),
            "Y700_PUBLISH_STATE": str(state),
            "Y700_PUBLISH_ASYNC": str(fake),
        })
        return env

    def _seed(self, env: dict[str, str], job: str = "dy-1", *, mode: str = "DRY_RUN", state_status: str = "READY_TO_COMMIT") -> Path:
        ready = Path(env["Y700_READY_ROOT"]) / job
        ready.mkdir(parents=True)
        manifest = ready / "manifest.json"
        manifest.write_text(json.dumps({"job_id": job, "publish_mode": mode, "visibility": "PUBLIC"}), encoding="utf-8")
        Path(env["Y700_PUBLISH_STATE"]).write_text(json.dumps({"job_id": job, "status": state_status, "visibility": "PUBLIC"}), encoding="utf-8")
        return manifest

    def test_ready_dry_run_is_atomically_armed_then_started(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = self._env(Path(tmp))
            manifest = self._seed(env)
            p = subprocess.run([str(SCRIPT), "dy-1", "telegram standing authorization"], env=env, text=True, capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(manifest.read_text())["publish_mode"], "COMMIT")
            approval = json.loads((Path(env["Y700_PUBLISH_RUN_ROOT"]) / "dy-1" / "approval.json").read_text())
            self.assertEqual(approval["scope"], "one_commit_attempt")
            self.assertIn('"commit":true', p.stdout)

    def test_wrong_state_fails_without_arming(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = self._env(Path(tmp))
            manifest = self._seed(env, state_status="NAVIGATING")
            p = subprocess.run([str(SCRIPT), "dy-1"], env=env, text=True, capture_output=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual(json.loads(manifest.read_text())["publish_mode"], "DRY_RUN")

    def test_already_commit_refuses_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = self._env(Path(tmp))
            manifest = self._seed(env, mode="COMMIT")
            p = subprocess.run([str(SCRIPT), "dy-1"], env=env, text=True, capture_output=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("reconcile before any retry", p.stderr)
            self.assertEqual(json.loads(manifest.read_text())["publish_mode"], "COMMIT")

    def test_stale_lock_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = self._env(Path(tmp))
            self._seed(env)
            lock = Path(env["Y700_PUBLISH_RUN_ROOT"]) / "dy-1" / "commit-transition.lock"
            lock.mkdir(parents=True)
            (lock / "pid").write_text("999999\n")
            p = subprocess.run([str(SCRIPT), "dy-1"], env=env, text=True, capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == "__main__":
    unittest.main()
