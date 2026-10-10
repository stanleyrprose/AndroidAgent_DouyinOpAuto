import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.media_lifecycle import TransferSafetyError, verify_and_clean


class MediaLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "dy-test"
        for name in ("source", "analysis", "production", "export"):
            (self.root / name).mkdir(parents=True)
        self.video = self.root / "production" / "video.my.mp4"
        self.video.write_bytes(b"video" * 100)
        self.audio = self.root / "analysis" / "audio.wav"
        self.audio.write_bytes(b"audio")
        (self.root / "analysis" / "ledger.json").write_text("{}")
        self.hash = hashlib.sha256(self.video.read_bytes()).hexdigest()

    def run_clean(self):
        return verify_and_clean(self.root, ssh_target="y700", device_path="/storage/emulated/0/Movies/a.mp4")

    def test_success_and_idempotence(self):
        with patch("pipeline.media_lifecycle._remote_hash", return_value=self.hash) as remote:
            result = self.run_clean()
            self.assertEqual(result["status"], "MAC_MEDIA_CLEANED")
            self.assertEqual(result["deleted_count"], 2)
            self.assertFalse(self.video.exists())
            self.assertFalse(self.audio.exists())
            self.assertTrue((self.root / "analysis" / "ledger.json").exists())
            self.assertEqual(self.run_clean(), result)
            self.assertEqual(remote.call_count, 1)

    def test_mismatch_retains_all(self):
        with patch("pipeline.media_lifecycle._remote_hash", return_value="0" * 64):
            with self.assertRaisesRegex(TransferSafetyError, "mismatch"):
                self.run_clean()
        self.assertTrue(self.video.exists())
        self.assertTrue(self.audio.exists())

    def test_ssh_failure_retains_all(self):
        with patch("pipeline.media_lifecycle._remote_hash", side_effect=TransferSafetyError("offline")):
            with self.assertRaises(TransferSafetyError):
                self.run_clean()
        self.assertTrue(self.video.exists())

    def test_symlink_refused(self):
        (self.root / "analysis" / "evil.jpg").symlink_to(self.video)
        with patch("pipeline.media_lifecycle._remote_hash", return_value=self.hash):
            with self.assertRaisesRegex(TransferSafetyError, "symlink"):
                self.run_clean()
        self.assertTrue(self.video.exists())

    def test_incomplete_receipt_blocks_retry(self):
        receipt = self.root / "export" / "media-cleanup-receipt.json"
        receipt.write_text('{"status":"TRANSFER_VERIFIED"}')
        with self.assertRaisesRegex(TransferSafetyError, "manual recovery"):
            self.run_clean()
        self.assertTrue(self.video.exists())

    def test_missing_artifact_refuses(self):
        self.video.unlink()
        with self.assertRaises(FileNotFoundError):
            self.run_clean()


if __name__ == "__main__":
    unittest.main()
