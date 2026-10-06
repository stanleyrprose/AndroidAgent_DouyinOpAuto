from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from publisher import publish_job

ROOT = Path(__file__).resolve().parents[1]
RESTORE = ROOT / "scripts" / "restore-initial-power-state.sh"


class CaptureInitialPowerStateTests(unittest.TestCase):
    def test_asleep_is_captured_once_before_unlock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job-1"
            job.mkdir()
            result = subprocess.CompletedProcess(["androidctl"], 0, "  mWakefulness=Asleep\n", "")
            with mock.patch.object(publish_job, "run", return_value=result) as runner:
                first = publish_job.capture_initial_power_state(job, "job-1")
            self.assertEqual(first["initial_power_state"], "ASLEEP")
            self.assertTrue(first["restore_required"])
            runner.assert_called_once()
            with mock.patch.object(publish_job, "run", side_effect=AssertionError("must reuse marker")):
                second = publish_job.capture_initial_power_state(job, "job-1")
            self.assertEqual(second["captured_at"], first["captured_at"])

    def test_awake_does_not_require_restore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job-1"
            job.mkdir()
            result = subprocess.CompletedProcess(["androidctl"], 0, "mWakefulness=Awake\n", "")
            with mock.patch.object(publish_job, "run", return_value=result):
                data = publish_job.capture_initial_power_state(job, "job-1")
            self.assertEqual(data["initial_power_state"], "AWAKE")
            self.assertFalse(data["restore_required"])


class RestoreInitialPowerStateScriptTests(unittest.TestCase):
    def _env(self, td: Path) -> tuple[dict[str, str], Path, Path, Path]:
        ready = td / "ready"
        published = td / "published"
        runs = td / "runs"
        state = td / "publisher.json"
        for path in (ready, published, runs):
            path.mkdir(parents=True, exist_ok=True)
        log = td / "root-exec.log"
        root_exec = td / "root-exec.sh"
        root_exec.write_text(f'#!/bin/bash\nprintf "%s\\n" "$*" >> "{log}"\n', encoding="utf-8")
        root_exec.chmod(0o755)
        env = os.environ.copy()
        env.update({
            "Y700_READY_ROOT": str(ready),
            "Y700_PUBLISHED_ROOT": str(published),
            "Y700_PUBLISH_RUN_ROOT": str(runs),
            "Y700_PUBLISH_STATE": str(state),
            "Y700_ROOT_EXEC": str(root_exec),
        })
        return env, state, log, published

    def _seed(self, published: Path, state: Path, initial: str = "ASLEEP") -> Path:
        job = published / "job-1"
        job.mkdir(parents=True)
        marker = job / "initial-power-state.json"
        marker.write_text(json.dumps({
            "schema_version": 1,
            "job_id": "job-1",
            "initial_power_state": initial,
            "restore_required": initial == "ASLEEP",
        }), encoding="utf-8")
        state.write_text(json.dumps({"job_id": "job-1", "status": "PUBLISHED"}), encoding="utf-8")
        return marker

    def test_asleep_is_restored_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env, state, log, published = self._env(Path(tmp))
            marker = self._seed(published, state, "ASLEEP")
            p = subprocess.run([str(RESTORE), "job-1"], env=env, text=True, capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("RESTORED_ASLEEP", p.stdout)
            self.assertIn("KEYCODE_SLEEP", log.read_text())
            data = json.loads(marker.read_text())
            self.assertEqual(data["restore_action"], "KEYCODE_SLEEP")
            before = log.read_text()
            p2 = subprocess.run([str(RESTORE), "job-1"], env=env, text=True, capture_output=True)
            self.assertEqual(p2.returncode, 0)
            self.assertIn("ALREADY_RESTORED", p2.stdout)
            self.assertEqual(log.read_text(), before)

    def test_awake_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env, state, log, published = self._env(Path(tmp))
            self._seed(published, state, "AWAKE")
            p = subprocess.run([str(RESTORE), "job-1"], env=env, text=True, capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("RESTORE_NOT_REQUIRED", p.stdout)
            self.assertFalse(log.exists())

    def test_live_other_publisher_defers_sleep(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env, state, log, published = self._env(Path(tmp))
            self._seed(published, state, "ASLEEP")
            other = Path(env["Y700_PUBLISH_RUN_ROOT"]) / "job-2"
            other.mkdir()
            (other / "pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
            p = subprocess.run([str(RESTORE), "job-1"], env=env, text=True, capture_output=True)
            self.assertEqual(p.returncode, 5)
            self.assertIn("RESTORE_DEFERRED_PUBLISHER_RUNNING", p.stdout)
            self.assertFalse(log.exists())


if __name__ == "__main__":
    unittest.main()
