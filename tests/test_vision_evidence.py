import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from automation import ui_job


class VisionEvidenceQuotaTest(unittest.TestCase):
    def test_request_rejects_unknown_vision_key(self):
        req = {
            "protocol_version": 1,
            "job_id": "vision-test",
            "actions": [{"action": "health"}],
            "vision": {"enabled": True, "mystery": True},
        }
        with self.assertRaisesRegex(ui_job.UiJobError, "unsupported vision keys"):
            ui_job.validate_request(req)

    def test_request_accepts_ocr_enabled_boolean(self):
        req = {
            "protocol_version": 1,
            "job_id": "vision-ocr-test",
            "actions": [{"action": "health"}],
            "vision": {"enabled": True, "ocr_enabled": True},
        }
        ui_job.validate_request(req)

    def test_request_rejects_non_boolean_ocr_enabled(self):
        req = {
            "protocol_version": 1,
            "job_id": "vision-ocr-test",
            "actions": [{"action": "health"}],
            "vision": {"enabled": True, "ocr_enabled": "yes"},
        }
        with self.assertRaisesRegex(ui_job.UiJobError, "ocr_enabled"):
            ui_job.validate_request(req)

    def test_request_rejects_too_small_quota(self):
        req = {
            "protocol_version": 1,
            "job_id": "vision-test",
            "actions": [{"action": "health"}],
            "vision": {"enabled": True, "evidence_max_bytes": 1024},
        }
        with self.assertRaisesRegex(ui_job.UiJobError, "evidence_max_bytes"):
            ui_job.validate_request(req)

    def test_quota_evicts_only_old_terminal_unpinned_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            current = root / "current"
            old = root / "old"
            active = root / "active"
            pinned = root / "pinned"

            def make_job(path: Path, status: str, size: int, pin: bool = False):
                ev = path / "evidence"
                ev.mkdir(parents=True)
                (ev / "vision-metadata.json").write_text("{}")
                (ev / "payload.bin").write_bytes(b"x" * size)
                (path / "state.json").write_text(json.dumps({"status": status}))
                if pin:
                    (path / ".pinned").write_text("1")

            make_job(current, "RUNNING", 200)
            make_job(old, "PASS", 200)
            make_job(active, "RUNNING", 200)
            make_job(pinned, "PASS", 200, pin=True)

            with mock.patch.object(ui_job, "UI_JOBS", root):
                evicted, retained = ui_job.enforce_vision_evidence_quota(
                    650, current_ui_dir=current
                )

            self.assertEqual(evicted, 1)
            self.assertFalse((old / "evidence").exists())
            self.assertTrue((old / "state.json").exists())
            self.assertTrue((old / "vision-evidence-evicted.json").exists())
            self.assertTrue((current / "evidence").exists())
            self.assertTrue((active / "evidence").exists())
            self.assertTrue((pinned / "evidence").exists())
            self.assertLessEqual(retained, 650)

    def test_reconcile_required_is_never_evicted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            current = root / "current"
            reconcile = root / "reconcile"
            for path, status in (
                (current, "RUNNING"),
                (reconcile, "RECONCILE_REQUIRED"),
            ):
                ev = path / "evidence"
                ev.mkdir(parents=True)
                (ev / "vision-metadata.json").write_text("{}")
                (ev / "payload.bin").write_bytes(b"x" * 300)
                (path / "state.json").write_text(json.dumps({"status": status}))

            with mock.patch.object(ui_job, "UI_JOBS", root):
                evicted, _ = ui_job.enforce_vision_evidence_quota(
                    100, current_ui_dir=current
                )
            self.assertEqual(evicted, 0)
            self.assertTrue((reconcile / "evidence").exists())


if __name__ == "__main__":
    unittest.main()
