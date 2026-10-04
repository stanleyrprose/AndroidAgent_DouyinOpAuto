from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from automation import ui_job


class FailureEvidenceExportTests(unittest.TestCase):
    def test_driver_failure_evidence_is_persisted_as_durable_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ui_dir = Path(td) / "job-1"
            (ui_dir / "evidence").mkdir(parents=True)
            req = {
                "job_id": "job-1",
                "session_id": "session-1",
                "actions": [{
                    "action_id": "missing",
                    "action": "assert",
                    "selector": {"resource_id": "missing:id/value"},
                    "expect": {"package": "com.example"},
                }],
            }
            result = {
                "status": "FAILED",
                "error": {"code": "ELEMENT_NOT_FOUND", "message": "missing"},
                "actions": [{
                    "action_id": "missing",
                    "action": "assert",
                    "status": "FAILED",
                    "error": {"code": "ELEMENT_NOT_FOUND", "message": "missing"},
                    "failure_evidence": {
                        "timestamp_ms": 1234,
                        "package": "com.example",
                        "activity": "mResumedActivity: com.example/.Main",
                        "screenshot": {
                            "path": "/data/user/0/com.stanley.y700automation/files/x/failure-action-0.png",
                            "size": 42,
                        },
                        "compact_ui_tree": {
                            "package": "com.example",
                            "node_count": 1,
                            "elements": [{"resource_id": "com.example:id/root"}],
                        },
                    },
                }],
            }
            with (
                mock.patch.object(
                    ui_job,
                    "copy_screenshot",
                    return_value="evidence/failure-action-0.png",
                ),
                mock.patch.object(ui_job, "_host_failure_fallback", return_value={}),
            ):
                ref = ui_job.export_failure_evidence(ui_dir, req, result)

            self.assertEqual(ref["screenshot"], "evidence/failure-action-0.png")
            self.assertEqual(ref["compact_ui_tree"], "evidence/failure-tree.json")
            context = json.loads((ui_dir / "evidence" / "failure-context.json").read_text())
            tree = json.loads((ui_dir / "evidence" / "failure-tree.json").read_text())
            self.assertEqual(context["action"], "assert")
            self.assertEqual(context["selector"], {"resource_id": "missing:id/value"})
            self.assertEqual(context["postcondition"], {"package": "com.example"})
            self.assertEqual(context["error"]["code"], "ELEMENT_NOT_FOUND")
            self.assertEqual(context["package"], "com.example")
            self.assertIn("Main", context["activity"])
            self.assertEqual(tree["node_count"], 1)
            self.assertEqual(result["failure_evidence"]["context"], "evidence/failure-context.json")
            self.assertEqual(
                result["actions"][0]["failure_evidence"]["compact_ui_tree"],
                "evidence/failure-tree.json",
            )

    def test_no_driver_evidence_uses_host_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ui_dir = Path(td) / "job-2"
            (ui_dir / "evidence").mkdir(parents=True)
            req = {
                "job_id": "job-2",
                "session_id": "session-2",
                "actions": [{"action_id": "observe", "action": "observe"}],
            }
            result = {
                "status": "FAILED",
                "error": {"code": "DRIVER_CRASHED", "message": "boom"},
                "actions": [],
            }
            fallback = {
                "source": "host_fallback",
                "activity": "mResumedActivity: com.example/.Main",
                "screenshot": "evidence/failure-host.png",
                "compact_ui_tree": "evidence/failure-tree.json",
            }
            with mock.patch.object(ui_job, "_host_failure_fallback", return_value=fallback):
                ref = ui_job.export_failure_evidence(ui_dir, req, result)

            self.assertEqual(ref["screenshot"], "evidence/failure-host.png")
            context = json.loads((ui_dir / "evidence" / "failure-context.json").read_text())
            self.assertEqual(context["error"]["code"], "DRIVER_CRASHED")
            self.assertEqual(context["activity"], fallback["activity"])


if __name__ == "__main__":
    unittest.main()
