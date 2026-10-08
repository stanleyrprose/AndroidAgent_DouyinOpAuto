from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "publisher" / "store_direct_download.py"
COMPLETE = ROOT / "mac" / "production-pipeline" / "scripts" / "complete-direct-download.sh"
ENTRY = ROOT / "mac" / "production-pipeline" / "scripts" / "direct-download-to-y700.sh"
SOUL = ROOT / "config" / "hermes-y700automation-SOUL.md"


class DirectDownloadContractTests(unittest.TestCase):
    def test_control_contract_is_video_only(self) -> None:
        soul = SOUL.read_text(encoding="utf-8")
        self.assertIn("直接下载<sep><Douyin share text or URL>", soul)
        self.assertIn("Direct Download<sep><Douyin share text or URL>", soul)
        self.assertIn("DIRECT_DOWNLOAD", soul)
        self.assertIn("direct-download-to-y700.sh", soul)

        entry = ENTRY.read_text(encoding="utf-8")
        complete = COMPLETE.read_text(encoding="utf-8")
        store = STORE.read_text(encoding="utf-8")
        joined = "\n".join([entry, complete, store])
        self.assertIn("pull-artifact-bundle.py", complete)
        self.assertIn("original.mp4", joined)
        self.assertIn("DIRECT_DOWNLOADED", joined)
        self.assertNotIn("approve-public-commit.sh", joined)
        self.assertNotIn("publish-async.sh", joined)
        self.assertNotIn("com.zui.notes", joined)
        self.assertNotIn("caption.my.txt", joined)
        self.assertNotIn("apps.tiktok", joined)

    def test_y700_direct_store_verifies_media_and_restores_asleep(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            job_id = "dd-1234567890123456789"
            pull = td / "pull"
            bundle = pull / job_id
            bundle.mkdir(parents=True)
            (bundle / ".complete").write_text("verified\n", encoding="utf-8")
            (bundle / "manifest.json").write_text(json.dumps({
                "schema_version": 1,
                "job_id": job_id,
                "kind": "generic-artifact",
                "expires_at": 9999999999,
                "artifacts": [{
                    "name": "original.mp4",
                    "size": 123,
                    "sha256": "a" * 64,
                    "url": "https://example.invalid/cap/redacted/original.mp4",
                }],
            }), encoding="utf-8")

            run_root = td / "runs"
            state = td / "state.json"
            root_log = td / "root.log"
            root_exec = td / "root-exec.sh"
            root_exec.write_text(
                f'''#!/bin/bash
printf '%s\\n' "$*" >> "{root_log}"
case "$*" in
  *"content query"*) echo "Row: 0 _id=1, _display_name={job_id}.mp4, relative_path=Movies/Y700Agent/" ;;
esac
''',
                encoding="utf-8",
            )
            root_exec.chmod(0o755)

            androidctl = td / "androidctl.sh"
            androidctl.write_text('#!/bin/bash\necho "mWakefulness=Asleep"\n', encoding="utf-8")
            androidctl.chmod(0o755)

            unlock = td / "secure-unlock.sh"
            unlock.write_text('#!/bin/bash\necho DEVICE_UNLOCK_OK\n', encoding="utf-8")
            unlock.chmod(0o755)

            env = os.environ.copy()
            env.update({
                "Y700_DIRECT_PULL_ROOT": str(pull),
                "Y700_DIRECT_HOST_PULL_ROOT": "/fake/host/direct-download",
                "Y700_DIRECT_RUN_ROOT": str(run_root),
                "Y700_DIRECT_STATE": str(state),
                "Y700_ROOT_EXEC": str(root_exec),
                "Y700_ANDROIDCTL": str(androidctl),
                "Y700_SECURE_UNLOCK": str(unlock),
            })
            p = subprocess.run(
                ["python3", str(STORE), job_id],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(p.returncode, 0, p.stderr)
            out = json.loads(p.stdout.strip().splitlines()[-1])
            self.assertEqual(out["status"], "DIRECT_DOWNLOADED")
            self.assertTrue(out["media_store_verified"])
            self.assertFalse(out["note_saved"])
            self.assertEqual(out["device_path"], f"/sdcard/Movies/Y700Agent/{job_id}.mp4")

            commands = root_log.read_text(encoding="utf-8")
            self.assertIn("original.mp4", commands)
            self.assertIn("Movies/Y700Agent", commands)
            self.assertIn("KEYCODE_SLEEP", commands)
            self.assertNotIn("com.zui.notes", commands)
            self.assertNotIn("tiktok", commands.lower())
            power = json.loads((run_root / job_id / "power-restore.json").read_text(encoding="utf-8"))
            self.assertEqual(power["status"], "RESTORED_ASLEEP")

    def test_direct_store_rejects_non_original_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            job_id = "dd-12345"
            bundle = td / "pull" / job_id
            bundle.mkdir(parents=True)
            (bundle / ".complete").write_text("verified\n", encoding="utf-8")
            (bundle / "manifest.json").write_text(json.dumps({
                "schema_version": 1,
                "job_id": job_id,
                "kind": "generic-artifact",
                "artifacts": [{
                    "name": "rendered.mp4",
                    "size": 1,
                    "sha256": "b" * 64,
                    "url": "https://example.invalid/rendered.mp4",
                }],
            }), encoding="utf-8")
            env = os.environ.copy()
            env["Y700_DIRECT_PULL_ROOT"] = str(td / "pull")
            p = subprocess.run(["python3", str(STORE), job_id], env=env, text=True, capture_output=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("DIRECT_DOWNLOAD_FAILED", p.stdout)


if __name__ == "__main__":
    unittest.main()
