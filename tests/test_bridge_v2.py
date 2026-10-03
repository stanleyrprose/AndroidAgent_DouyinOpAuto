from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from bridge import bridge_client as bc


class BridgeV2ClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.paths = bc.BridgePaths(jobs=root / "jobs", runtime=root / "runtime")
        bc.ensure_layout(self.paths)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_atomic_submission_only_exposes_complete_active_job(self) -> None:
        job = bc.submit_root("echo bridge-v2", timeout_ms=5000, paths=self.paths)
        self.assertFalse((self.paths.staging / job).exists())
        active = self.paths.active / job
        self.assertTrue(active.is_dir())
        self.assertTrue((active / "request.json").is_file())
        self.assertTrue((active / "state.json").is_file())
        self.assertTrue((active / "journal.jsonl").is_file())

        req = bc.read_json(active / "request.json", max_bytes=bc.REQUEST_MAX_BYTES)
        state_obj = bc.read_json(active / "state.json")
        self.assertEqual(req["protocol_version"], 2)
        self.assertEqual(req["execution_policy"]["replay"], "NEVER")
        self.assertEqual(state_obj["state"], "QUEUED")
        self.assertEqual(stat.S_IMODE(active.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((active / "request.json").stat().st_mode), 0o600)

    def test_half_created_staging_job_is_not_visible(self) -> None:
        job = "root-half-created"
        stage = self.paths.staging / job
        stage.mkdir(mode=0o700)
        (stage / "request.json.tmp").write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(bc.BridgeError, "JOB_NOT_FOUND"):
            bc.status(job, paths=self.paths)

    def test_archive_lookup_returns_terminal_job(self) -> None:
        job = bc.submit_root("true", timeout_ms=5000, paths=self.paths)
        active = self.paths.active / job
        bc.atomic_json(active / "state.json", {"state": "SUCCEEDED"})
        bc.atomic_json(active / "result.json", {"status": "SUCCEEDED", "exit_code": 0})
        dest = self.paths.archive / "succeeded" / job
        os.replace(active, dest)
        snap = bc.status(job, paths=self.paths)
        self.assertEqual(snap["result"]["status"], "SUCCEEDED")
        self.assertIn("/archive/succeeded/", snap["location"])

    def test_cancel_is_idempotent_under_concurrency(self) -> None:
        job = bc.submit_root("sleep 1", timeout_ms=5000, paths=self.paths)

        def do_cancel(i: int) -> None:
            bc.cancel(job, reason=f"r{i}", paths=self.paths)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(do_cancel, range(16)))

        active = self.paths.active / job
        cancel_obj = bc.read_json(active / "cancel.json", max_bytes=bc.CANCEL_MAX_BYTES)
        self.assertTrue(cancel_obj["reason"].startswith("r"))
        rows = [
            json.loads(line)
            for line in (active / "journal.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        cancel_rows = [row for row in rows if row.get("event") == "CANCEL_REQUESTED"]
        self.assertEqual(len(cancel_rows), 16)

    def test_malformed_state_is_protocol_error_not_silently_defaulted(self) -> None:
        job = bc.submit_root("true", timeout_ms=5000, paths=self.paths)
        state_path = self.paths.active / job / "state.json"
        state_path.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(bc.BridgeError, "malformed durable JSON"):
            bc.status(job, paths=self.paths)

    def test_request_size_limit_blocks_before_active_visibility(self) -> None:
        with mock.patch.object(bc, "REQUEST_MAX_BYTES", 300):
            with self.assertRaisesRegex(bc.BridgeError, "JOB_PAYLOAD_TOO_LARGE"):
                bc.submit_root("x" * 1000, timeout_ms=5000, paths=self.paths)
        self.assertEqual(list(self.paths.active.iterdir()), [])

    def test_v1_active_and_history_are_directly_queryable(self) -> None:
        active_v1 = self.paths.jobs / "legacy-active"
        active_v1.mkdir(mode=0o700)
        bc.atomic_json(active_v1 / "state.json", {"status": "RUNNING"})
        bc.atomic_json(active_v1 / "request.json", {"version": 1, "action": "root_exec"})
        snap = bc.status("legacy-active", paths=self.paths)
        self.assertEqual(snap["protocol_version"], 1)
        self.assertEqual(snap["state"]["status"], "RUNNING")

        history = self.paths.legacy_history / "legacy-done"
        history.mkdir(parents=True, mode=0o700)
        bc.atomic_json(history / "state.json", {"status": "SUCCEEDED"})
        bc.atomic_json(history / "result.json", {"status": "SUCCEEDED", "exit_code": 0})
        snap = bc.status("legacy-done", paths=self.paths)
        self.assertEqual(snap["protocol_version"], 1)
        self.assertEqual(snap["result"]["exit_code"], 0)

    def test_cleanup_staging_is_explicit_and_never_executes_content(self) -> None:
        job = "root-stale-stage"
        stage = self.paths.staging / job
        stage.mkdir(mode=0o700)
        (stage / "request.json").write_text('{"protocol_version":2}', encoding="utf-8")
        old = time.time() - 7200
        os.utime(stage, (old, old))
        result = bc.cleanup_staging(ttl_seconds=3600, paths=self.paths)
        self.assertEqual(result["removed"], [job])
        self.assertFalse(stage.exists())
        maintenance = self.paths.control / "maintenance.jsonl"
        self.assertIn("STALE_STAGING_REMOVED", maintenance.read_text(encoding="utf-8"))

    def test_health_reports_corrupt_control_file_without_crashing(self) -> None:
        (self.paths.control / "executor.json").write_text("{bad", encoding="utf-8")
        report = bc.health(paths=self.paths)
        self.assertEqual(report["executor"]["status"], "CORRUPT")

    def test_reserved_job_ids_are_rejected(self) -> None:
        for job_id in ("active", "archive", "control", ".staging"):
            with self.subTest(job_id=job_id):
                with self.assertRaisesRegex(bc.BridgeError, "invalid job_id"):
                    bc.submit_root("true", timeout_ms=5000, job_id=job_id, paths=self.paths)

    def test_archived_job_id_cannot_be_reused(self) -> None:
        job_id = "root-archived-collision"
        archived = self.paths.archive / "succeeded" / job_id
        archived.mkdir(mode=0o700)
        bc.atomic_json(archived / "state.json", {"state": "SUCCEEDED"})
        bc.atomic_json(archived / "result.json", {"status": "SUCCEEDED", "exit_code": 0})
        with self.assertRaisesRegex(bc.BridgeError, "job already exists"):
            bc.submit_root("true", timeout_ms=5000, job_id=job_id, paths=self.paths)

    def test_symlink_job_root_is_rejected(self) -> None:
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        link = self.paths.active / "root-symlink"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(bc.BridgeError, "SYMLINK_JOB_ROOT"):
            bc.status("root-symlink", paths=self.paths)

    def test_cli_separator_is_not_executed_as_command_text(self) -> None:
        argv = ["bridge_client.py", "exec-root", "--timeout-ms", "5000", "--", "echo", "ok"]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(bc, "exec_root", return_value=0) as call:
            self.assertEqual(bc.main(), 0)
        self.assertEqual(call.call_args.args[0], "echo ok")
        self.assertEqual(call.call_args.kwargs["timeout_ms"], 5000)


if __name__ == "__main__":
    unittest.main()
