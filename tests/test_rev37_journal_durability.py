"""Sprint 1 journal safety regression candidates (not run during development)."""
from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
import unittest
from pathlib import Path

from automation import ui_job


class JournalDurabilityTests(unittest.TestCase):
    def test_concurrent_append_produces_complete_jsonl_rows(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "job"
            folder.mkdir(mode=0o700)
            path = folder / "journal.jsonl"
            errors = []

            def append_worker(worker: int) -> None:
                try:
                    for index in range(25):
                        ui_job.append_journal(path, {
                            "phase": "HEARTBEAT", "worker": worker, "index": index,
                        })
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=append_worker, args=(n,))
                       for n in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertFalse(errors)
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 100)
            self.assertEqual(
                {(row["worker"], row["index"])
                 for row in map(json.loads, lines)},
                {(worker, index) for worker in range(4) for index in range(25)},
            )
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_symlink_and_hardlink_rejected_without_writing(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "job"
            folder.mkdir(mode=0o700)
            victim = folder / "victim"
            victim.write_text("unchanged", encoding="utf-8")
            victim.chmod(0o600)
            for path in (folder / "symlink", folder / "hardlink"):
                if path.name == "symlink":
                    path.symlink_to(victim)
                else:
                    os.link(victim, path)
                with self.assertRaises((ui_job.UiJobError, OSError)):
                    ui_job.append_journal(path, {"phase": "MUTATION_PREPARED"})
                self.assertEqual(victim.read_text(encoding="utf-8"), "unchanged")
