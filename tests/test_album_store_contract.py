from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
        self.assertIn("com.zui.notes/.home.ShareReceiverIntentActivity", text)
        self.assertIn("android.intent.extra.TEXT", text)

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
        self.assertIn("AUTO_PUBLISH", text)
        self.assertIn("STORE_ALBUM", text)
        self.assertIn("ASCII `:`", text)
        self.assertIn("Chinese `：`", text)
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
            caption = "တစ်ချက်တည်းနဲ့ လွယ်လွယ်ကူကူ ကူးယူတင်နိုင်တဲ့ caption"
            (job / "caption.my.txt").write_text(caption + "\n", encoding="utf-8")
            run_root = td / "runs"
            state = td / "album-state.json"
            root_log = td / "root.log"

            root_exec = td / "root-exec.sh"
            root_exec.write_text(
                f'''#!/bin/bash\nprintf '%s\\n' "$*" >> "{root_log}"\ncase "$*" in\n  *"content query"*) echo "Row: 0 _id=1, _display_name={job.name}.mp4, relative_path=Movies/Y700Agent/" ;;\n  *"ShareReceiverIntentActivity"*) printf "Status: ok\nActivity: com.zui.notes/.home.MainActivity\n" ;;\nesac\n''',
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
                "Y700_RUNTIME": str(td / "runtime"),
                "Y700_UI_STATE_DIR": str(td / "runtime" / "ui-state"),
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
            self.assertTrue(out["note_saved"])
            self.assertEqual(out["note_app"], "com.zui.notes")
            commands = root_log.read_text()
            self.assertNotIn("-delete", commands)
            self.assertIn("KEYCODE_SLEEP", commands)
            self.assertIn("Movies/Y700Agent", commands)
            self.assertIn("com.zui.notes/.home.ShareReceiverIntentActivity", commands)
            self.assertIn(caption, commands)
            power = json.loads((run_root / job.name / "power-restore.json").read_text())
            self.assertEqual(power["status"], "RESTORED_ASLEEP")

    def test_album_store_claim_and_epoch_precede_legacy_ui_mutation(self) -> None:
        from publisher import store_album_job as store

        events: list[str] = []

        @contextmanager
        def fake_claim(**kwargs):
            events.append("claim_enter")
            try:
                yield SimpleNamespace(as_dict=lambda: {"claim_id": "claim-test"})
            finally:
                events.append("claim_exit")

        def fake_root_exec(command, **kwargs):
            events.append("root:" + str(command))
            if "content query" in str(command):
                return SimpleNamespace(
                    stdout=(
                        "Row: 0 _id=1, _display_name=job-1.mp4, "
                        "relative_path=Movies/Y700Agent/"
                    ),
                    stderr="",
                    returncode=0,
                )
            return SimpleNamespace(stdout="", stderr="", returncode=0)

        def fake_run(cmd, **kwargs):
            events.append("run:" + " ".join(map(str, cmd)))
            return SimpleNamespace(stdout="", stderr="", returncode=0)

        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            ready = td / "ready"
            job = ready / "job-1"
            job.mkdir(parents=True)
            run_root = td / "runs"

            manifest = {
                "job_id": "job-1",
                "video_file": "video.my.mp4",
                "caption_file": "caption.my.txt",
            }

            with (
                patch.object(store, "READY", ready),
                patch.object(store, "RUN_ROOT", run_root),
                patch.object(store, "existing_result", return_value=None),
                patch.object(store, "load_manifest", return_value=manifest),
                patch.object(store, "capture_power_state", return_value=("AWAKE", "")),
                patch.object(store, "write_state", side_effect=lambda *a, **k: {}),
                patch.object(store, "write_json_atomic", side_effect=lambda *a, **k: None),
                patch.object(
                    store.resource_arbiter,
                    "acquire_android_ui",
                    side_effect=fake_claim,
                ),
                patch.object(
                    store.state_integrity,
                    "bump_epoch",
                    side_effect=lambda reason: events.append("epoch") or {},
                ),
                patch.object(store, "run", side_effect=fake_run),
                patch.object(store, "root_exec", side_effect=fake_root_exec),
                patch.object(
                    store,
                    "save_caption_note",
                    side_effect=lambda *a, **k: {
                        "note_app": "com.zui.notes",
                        "note_method": "ACTION_SEND_TEXT_PLAIN",
                        "caption_sha256": "a" * 64,
                    },
                ),
                patch.object(
                    store,
                    "restore_power_state",
                    return_value={"status": "RESTORE_NOT_REQUIRED"},
                ),
            ):
                result = store.store("job-1")

        self.assertEqual(result["status"], "STORED_IN_ALBUM")
        first_root = next(i for i, event in enumerate(events) if event.startswith("root:"))
        secure_unlock = next(
            i for i, event in enumerate(events)
            if event.startswith("run:") and "secure-unlock" in event
        )
        self.assertLess(events.index("claim_enter"), events.index("epoch"))
        self.assertLess(events.index("epoch"), secure_unlock)
        self.assertLess(secure_unlock, first_root)
        self.assertGreater(events.index("claim_exit"), first_root)

    def test_album_store_note_is_idempotent(self) -> None:
        text = STORE.read_text()
        self.assertIn("note-result.json", text)
        self.assertIn("caption_sha256", text)
        self.assertIn('previous.get("note_saved") is True', text)


if __name__ == "__main__":
    unittest.main()
