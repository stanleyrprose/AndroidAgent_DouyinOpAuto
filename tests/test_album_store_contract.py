from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "publisher" / "store_album_job.py"
MAC_STORE = ROOT / "mac" / "production-pipeline" / "scripts" / "store-to-y700-album.sh"
SOUL = ROOT / "config" / "hermes-y700automation-SOUL.md"


class AlbumStoreContractTests(unittest.TestCase):
    def test_album_store_is_non_destructive_and_has_no_tiktok_publish_capability(self) -> None:
        text = STORE.read_text()
        self.assertNotIn("find {ALBUM}", text)
        self.assertNotIn("-type f -delete", text)
        self.assertNotIn("apps.tiktok", text)
        self.assertNotIn("approve-public-commit", text)
        self.assertNotIn("publish-async", text)
        self.assertIn("STORED_IN_ALBUM", text)
        self.assertIn("Y700Agent", text)

    def test_mac_album_store_wrapper_has_no_publish_capability(self) -> None:
        text = MAC_STORE.read_text()
        self.assertIn("publisher/pull_job.py", text)
        self.assertIn("store-to-album.sh", text)
        self.assertIn("mark-album-stored", text)
        self.assertIn("ALBUM_STORED", text)
        self.assertNotIn("approve-public-commit.sh", text)
        self.assertNotIn("publish-async.sh", text)
        self.assertNotIn("publish_job.py", text)

    def test_telegram_requires_explicit_intent_prefix(self) -> None:
        text = SOUL.read_text()
        self.assertIn("自动发布+", text)
        self.assertIn("存到相册+", text)
        self.assertIn("bare Douyin URL", text)
        self.assertIn("must not start", text)

    def test_album_store_restores_asleep_without_deleting_other_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            ready = td / "ready"
            job = ready / "dy-1234567890123456789"
            job.mkdir(parents=True)
            manifest = {
                "schema_version": 1,
                "job_id": job.name,
                "source": "douyin:1234567890123456789",
                "target": "tiktok",
                "language": "my",
                "status": "READY",
                "video_file": "video.my.mp4",
                "caption_file": "caption.my.txt",
                "sha256": {
                    "video.my.mp4": "a" * 64,
                    "caption.my.txt": "b" * 64,
                },
                "publish_mode": "DRY_RUN",
            }
            (job / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            run_root = td / "runs"
            state = td / "album-state.json"
            root_log = td / "root.log"

            root_exec = td / "root-exec.sh"
            root_exec.write_text(
                f'''#!/bin/bash\nprintf '%s\\n' "$*" >> "{root_log}"\ncase "$*" in\n  *"content query"*) echo "Row: 0 _id=1, _display_name={job.name}.mp4, relative_path=Movies/Y700Agent/" ;;\nesac\n''',
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
                "Y700_READY_ROOT": str(ready),
                "Y700_ALBUM_STORE_RUN_ROOT": str(run_root),
                "Y700_ALBUM_STORE_STATE": str(state),
                "Y700_HOST_READY_ROOT": "/fake/host/ready",
                "Y700_ROOT_EXEC": str(root_exec),
                "Y700_ANDROIDCTL": str(androidctl),
                "Y700_SECURE_UNLOCK": str(unlock),
            })
            p = subprocess.run(
                ["python3", str(STORE), job.name],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(p.returncode, 0, p.stderr)
            out = json.loads(p.stdout.strip().splitlines()[-1])
            self.assertEqual(out["status"], "STORED_IN_ALBUM")
            self.assertTrue(out["media_store_verified"])
            commands = root_log.read_text()
            self.assertNotIn("-delete", commands)
            self.assertIn("KEYCODE_SLEEP", commands)
            self.assertIn("Movies/Y700Agent", commands)
            power = json.loads((run_root / job.name / "power-restore.json").read_text())
            self.assertEqual(power["status"], "RESTORED_ASLEEP")


if __name__ == "__main__":
    unittest.main()
