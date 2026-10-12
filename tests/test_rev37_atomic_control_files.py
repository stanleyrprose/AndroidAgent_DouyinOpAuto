"""Source-only regression candidates for UI control-file atomic replacement."""
import os
import stat
import tempfile
import unittest
from pathlib import Path

from automation import ui_job


class AtomicControlFileTests(unittest.TestCase):
    def test_atomic_create_and_replace(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "job"
            folder.mkdir(mode=0o700)
            target = folder / "state.json"
            ui_job.atomic_write(target, b'{"status":"RUNNING"}\n')
            ui_job.atomic_write(target, b'{"status":"PASS"}\n')
            self.assertEqual(target.read_bytes(), b'{"status":"PASS"}\n')
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertFalse(list(folder.glob(".atomic-*")))

    def test_symlink_target_does_not_replace_victim(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "job"
            folder.mkdir(mode=0o700)
            victim = folder / "victim"
            victim.write_bytes(b"preserve")
            (folder / "state.json").symlink_to(victim)
            with self.assertRaises(ui_job.UiJobError):
                ui_job.atomic_write(folder / "state.json", b"overwrite")
            self.assertEqual(victim.read_bytes(), b"preserve")
            self.assertFalse(list(folder.glob(".atomic-*")))

    def test_untrusted_directory_is_denied(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "job"
            folder.mkdir(mode=0o755)
            with self.assertRaises(ui_job.UiJobError):
                ui_job.atomic_write(folder / "state.json", b"data")
            self.assertFalse((folder / "state.json").exists())

    def test_parent_symlink_is_denied(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "real"
            folder.mkdir(mode=0o700)
            (Path(root) / "alias").symlink_to(folder, target_is_directory=True)
            with self.assertRaises(ui_job.UiJobError):
                ui_job.atomic_write(Path(root) / "alias" / "state.json", b"data")
            self.assertFalse((folder / "state.json").exists())
