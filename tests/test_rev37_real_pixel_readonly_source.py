"""Sprint 1A static safety checks for read-only real-pixel Android test.

Full behavior and OpenCV implementation must be verified by compiled Android
instrumentation at a later isolated deployment; these tests never claim D-G3.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / ("mac/android-automation/app/src/androidTest/java/"
               "com/stanley/y700automation/vision/"
               "Rev37ReadOnlyFrameReceiptInstrumentedTest.java")
DRIVER = ROOT / ("mac/android-automation/app/src/androidTest/java/"
                 "com/stanley/y700automation/"
                 "AutomationInstrumentedTest.java")


class RealPixelReadOnlySourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = TEST.read_text(encoding="utf-8")
        cls.driver = DRIVER.read_text(encoding="utf-8")

    def test_new_entrypoint_separate_from_mutating_benchmark(self):
        self.assertIn("class Rev37ReadOnlyFrameReceiptInstrumentedTest", self.src)
        self.assertIn("void readOnlyPixelBoundLocator()", self.src)
        self.assertNotIn("runVisionV0Benchmark", self.src)
        self.assertNotIn("launchBenchmarkActivity", self.src)

    def test_no_android_input_wake_unlock_or_screenshot_storage(self):
        self.assertNotRegex(self.src, r"\bdevice\.(click|swipe|pressBack|pressHome|wakeUp)\s*\(")
        self.assertNotIn("dismiss-keyguard", self.src)
        self.assertNotIn("executeShellCommand", self.src)
        self.assertNotIn("FileOutputStream", self.src)
        self.assertNotIn(".compress(", self.src)
        self.assertNotIn("Intent(", self.src)

    def test_exact_capture_binding_and_bootclock_age(self):
        self.assertIn("VisionV0Harness.capture(instrumentation, device, null, 0L)", self.src)
        self.assertIn("VisionV0Harness.matchTemplate(", self.src)
        self.assertIn("target.frameGeneration == receipt.generation", self.src)
        self.assertIn("sameFrameId(receipt.frameId, locatorFrameId)", self.src)
        self.assertIn("SystemClock.elapsedRealtimeNanos()", self.src)
        self.assertIn("(observedNs - captureStartNs)", self.src)
        self.assertIn("candidate.recycle()", self.src)
        self.assertIn("template.recycle()", self.src)

    def test_report_explicitly_denies_production_and_hides_pixels(self):
        self.assertIn('.put("production_dg3_passed", false)', self.src)
        self.assertIn('.put("visual_dispatch_allowed", false)', self.src)
        self.assertIn('.put("action_attempts", 0)', self.src)
        self.assertIn('.put("pixel_persisted", false)', self.src)
        self.assertIn('.put("semantic_epoch_revision_verified", false)', self.src)
        self.assertIn('.put("blocking_overlay_verified", false)', self.src)
        self.assertNotRegex(self.src, r'\.put\("frame_fingerprint"')
        self.assertNotRegex(self.src, r'\.put\("target_bounds"')

    def test_driver_mutation_gate_still_hard_closed(self):
        self.assertIn("VISION_DRIVER_GATE_CLOSED", self.driver)
        self.assertIn("interactiveVisionMutationRequiresDg3(action)", self.driver)


if __name__ == "__main__":
    unittest.main()
