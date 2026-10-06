import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

class ResourceArbiterTests(unittest.TestCase):
    def load_ra(self, root):
        with patch.dict(os.environ, {"Y700_RUNTIME": str(root)}, clear=False):
            os.environ.pop("Y700_RESOURCE_DIR", None)
            import automation.resource_arbiter as ra
            return importlib.reload(ra)

    def test_claim_guard_and_stale_claim_id(self):
        with tempfile.TemporaryDirectory() as td:
            ra=self.load_ra(Path(td))
            with ra.acquire_android_ui(owner_kind="LEGACY",owner_id="legacy",backend_job_id="ui-1") as guard:
                ra.assert_guard(guard.as_dict()); old=guard.as_dict()
            with ra.acquire_android_ui(owner_kind="LEGACY",owner_id="legacy",backend_job_id="ui-2") as guard2:
                self.assertNotEqual(guard2.claim_id,old["claim_id"])
                with self.assertRaisesRegex(ra.ResourceError,"RESOURCE_OWNERSHIP_MISMATCH"): ra.assert_guard(old)

    def test_unknown_durable_claim_blocks_new_owner(self):
        with tempfile.TemporaryDirectory() as td:
            ra=self.load_ra(Path(td)); ra.ANDROID_UI_DIR.mkdir(parents=True)
            ra._atomic_json(ra.CLAIM_PATH,{"resource":"android_ui","owner_kind":"LEGACY","owner_id":"old","claim_id":"old-c","backend_job_id":"old-b"})
            with self.assertRaisesRegex(ra.ResourceError,"RESOURCE_RECONCILE_REQUIRED"):
                with ra.acquire_android_ui(owner_kind="LEGACY",owner_id="new",backend_job_id="new-b"): pass

    def test_capability_claim_requires_capability_job(self):
        with tempfile.TemporaryDirectory() as td:
            ra=self.load_ra(Path(td))
            with self.assertRaisesRegex(ra.ResourceError,"CAPABILITY_JOB_ID_REQUIRED"):
                with ra.acquire_android_ui(owner_kind="CAPABILITY",owner_id="x",backend_job_id="b"): pass

if __name__=="__main__": unittest.main()
