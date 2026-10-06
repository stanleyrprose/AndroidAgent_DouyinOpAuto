from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
DRIVER = ROOT / "mac/android-automation/app/src/androidTest/java/com/stanley/y700automation/AutomationInstrumentedTest.java"
OCR = ROOT / "mac/android-automation/app/src/androidTest/java/com/stanley/y700automation/vision/OcrTextLocator.java"
BENCH = ROOT / "mac/android-automation/app/src/debug/java/com/stanley/y700automation/VisionBenchmarkActivity.java"
POLICY = ROOT / "automation/vision_policy.py"


class VisionV3ContractTest(unittest.TestCase):
    def test_semantic_success_returns_before_vision_cascade(self) -> None:
        text = DRIVER.read_text(encoding="utf-8")
        semantic = text.index('.put("locator_source", "semantic")')
        cascade = text.index("return clickVisionCascade")
        self.assertLess(semantic, cascade)

    def test_mixed_fallback_is_template_then_ocr_and_bounded(self) -> None:
        text = DRIVER.read_text(encoding="utf-8")
        self.assertIn("fallback.length() > 8", text)
        self.assertIn("templates.addAll(ocr)", text)
        self.assertNotIn("mixed template+OCR fallback is reserved for Sprint V3", text)

        policy = POLICY.read_text(encoding="utf-8")
        self.assertIn("return [*templates, *ocr]", policy)

    def test_stale_target_reresolve_is_exactly_once_before_input(self) -> None:
        text = DRIVER.read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count("resolveAttempt < 2"), 2)
        self.assertIn("visionStaleReresolveCount++", text)
        self.assertIn("locator.invalidateObservationCache()", text)
        self.assertIn(
            'intent.putExtra("track_click_count", testBenchmarkTrackClickCount)',
            text,
        )

    def test_postcondition_failure_never_becomes_soft_fallback(self) -> None:
        text = DRIVER.read_text(encoding="utf-8")
        soft_start = text.index("private boolean isSoftLocatorMiss")
        soft_end = text.index("private boolean isStaleVisionFailure", soft_start)
        soft = text[soft_start:soft_end]
        self.assertNotIn("POSTCONDITION", soft)
        self.assertNotIn("AMBIGUOUS", soft)
        self.assertIn("VISION_POSTCONDITION_FAILED", text)

    def test_popup_recovery_is_package_bound_and_template_roi_bounded(self) -> None:
        text = DRIVER.read_text(encoding="utf-8")
        self.assertIn('known popup recovery requires expected_package', text)
        self.assertIn('expectedPackage.equals(currentPackage)', text)
        self.assertIn('popup semantic dismiss must be semantic-only', text)
        self.assertIn('popup template recovery requires bounded roi or roi_ratio', text)
        self.assertIn('popups.length() > 4', text)

    def test_ocr_cache_is_package_aware_and_explicitly_invalidatable(self) -> None:
        text = OCR.read_text(encoding="utf-8")
        self.assertIn("sameString(cachedPackage, currentPackage)", text)
        self.assertIn("public synchronized void invalidateObservationCache()", text)
        self.assertIn("cachedPackage = null", text)
        self.assertIn("cachedOcr = null", text)

    def test_gate_can_prove_zero_duplicate_target_click(self) -> None:
        bench = BENCH.read_text(encoding="utf-8")
        driver = DRIVER.read_text(encoding="utf-8")
        self.assertIn('track_click_count', bench)
        self.assertIn('VISION_V3_CLICKED_COUNT_', bench)
        self.assertIn('targetClickCount++', bench)
        self.assertIn('test_benchmark_track_click_count', driver)
        self.assertIn('private boolean trackClickCountMode;', bench)
        self.assertIn('trackClickCountMode = true;', bench)
        self.assertIn('new BenchmarkView(intent, trackClickCountMode)', bench)
        self.assertNotIn(
            'trackClickCount = source.getBooleanExtra("track_click_count", false);',
            bench,
        )

    def test_external_irreversible_vision_remains_blocked(self) -> None:
        text = DRIVER.read_text(encoding="utf-8")
        self.assertIn('"EXTERNAL_IRREVERSIBLE".equals(sideEffect)', text)
        self.assertIn('"BLOCKED"', text)


if __name__ == "__main__":
    unittest.main()
