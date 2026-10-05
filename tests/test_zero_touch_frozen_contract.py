from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ZeroTouchFrozenContractTests(unittest.TestCase):
    def test_localization_requires_caption_basis(self) -> None:
        text = (ROOT / "mac/production-pipeline/pipeline/localize.py").read_text()
        self.assertIn("caption_basis", text)
        self.assertIn("schema_version", text)

    def test_atomic_public_commit_entrypoint_exists_and_refuses_blind_retry(self) -> None:
        text = (ROOT / "scripts/approve-public-commit.sh").read_text()
        self.assertIn('READY_TO_COMMIT', text)
        self.assertIn('manifest is already COMMIT; reconcile before any retry', text)
        self.assertIn('"$PUBLISH_ASYNC" "$JOB_ID" --commit', text)

    def test_publication_closure_has_no_publish_capability(self) -> None:
        text = (ROOT / "mac/production-pipeline/scripts/close-y700-publication.sh").read_text()
        self.assertIn("reconcile-public-async.sh", text)
        self.assertIn("PUBLISHED_VERIFIED", text)
        self.assertNotIn("approve-public-commit.sh", text)
        self.assertNotIn("publish-async.sh", text)
        self.assertNotIn("publish_job.py", text)

    def test_telegram_soul_binds_zero_touch_contract(self) -> None:
        text = (ROOT / "config/hermes-y700automation-SOUL.md").read_text()
        self.assertIn("caption_basis", text)
        self.assertIn("approve-public-commit.sh", text)
        self.assertIn("start-publication-closure.sh", text)
        self.assertIn("AMBIGUOUS_COMMIT_NEEDS_RECONCILE", text)


if __name__ == "__main__":
    unittest.main()
