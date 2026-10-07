from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from pipeline.state import set_workflow_intent

ROOT = Path(__file__).resolve().parents[1]
RESUME = ROOT / "scripts" / "resume-job.sh"
START = ROOT / "scripts" / "start-resume-job.sh"


class FakeJob:
    def __init__(self, state: dict):
        self._state = dict(state)
        self.job_id = state.get("job_id", "dy-1")
        self.events: list[tuple[str, dict]] = []

    def state(self):
        return dict(self._state)

    def write_state(self, state: str, **extra):
        self._state.update(extra)
        self._state["state"] = state
        return dict(self._state)

    def event(self, kind: str, **data):
        self.events.append((kind, data))


class WorkflowIntentTests(unittest.TestCase):
    def test_intent_is_write_once_and_idempotent(self) -> None:
        job = FakeJob({"job_id": "dy-1", "state": "EXPORTED"})
        first = set_workflow_intent(job, "STORE_ALBUM")
        self.assertEqual(first["workflow_intent"], "STORE_ALBUM")
        second = set_workflow_intent(job, "STORE_ALBUM")
        self.assertEqual(second["workflow_intent"], "STORE_ALBUM")
        with self.assertRaisesRegex(RuntimeError, "workflow intent is immutable"):
            set_workflow_intent(job, "AUTO_PUBLISH")

    def test_missing_intent_is_not_backfilled_after_terminal(self) -> None:
        job = FakeJob({"job_id": "dy-1", "state": "VERIFIED"})
        with self.assertRaisesRegex(RuntimeError, "cannot backfill"):
            set_workflow_intent(job, "AUTO_PUBLISH")


