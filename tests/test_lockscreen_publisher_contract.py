from __future__ import annotations

import inspect
import unittest
from pathlib import Path

from publisher import publish_job

ROOT = Path(__file__).resolve().parents[1]


class LockscreenPublisherContractTests(unittest.TestCase):
    def test_secure_unlock_precedes_preflight_and_staging(self) -> None:
        source = inspect.getsource(publish_job.main)
        unlock = source.index("ensure_device_unlocked(args.job_id)")
        preflight = source.index('update("PREFLIGHT"')
        staging = source.index('update("STAGING"')
        self.assertLess(unlock, preflight)
        self.assertLess(preflight, staging)

    def test_preflight_unlock_has_bounded_timeout(self) -> None:
        source = inspect.getsource(publish_job.ensure_device_unlocked)
        self.assertIn("timeout=45", source)
        self.assertIn('update("UNLOCKING", job_id)', source)
        self.assertIn("secure unlock failed before preflight/staging", source)

    def test_stage_media_queries_use_bounded_bridge_timeout(self) -> None:
        source = (ROOT / "publisher" / "stage_job.py").read_text()
        self.assertIn('env["Y700_BRIDGE_TIMEOUT_MS"]', source)
        self.assertIn("timeout_ms=5000", source)
        self.assertIn("subprocess.TimeoutExpired", source)


if __name__ == "__main__":
    unittest.main()
