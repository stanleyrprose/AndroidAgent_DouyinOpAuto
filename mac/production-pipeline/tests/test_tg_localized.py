"""Focused safety regressions for the TG-only localized-download intent."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.common import atomic_json, read_json
from pipeline.export import export
from pipeline.telegram_media import MediaDeliveryError
from pipeline.tg_localized import TelegramCleanupError, finish


class FakeJob:
    def __init__(self, jobs: Path):
        self.job_id = "dy-1234567890123456789"
        self.dir = jobs / self.job_id
        self.dir.mkdir(parents=True)
        for name in ("source", "analysis", "localization", "production", "export", "evidence"):
            (self.dir / name).mkdir()
        (self.dir / "source" / "original.mp4").write_bytes(b"original video")
        (self.dir / "analysis" / "transcript.json").write_text("{}", encoding="utf-8")
        (self.dir / "localization" / "localization.json").write_text("{}", encoding="utf-8")
        (self.dir / "production" / "video.my.mp4").write_bytes(b"burmese rendered video")
        (self.dir / "production" / "caption.my.txt").write_text("caption", encoding="utf-8")
        atomic_json(self.dir / "state.json", {
            "job_id": self.job_id,
            "state": "RENDERED",
            "workflow_intent": "TG_LOCALIZED",
        })

    def state(self):
        return read_json(self.dir / "state.json")

    def write_state(self, name, **kwargs):
        data = {**self.state(), "state": name, **kwargs}
        atomic_json(self.dir / "state.json", data)
        return data


class TelegramLocalizedCompletionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.jobs = root / "jobs"
        self.jobs.mkdir()
        self.tmp = root / "tmp"
        self.tmp.mkdir()
        self.job = FakeJob(self.jobs)
        (self.tmp / self.job.job_id).mkdir()
        (self.tmp / self.job.job_id / "scratch.txt").write_text("temporary", encoding="utf-8")
        self.env = patch.dict(os.environ, {
            "Y700_TG_CHAT_ID": "-123",
            "Y700_TG_MEDIA_SENDER": "/fake/media",
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.patches = [
            patch("pipeline.tg_localized.JOBS", self.jobs),
            patch("pipeline.tg_localized.TMP", self.tmp),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.success = {"ok": True, "result": {
            "message_id": 321, "chat": {"id": -123},
        }}

    def test_success_cleans_all_artifacts_and_retains_only_delivery_proof(self):
        with patch("pipeline.telegram_media._send", return_value=self.success) as sender:
            result = finish(self.job)
            repeated = finish(self.job)
        self.assertEqual(sender.call_count, 1)
        self.assertEqual(result, repeated)
        self.assertEqual(result["status"], "TG_DELIVERED")
        self.assertEqual(result["message_id"], 321)
        self.assertEqual(self.job.state()["telegram_cleanup_status"], "COMPLETE")
        for name in ("source", "analysis", "localization", "production",
                     "evidence", "export", "resume", "tmp"):
            self.assertFalse((self.job.dir / name).exists())
        self.assertFalse((self.tmp / self.job.job_id).exists())
        self.assertTrue((self.job.dir / "state.json").is_file())
        receipt = read_json(self.job.dir / "tg-delivery-receipt.json")
        self.assertEqual(receipt["message_id"], 321)
        self.assertEqual(receipt["intent"], "TG_LOCALIZED")
        self.assertEqual(len(receipt["sha256"]), 64)
        self.assertEqual(len(receipt["destination_sha256"]), 64)

    def test_uncertain_delivery_retains_media_and_never_auto_retries(self):
        with patch("pipeline.telegram_media._send",
                   side_effect=MediaDeliveryError("DELIVERY_UNCERTAIN")) as sender:
            for _ in range(2):
                with self.assertRaisesRegex(MediaDeliveryError, "UNCERTAIN"):
                    finish(self.job)
        self.assertEqual(sender.call_count, 1)
        self.assertEqual(self.job.state()["state"], "RENDERED")
        self.assertTrue((self.job.dir / "source" / "original.mp4").exists())
        self.assertTrue((self.job.dir / "production" / "video.my.mp4").exists())
        self.assertFalse((self.job.dir / "tg-delivery-receipt.json").exists())

    def test_wrong_chat_or_missing_message_id_preserves_media(self):
        for response in (
            {"ok": True, "result": {"message_id": 1, "chat": {"id": 55}}},
            {"ok": True, "result": {"chat": {"id": -123}}},
        ):
            with self.subTest(response=response):
                (self.job.dir / "export" / "telegram-media-receipt.json").unlink(missing_ok=True)
                with patch("pipeline.telegram_media._send", return_value=response):
                    with self.assertRaises(MediaDeliveryError):
                        finish(self.job)
                self.assertEqual(self.job.state()["state"], "RENDERED")
                self.assertTrue((self.job.dir / "production" / "video.my.mp4").exists())

    def test_crash_during_cleanup_resumes_without_resending(self):
        with patch("pipeline.telegram_media._send", return_value=self.success) as sender:
            with patch("pipeline.tg_localized.shutil.rmtree", side_effect=OSError("disk busy")):
                with self.assertRaisesRegex(OSError, "disk busy"):
                    finish(self.job)
            self.assertEqual(self.job.state()["state"], "TG_DELIVERED_CLEANUP_PENDING")
            self.assertEqual(read_json(self.job.dir / "tg-delivery-receipt.json")["message_id"], 321)
            finish(self.job)
        self.assertEqual(sender.call_count, 1)
        self.assertEqual(self.job.state()["state"], "TG_DELIVERED")
        self.assertFalse((self.job.dir / "source").exists())

    def test_symlink_in_cleanup_scope_blocks_without_following_it(self):
        external = self.jobs.parent / "external.txt"
        external.write_text("must remain", encoding="utf-8")
        link = self.job.dir / "analysis" / "external"
        link.symlink_to(external)
        with patch("pipeline.telegram_media._send", return_value=self.success) as sender:
            with self.assertRaisesRegex(TelegramCleanupError, "symlink"):
                finish(self.job)
            self.assertEqual(self.job.state()["state"], "TG_DELIVERED_CLEANUP_PENDING")
            self.assertTrue((self.job.dir / "source" / "original.mp4").exists())
            self.assertEqual(external.read_text(), "must remain")
            link.unlink()
            finish(self.job)
        self.assertEqual(sender.call_count, 1)
        self.assertEqual(external.read_text(), "must remain")

    def test_non_tg_intent_never_sends_or_cleans(self):
        self.job.write_state("RENDERED", workflow_intent="STORE_ALBUM")
        with patch("pipeline.telegram_media._send") as sender:
            with self.assertRaisesRegex(TelegramCleanupError, "intent"):
                finish(self.job)
            sender.assert_not_called()
        self.assertTrue((self.job.dir / "source" / "original.mp4").exists())

    def test_dedupe_index_can_refresh_after_source_metadata_is_deleted(self):
        from pipeline.cli import refresh_index
        self.job.write_state(
            "RENDERED",
            aweme_id="1234567890123456789",
            source_url="https://www.douyin.com/video/1234567890123456789",
        )
        with patch("pipeline.telegram_media._send", return_value=self.success):
            finish(self.job)
        with patch("pipeline.cli.index_job") as record:
            refresh_index(self.job)
        self.assertEqual(record.call_args.kwargs["aweme_id"], "1234567890123456789")
        self.assertIsNotNone(record.call_args.kwargs["url_key"])

    def test_tg_intent_rejects_y700_capability_export(self):
        with self.assertRaisesRegex(RuntimeError, "Telegram-only"):
            export(self.job.dir)
        self.assertTrue((self.job.dir / "production" / "video.my.mp4").exists())


if __name__ == "__main__":
    unittest.main()
