from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VisionV3AuthorizationGuardTest(unittest.TestCase):
    def test_android_driver_allows_bounded_multi_candidate_fallback(self) -> None:
        text = (
            ROOT
            / "mac/android-automation/app/src/androidTest/java/com/stanley/"
            "y700automation/AutomationInstrumentedTest.java"
        ).read_text(encoding="utf-8")
        self.assertNotIn("if (fallback.length() > 1)", text)
        self.assertNotIn("multi-candidate Vision fallback is not authorized", text)
        self.assertIn("if (fallback.length() > 8)", text)

    def test_host_validator_accepts_explicit_hybrid_but_defaults_remain_off(self) -> None:
        text = (ROOT / "automation" / "ui_job.py").read_text(encoding="utf-8")
        self.assertNotIn("multi-candidate Vision fallback is not authorized", text)
        policy = (ROOT / "automation" / "vision_policy.py").read_text(encoding="utf-8")
        self.assertIn("vision_enabled: bool = False", policy)
        self.assertIn("ocr_enabled: bool = False", policy)

    def test_checkpoint_records_v3_production_acceptance(self) -> None:
        text = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8")
        self.assertIn(
            "Sprint V3 — PASS / FROZEN / PRODUCTION AUTHORIZED",
            text,
        )
        self.assertIn(
            "Hybrid semantic -> template -> OCR routing = READY / AUTHORIZED WHEN EXPLICITLY REQUESTED",
            text,
        )

    def test_v3_docs_record_explicit_user_authorization(self) -> None:
        impl = (ROOT / "docs/VISION-V3-IMPLEMENTATION.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("PRODUCTION HYBRID ROUTING AUTHORIZED", impl)
        self.assertIn("explicitly authorized by the user on 2026-10-08", impl)


if __name__ == "__main__":
    unittest.main()
