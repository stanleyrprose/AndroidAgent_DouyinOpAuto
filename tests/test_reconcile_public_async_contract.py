from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reconcile-public-async.sh"


class ReconcilePublicAsyncContractTests(unittest.TestCase):
    def test_wrapper_is_detached_and_reconciliation_only(self) -> None:
        text = SCRIPT.read_text()
        self.assertIn("nohup bash -c", text)
        self.assertIn("publisher/reconcile_public.py", text)
        self.assertIn('"$root/bridge/androidctl.sh" unlock-secure', text)
        self.assertIn("screen_off_timeout 300000", text)
        self.assertIn("trap restore_timeout EXIT", text)
        self.assertIn('"action":"RECONCILE_ONLY"', text)
        self.assertNotIn("publish-async.sh", text)
        self.assertNotIn("publisher/publish_job.py", text)
        self.assertNotIn("--commit", text)

    def test_wrapper_is_idempotent_for_published_and_running_jobs(self) -> None:
        text = SCRIPT.read_text()
        self.assertIn("ALREADY_PUBLISHED", text)
        self.assertIn("ALREADY_RUNNING", text)
        self.assertIn("reconcile.pid", text)


if __name__ == "__main__":
    unittest.main()
