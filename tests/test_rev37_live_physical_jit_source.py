"""D-G3 live Android physical JIT negative-only boundary source guards."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / ("mac/android-automation/app/src/androidTest/java/"
               "com/stanley/y700automation/vision/"
               "Rev37ReadOnlyFrameReceiptInstrumentedTest.java")


class LivePhysicalJitSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = JAVA.read_text(encoding="utf-8")
        start = src.index("public void readOnlyLivePhysicalJitFailClosed()")
        end = src.index("/** No Android input. Synthetic frame-id mismatch", start)
        cls.method = src[start:end]

    def test_actual_screenshot_and_clock_age(self):
        self.assertIn("VisionV0Harness.capture(", self.method)
        self.assertIn("frameStartNs / NS_PER_MS", self.method)
        self.assertIn("SystemClock.elapsedRealtimeNanos() / NS_PER_MS", self.method)
        self.assertIn("SystemClock.sleep(fixtureMaxAgeMs + 180L)", self.method)
        self.assertIn("real_elapsed_frame_age_ms", self.method)
        self.assertIn("age > fixtureMaxAgeMs", self.method)

    def test_device_fields_reread_independently(self):
        for word in ("readBootId(instrumentation)", "device.getDisplayRotation()",
                     "device.getCurrentPackageName()", "keyguard.isKeyguardLocked()",
                     "power.isInteractive()", "device.getDisplayWidth()",
                     "device.getDisplayHeight()"):
            self.assertIn(word, self.method)

    def test_missing_authority_unavailable_is_explicit(self):
        for word in ('"semantic_sot_readable", false',
                     '"overlay_classification_verified", false',
                     '"foreground_activity_verified", false',
                     '"fixture_fields_not_authority", true',
                     '"pixel_locator_verified", false',
                     '"SYNTHETIC_CENTRE_REGION_NOT_SEMANTIC"'):
            self.assertIn(word, self.method)
        self.assertIn("epoch-fixture-NOT-SOT", self.method)
        self.assertIn("blocking_overlay_present", self.method)

    def test_failure_codes_and_gate_must_remain_closed(self):
        self.assertIn('Rev37JitFrameGuard.LOCATOR_MISMATCH', self.method)
        self.assertIn('Rev37JitFrameGuard.STALE.equals(withoutSot.code)', self.method)
        self.assertIn('Rev37JitFrameGuard.STALE.equals(stale.code)', self.method)
        self.assertIn('READ_ONLY_REAL_CONTEXT_DRIFT_BLOCKED', self.method)
        self.assertIn('verifyForProductionDispatch(', self.method)
        self.assertIn('assertFalse(report.optBoolean("production_dg3_passed", true))',
                      self.method)
        self.assertIn('assertFalse(report.optBoolean("visual_dispatch_allowed", true))',
                      self.method)
        self.assertIn('assertEquals(0, report.getInt("action_attempts"))',
                      self.method)

    def test_no_input_injection_or_target_misrepresentation(self):
        for forbidden in ('device.click(', 'device.swipe(', 'device.pressBack(',
                          'getUiAutomation().injectInputEvent(', 'performClick(',
                          'READ_ONLY_CROSS_FRAME_TARGET_LOCATED'):
            self.assertNotIn(forbidden, self.method)


if __name__ == "__main__":
    unittest.main()
