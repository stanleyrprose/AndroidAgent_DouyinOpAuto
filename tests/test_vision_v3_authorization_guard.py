from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VisionV3AuthorizationGuardTest(unittest.TestCase):
    def test_android_driver_blocks_multi_candidate_fallback(self) -> None:
        text = (
            ROOT
            / "mac/android-automation/app/src/androidTest/java/com/stanley/"
            "y700automation/AutomationInstrumentedTest.java"
        ).read_text(encoding="utf-8")
        self.assertIn("if (fallback.length() > 1)", text)
        self.assertIn("multi-candidate Vision fallback is not authorized", text)
        self.assertIn("VisionTemplateLocator.ERR_POLICY_BLOCKED", text)

    def test_checkpoint_marks_v3_production_disabled(self) -> None:
        text = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8")
        self.assertIn(
            "Sprint V3 — ENGINEERING EVIDENCE ONLY / PRODUCTION DISABLED",
            text,
        )
        self.assertIn(
            "Hybrid semantic -> template -> OCR routing = DISABLED / NOT AUTHORIZED",
            text,
        )

    def test_v3_docs_do_not_claim_user_authorization(self) -> None:
        impl = (ROOT / "docs/VISION-V3-IMPLEMENTATION.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("PRODUCTION HYBRID ROUTING NOT AUTHORIZED", impl)
        self.assertNotIn("V3 is explicitly authorized by the user", impl)


if __name__ == "__main__":
    unittest.main()
