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
            # Explicit chmod: the test suite may enforce a 077 umask.
            folder.chmod(0o755)
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

class BoundedControlReadTests(unittest.TestCase):
    def test_missing_file_returns_default(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "job"
            folder.mkdir(mode=0o700)
            self.assertEqual(ui_job.read_json(folder / "missing.json", {}), {})

    def test_round_trip_json(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "job"
            folder.mkdir(mode=0o700)
            target = folder / "state.json"
            ui_job.atomic_json(target, {"status": "PASS"})
            self.assertEqual(ui_job.read_json(target), {"status": "PASS"})

    def test_symlink_and_hardlink_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "job"
            folder.mkdir(mode=0o700)
            victim = folder / "victim.json"
            ui_job.atomic_json(victim, {"safe": True})
            alias = folder / "alias.json"
            alias.symlink_to(victim)
            with self.assertRaises((ui_job.UiJobError, OSError)):
                ui_job.read_json(alias)
            alias.unlink()
            os.link(victim, alias)
            with self.assertRaises(ui_job.UiJobError):
                ui_job.read_json(alias)

    def test_oversized_control_file_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "job"
            folder.mkdir(mode=0o700)
            target = folder / "state.json"
            ui_job.atomic_write(target, b'{"payload":"123456789"}')
            with self.assertRaises(ui_job.UiJobError):
                ui_job.read_json(target, max_bytes=8)

    def test_fifo_is_not_opened_as_control_file(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "job"
            folder.mkdir(mode=0o700)
            fifo = folder / "state.json"
            os.mkfifo(fifo, 0o600)
            with self.assertRaises(ui_job.UiJobError):
                ui_job.read_json(fifo)

class ControlReadContinuityTests(unittest.TestCase):
    def test_invalid_json_is_explicitly_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "job"
            folder.mkdir(mode=0o700)
            target = folder / "state.json"
            ui_job.atomic_write(target, b'{"unfinished":')
            with self.assertRaisesRegex(ui_job.UiJobError, "CONTROL_READ_MALFORMED"):
                ui_job.read_json(target)

    def test_invalid_utf8_is_explicitly_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "job"
            folder.mkdir(mode=0o700)
            target = folder / "state.json"
            ui_job.atomic_write(target, bytes([255]))
            with self.assertRaisesRegex(ui_job.UiJobError, "CONTROL_READ_MALFORMED"):
                ui_job.read_json(target)
