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
        # Single allowed shell read is Android kernel boot_id; no UI command.
        self.assertEqual(self.src.count("executeShellCommand("), 1)
        self.assertIn('executeShellCommand("cat /proc/sys/kernel/random/boot_id")', self.src)
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

    def test_staging_android_variant_does_not_override_debug_app(self):
        gradle = (ROOT / "mac/android-automation/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        self.assertIn('create("dg3Probe")', gradle)
        self.assertIn('applicationIdSuffix = ".dg3probe"', gradle)
        self.assertIn('providers.gradleProperty("rev37Probe")', gradle)
        self.assertIn('testBuildType = "dg3Probe"', gradle)
        self.assertIn('java.srcDir("src/debug/java")', gradle)
        self.assertIn('extendsFrom(configurations.getByName("debugImplementation"))', gradle)
        self.assertIn('applicationId = "com.stanley.y700automation"', gradle)

    def test_bounded_same_frame_candidates_preserve_ambiguity_threshold(self):
        self.assertIn("List<Rect> patches = new ArrayList<>();", self.src)
        self.assertIn("All retries are on the SAME immutable captured frame.", self.src)
        self.assertIn("for (Rect patch : patches)", self.src)
        self.assertIn("VisionV0Harness.ERR_TEMPLATE_AMBIGUOUS", self.src)
        self.assertIn("0.90, 8.0, 0.03", self.src)
        self.assertIn('.put("locator_attempts", attempts)', self.src)
        self.assertIn('.put("ambiguous_candidate_count", ambiguousCount)', self.src)
        self.assertIn("screen_interactive_before_capture", self.src)
        self.assertIn("keyguard_unlocked_before_capture", self.src)

    def test_cross_frame_tiktok_target_probe_is_no_input_and_non_authoritative(self):
        self.assertIn("void readOnlyTikTokCreateCrossFrameLocator()", self.src)
        self.assertIn("void readOnlyBootIdentity()", self.src)
        self.assertIn('device.findObjects(By.desc("创建"))', self.src)
        self.assertIn('device.findObjects(By.text("创建"))', self.src)
        self.assertIn("Bitmap.createBitmap(", self.src)
        self.assertIn("VisionV0Harness.Frame captureA", self.src)
        self.assertIn("VisionV0Harness.Frame captureB", self.src)
        self.assertIn("captureB, reference, roi, false,", self.src)
        self.assertIn("captureA.generation != captureB.generation", self.src)
        self.assertIn("semanticConsistent", self.src)
        self.assertIn('executeShellCommand("cat /proc/sys/kernel/random/boot_id")', self.src)
        self.assertIn('.put("boot_id_consistent", bootSame)', self.src)
        self.assertIn('.put("reference_template_persisted", false)', self.src)
        self.assertIn('READ_ONLY_CROSS_FRAME_TARGET_LOCATED', self.src)
        self.assertIn('READ_ONLY_CROSS_FRAME_CONTEXT_NOT_VERIFIED', self.src)
        self.assertIn('assertFalse(report.optBoolean("production_dg3_passed", true))', self.src)

    def test_driver_mutation_gate_still_hard_closed(self):
        self.assertIn("VISION_DRIVER_GATE_CLOSED", self.driver)
        self.assertIn("interactiveVisionMutationRequiresDg3(action)", self.driver)


if __name__ == "__main__":
    unittest.main()
