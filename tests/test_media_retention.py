from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from publisher.media_retention import prune_verified_video

ROOT = Path(__file__).resolve().parents[1]


class MediaRetentionTests(unittest.TestCase):
    def test_prune_verified_copy_and_idempotence(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            video = folder / "video.mp4"
            video.write_bytes(b"test-video")
            digest = hashlib.sha256(video.read_bytes()).hexdigest()
            calls = []

            def android(cmd, **kw):
                calls.append(cmd)
                self.assertFalse(kw["check"])
                return SimpleNamespace(returncode=0, stdout=f"{digest}  /sdcard/Movies/Y700Agent/x.mp4")

            result = prune_verified_video(folder, "video.mp4", "/sdcard/Movies/Y700Agent/x.mp4", android)
            self.assertEqual(result["status"], "PRUNED")
            self.assertFalse(video.exists())
            self.assertEqual(len(calls), 1)
            self.assertEqual(
                prune_verified_video(folder, "video.mp4", "/sdcard/Movies/Y700Agent/x.mp4", android)["status"],
                "ALREADY_ABSENT",
            )

    def test_reject_mismatch_and_path_traversal(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            source = folder / "video.mp4"
            source.write_bytes(b"keep-this")
            bad = lambda *_a, **_kw: SimpleNamespace(returncode=0, stdout=f"{'0'*64}  x")
            self.assertEqual(
                prune_verified_video(folder, "video.mp4", "/sdcard/Movies/Y700Agent/x.mp4", bad)["status"],
                "SKIPPED",
            )
            self.assertEqual(
                prune_verified_video(folder, "../video.mp4", "/sdcard/Movies/Y700Agent/x.mp4", bad)["status"],
                "SKIPPED",
            )
            self.assertTrue(source.exists())

    def test_bridge_failure_does_not_remove_video(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "video.mp4"
            video.write_bytes(b"retain")
            bad = lambda *_a, **_kw: SimpleNamespace(returncode=124, stdout="")
            result = prune_verified_video(Path(root), "video.mp4", "/sdcard/Movies/Y700Agent/x.mp4", bad)
            self.assertEqual(result["reason"], "gallery_unreadable")
            self.assertTrue(video.exists())

    def test_export_uses_hardlink_instead_of_video_copy(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("y700_exporter", ROOT / "mac/media-export/export_job.py")
        exporter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(exporter)
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / "original.mp4"
            dst = Path(root) / "export.mp4"
            src.write_bytes(b"video-bytes")
            exporter.link_video_or_copy(src, dst)
            self.assertTrue(os.path.samefile(src, dst))

    def test_tiktok_staging_preserves_other_album_items(self):
        stage = (ROOT / "publisher/stage_job.py").read_text()
        self.assertNotIn("find {ALBUM}", stage)
        self.assertNotIn("-type f -delete", stage)
        self.assertIn("mv -f", stage)


if __name__ == "__main__":
    unittest.main()