class ResumeScriptTests(unittest.TestCase):
    def _base(self, td: Path, *, state: str, intent: str | None, expires: int = 9999999999):
        runtime = td / "runtime"
        job = "dy-1"
        job_dir = runtime / "jobs" / job
        (job_dir / "export").mkdir(parents=True)
        data = {"job_id": job, "state": state}
        if intent:
            data["workflow_intent"] = intent
        (job_dir / "state.json").write_text(json.dumps(data), encoding="utf-8")
        (job_dir / "export" / "handoff.json").write_text(json.dumps({
            "job_id": job,
            "manifest_url": "https://example.invalid/cap/secret/manifest.json",
            "expires_at": expires,
        }), encoding="utf-8")

        log = td / "calls.log"
        notify = td / "notify.sh"
        notify.write_text(f'#!/bin/bash\nprintf "notify %s\\n" "$*" >> "{log}"\necho \'{{"sent":true}}\'\n', encoding="utf-8")
        notify.chmod(0o755)
        closure = td / "closure.sh"
        closure.write_text(f'#!/bin/bash\nprintf "closure %s\\n" "$*" >> "{log}"\necho \'{{"status":"STARTED"}}\'\n', encoding="utf-8")
        closure.chmod(0o755)
        album = td / "album.sh"
        album.write_text(f'#!/bin/bash\nprintf "album %s\\n" "$*" >> "{log}"\necho \'{{"status":"STORED_IN_ALBUM"}}\'\n', encoding="utf-8")
        album.chmod(0o755)
        pipeline = td / "pipeline.sh"
        pipeline.write_text(
            f'''#!/bin/bash\nprintf "pipeline %s\\n" "$*" >> "{log}"\nif [ "$1" = export ]; then\n  python3 - "$Y700_PIPE_RUNTIME_ROOT/jobs/$2/export/handoff.json" <<'PY2'\nimport json,sys\np=sys.argv[1]\nd=json.load(open(p))\nd['expires_at']=9999999999\nopen(p,'w').write(json.dumps(d))\nPY2\nfi\nexit 0\n''',
            encoding="utf-8",
        )
        pipeline.chmod(0o755)
        env = os.environ.copy()
        env.update({
            "Y700_PIPE_RUNTIME_ROOT": str(runtime),
            "Y700_PIPELINE_CMD": str(pipeline),
            "Y700_ALBUM_STORE_CMD": str(album),
            "Y700_CLOSURE_START_CMD": str(closure),
            "Y700_TG_NOTIFY": str(notify),
            "Y700_RESUME_NOW_EPOCH": "1000",
            "Y700_RESUME_POLL_SEC": "0.01",
            "Y700_RESUME_TIMEOUT_SEC": "1",
        })
        return job, env, log

    def test_missing_intent_blocks_without_remote_or_album(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job, env, log = self._base(Path(tmp), state="EXPORTED", intent=None)
            p = subprocess.run([str(RESUME), job], env=env, text=True, capture_output=True)
            self.assertEqual(p.returncode, 6)
            self.assertIn("RESUME_BLOCKED", p.stdout)
            calls = log.read_text()
            self.assertNotIn("album ", calls)
            self.assertNotIn("closure ", calls)

    def test_album_resume_refreshes_only_expired_export_then_stores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job, env, log = self._base(Path(tmp), state="EXPORTED", intent="STORE_ALBUM", expires=900)
            p = subprocess.run([str(RESUME), job], env=env, text=True, capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            calls = log.read_text()
            self.assertIn("pipeline export dy-1", calls)
            self.assertIn("album dy-1 Y700Agent", calls)
            self.assertNotIn("closure ", calls)

    def test_auto_publish_commit_manifest_never_replays_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            job, env, log = self._base(td, state="APPROVED", intent="AUTO_PUBLISH")
            remote = td / "remote.sh"
            remote.write_text(
                f'''#!/bin/bash\nprintf "remote %s\\n" "$*" >> "{log}"\ncase "$*" in\n  *publish-status.sh*) echo '{{"status":"AMBIGUOUS_COMMIT_NEEDS_RECONCILE","publish_mode":"COMMIT","ready":true,"published":false}}' ;;\n  *approve-public-commit.sh*) echo SHOULD_NOT_RUN; exit 99 ;;\nesac\n''',
                encoding="utf-8",
            )
            remote.chmod(0o755)
            env["Y700_REMOTE_RUNNER"] = str(remote)
            p = subprocess.run([str(RESUME), job], env=env, text=True, capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("RECONCILE_REQUIRED", p.stdout)
            calls = log.read_text()
            self.assertIn("closure dy-1", calls)
            self.assertNotIn("approve-public-commit.sh", calls)

    def test_approved_job_cannot_reexport_when_remote_ready_is_lost(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            job, env, log = self._base(td, state="APPROVED", intent="AUTO_PUBLISH", expires=900)
            remote = td / "remote.sh"
            remote.write_text(
                f'''#!/bin/bash\nprintf "remote %s\\n" "$*" >> "{log}"\nif [[ "$*" == *publish-status.sh* ]]; then\n  echo '{{"status":"IDLE","publish_mode":null,"ready":false,"published":false}}'\n  exit 0\nfi\n''',
                encoding="utf-8",
            )
            remote.chmod(0o755)
            env["Y700_REMOTE_RUNNER"] = str(remote)
            p = subprocess.run([str(RESUME), job], env=env, text=True, capture_output=True)
            self.assertEqual(p.returncode, 6)
            self.assertIn("RESUME_BLOCKED", p.stdout)
            self.assertNotIn("pipeline export", log.read_text())


    def test_y700_control_avoids_hermes_slash_namespace(self) -> None:
        soul = (ROOT.parent.parent / "config" / "hermes-y700automation-SOUL.md").read_text(encoding="utf-8")
        self.assertIn("继续任务<sep><job_id>", soul)
        self.assertIn("任务状态<sep><job_id>", soul)
        self.assertIn("取消任务<sep><job_id>", soul)
        self.assertIn("Automatic Publish<sep><Douyin share text or URL>", soul)
        self.assertIn("Save to Album<sep><Douyin share text or URL>", soul)
        self.assertIn("Resume Task<sep><job_id>", soul)
        self.assertIn("Task Status<sep><job_id>", soul)
        self.assertIn("Cancel Task<sep><job_id>", soul)
        self.assertIn("ASCII case-insensitive", soul)
        self.assertIn("`帮助` or `Help`", soul)
        self.assertIn("Slash commands belong to Hermes itself", soul)
        self.assertNotIn("`/resume <job_id>`", soul)
        self.assertNotIn("`/status [job_id]`", soul)
        self.assertNotIn("`/cancel <job_id>`", soul)

    def test_starter_is_detached_and_pid_idempotent(self) -> None:
        text = START.read_text()
        self.assertIn("nohup bash", text)
        self.assertIn("ALREADY_RUNNING", text)
        self.assertIn("RESUME_STARTED", text)


if __name__ == "__main__":
    unittest.main()
