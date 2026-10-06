from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from automation import ui_job
from bridge import bridge_client


class UiJobArchiveRaceTest(unittest.TestCase):
    def test_terminal_active_location_is_refreshed_to_archive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = bridge_client.BridgePaths(
                jobs=root / "jobs",
                runtime=root / "runtime",
            )
            active = paths.active / "job-1"
            archived = paths.archive / "succeeded" / "job-1"
            initial = {
                "protocol_version": 2,
                "job_id": "job-1",
                "location": str(active),
                "result": {"status": "SUCCEEDED", "exit_code": 0},
            }
            final = {
                "protocol_version": 2,
                "job_id": "job-1",
                "location": str(archived),
                "result": {"status": "SUCCEEDED", "exit_code": 0},
            }

            with mock.patch.object(ui_job, "BRIDGE_PATHS", paths), \
                 mock.patch.object(ui_job.bridge_v2, "status", return_value=final), \
                 mock.patch.object(ui_job.time, "sleep"):
                snapshot, location = ui_job._settle_terminal_bridge_location(
                    "job-1", initial, active
                )

            self.assertEqual(snapshot, final)
            self.assertEqual(location, archived)

    def test_non_v2_location_is_unchanged(self) -> None:
        location = Path("/tmp/legacy-job")
        snapshot = {"protocol_version": 1, "location": str(location)}
        got_snapshot, got_location = ui_job._settle_terminal_bridge_location(
            "legacy", snapshot, location
        )
        self.assertIs(got_snapshot, snapshot)
        self.assertEqual(got_location, location)


if __name__ == "__main__":
    unittest.main()
