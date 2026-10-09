import importlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ResourceArbiterSprint1Tests(unittest.TestCase):
    def load(self, root: Path):
        with patch.dict(os.environ, {"Y700_RUNTIME": str(root)}, clear=False):
            import automation.resource_arbiter as ra
            return importlib.reload(ra)

    def test_uses_frozen_canonical_paths(self):
        with tempfile.TemporaryDirectory() as td:
            ra = self.load(Path(td))
            self.assertEqual(ra.LOCK_PATH, Path(td) / "android-ui.lock")
            self.assertEqual(ra.CLAIM_PATH, Path(td) / "android-ui.claim.json")

    def test_durable_claim_schema_guard_and_release(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ra = self.load(root)
            identity = ra.request_identity({"job": "legacy-1"})
            with ra.acquire_android_ui(
                owner_kind="LEGACY",
                owner_id="legacy:tiktok:test",
                backend_type="tiktok-controller",
                backend_job_id="legacy-1",
                request_sha256=identity,
            ) as guard:
                claim = ra.read_claim()
                self.assertEqual(claim["claim_version"], 1)
                self.assertTrue(claim["claim_id"].startswith("ui-claim-"))
                self.assertEqual(claim["claim_generation"], 1)
                self.assertIsNone(claim["prior_claim_id"])
                self.assertEqual(claim["resource"], "android_ui")
                self.assertEqual(claim["owner_kind"], "LEGACY")
                self.assertEqual(claim["owner_id"], "legacy:tiktok:test")
                self.assertEqual(claim["backend_job_id"], "legacy-1")
                self.assertEqual(claim["request_sha256"], identity)
                self.assertIn("boot_id", claim["owner"])
                self.assertIn("proc_start_ticks", claim["owner"])
                self.assertEqual(ra.assert_guard(guard.as_dict())["claim_id"], guard.claim_id)
                self.assertEqual(stat.S_IMODE(ra.CLAIM_PATH.stat().st_mode), 0o600)
            self.assertIsNone(ra.read_claim())
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)

    def test_reacquire_gets_new_claim_id_and_lineage(self):
        with tempfile.TemporaryDirectory() as td:
            ra = self.load(Path(td))
            args = dict(
                owner_kind="LEGACY",
                owner_id="legacy:tiktok:same",
                backend_type="tiktok-controller",
                request_sha256=ra.request_identity({"same": True}),
            )
            with ra.acquire_android_ui(backend_job_id="run-1", **args) as first:
                old = first.as_dict()
                first_claim = ra.read_claim()
            with ra.acquire_android_ui(backend_job_id="run-2", **args) as second:
                current = ra.read_claim()
                self.assertNotEqual(second.claim_id, old["claim_id"])
                self.assertEqual(current["claim_generation"], 2)
                self.assertEqual(current["prior_claim_id"], first_claim["claim_id"])
                with self.assertRaisesRegex(ra.ResourceError, "RESOURCE_OWNERSHIP_MISMATCH"):
                    ra.assert_guard(old)

    def test_existing_durable_claim_blocks_new_owner(self):
        with tempfile.TemporaryDirectory() as td:
            ra = self.load(Path(td))
            ra._atomic_json(ra.CLAIM_PATH, {
                "claim_version": 1,
                "resource": "android_ui",
                "claim_id": "ui-claim-old",
                "owner_id": "legacy:old",
            })
            with self.assertRaisesRegex(ra.ResourceError, "RESOURCE_RECONCILE_REQUIRED"):
                with ra.acquire_android_ui(
                    owner_kind="LEGACY",
                    owner_id="legacy:new",
                    backend_type="test",
                    backend_job_id="new",
                    request_sha256=ra.request_identity({"new": True}),
                ):
                    pass
            self.assertEqual(ra.read_claim()["claim_id"], "ui-claim-old")

    def test_missing_or_wrong_guard_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ra = self.load(Path(td))
            with self.assertRaisesRegex(ra.ResourceError, "RESOURCE_OWNERSHIP_REQUIRED"):
                ra.assert_guard(None)
            with ra.acquire_android_ui(
                owner_kind="LEGACY",
                owner_id="legacy:x",
                backend_type="test",
                backend_job_id="b",
                request_sha256=ra.request_identity({"x": 1}),
            ) as guard:
                bad = guard.as_dict() | {"claim_id": "ui-claim-stale"}
                with self.assertRaisesRegex(ra.ResourceError, "RESOURCE_OWNERSHIP_MISMATCH"):
                    ra.assert_guard(bad)

    def test_active_execution_binding_is_durable_and_clearable(self):
        with tempfile.TemporaryDirectory() as td:
            ra = self.load(Path(td))
            with ra.acquire_android_ui(
                owner_kind="LEGACY",
                owner_id="legacy:tiktok:binding",
                backend_type="tiktok-controller",
                backend_job_id="lease-1",
                request_sha256=ra.request_identity({"binding": True}),
            ) as guard:
                guard.bind_active_execution(
                    ui_job_id="ui-job-1",
                    session_id="session-1",
                )
                claim = ra.read_claim()
                self.assertEqual(claim["active_ui_job_id"], "ui-job-1")
                self.assertEqual(claim["active_session_id"], "session-1")
                self.assertEqual(claim["active_backend_type"], "ui_job")
                guard.clear_active_execution(ui_job_id="ui-job-1")
                cleared = ra.read_claim()
                self.assertNotIn("active_ui_job_id", cleared)
                self.assertNotIn("active_session_id", cleared)

    def test_retained_claim_keeps_backend_addressability_and_reconcile_reason(self):
        with tempfile.TemporaryDirectory() as td:
            ra = self.load(Path(td))
            with ra.acquire_android_ui(
                owner_kind="LEGACY",
                owner_id="legacy:tiktok:retained",
                backend_type="tiktok-controller",
                backend_job_id="lease-retained",
                request_sha256=ra.request_identity({"retained": True}),
            ) as guard:
                claim_id = guard.claim_id
                guard.bind_active_execution(
                    ui_job_id="ui-job-retained",
                    session_id="session-retained",
                )
                guard.retain_for_reconcile("DRIVER_SESSION_LIVENESS_UNKNOWN")
            retained = ra.read_claim()
            self.assertIsNotNone(retained)
            self.assertEqual(retained["claim_id"], claim_id)
            self.assertTrue(retained["reconcile_required"])
            self.assertEqual(
                retained["reconcile_reason"],
                "DRIVER_SESSION_LIVENESS_UNKNOWN",
            )
            self.assertEqual(retained["active_ui_job_id"], "ui-job-retained")
            self.assertEqual(retained["active_session_id"], "session-retained")
            phases = [
                json.loads(line)["phase"]
                for line in ra.AUDIT_PATH.read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn("RESOURCE_BACKEND_BOUND", phases)
            self.assertIn("RESOURCE_RECONCILE_REQUIRED", phases)
            self.assertNotIn("RESOURCE_RELEASED", phases)


if __name__ == "__main__":
    unittest.main()
