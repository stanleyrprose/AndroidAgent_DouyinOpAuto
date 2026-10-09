from __future__ import annotations

import inspect
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_secure_unlock_holds_canonical_claim_and_invalidates_epoch_first(self) -> None:
        events: list[str] = []

        @contextmanager
        def fake_claim(**kwargs):
            events.append("claim_enter")
            try:
                yield SimpleNamespace()
            finally:
                events.append("claim_exit")

        def fake_run(cmd, **kwargs):
            events.append("run")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with (
            patch.object(publish_job, "update", side_effect=lambda *a, **k: {}),
            patch.object(
                publish_job.resource_arbiter,
                "acquire_android_ui",
                side_effect=fake_claim,
            ),
            patch.object(
                publish_job.state_integrity,
                "bump_epoch",
                side_effect=lambda reason: events.append("epoch") or {},
            ),
            patch.object(publish_job, "run", side_effect=fake_run),
        ):
            publish_job.ensure_device_unlocked("job-1")

        self.assertEqual(
            events,
            ["claim_enter", "epoch", "run", "claim_exit"],
        )

    def test_stage_media_queries_use_bounded_bridge_timeout(self) -> None:
        source = (ROOT / "publisher" / "stage_job.py").read_text()
        self.assertIn('env["Y700_BRIDGE_TIMEOUT_MS"]', source)
        self.assertIn("timeout_ms=5000", source)
        self.assertIn("subprocess.TimeoutExpired", source)


if __name__ == "__main__":
    unittest.main()
