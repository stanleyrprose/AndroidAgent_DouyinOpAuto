"""Read-only overlay window inventory may never declare no blockers from an empty list."""
import unittest
from pathlib import Path

JAVA = (Path(__file__).resolve().parents[1] / "mac/android-automation/app/src/androidTest/java/"
        "com/stanley/y700automation/vision/Rev37ReadOnlyFrameReceiptInstrumentedTest.java")


class OverlayWindowFactsSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = JAVA.read_text(encoding="utf-8")
        start = src.index("public void readOnlyOverlayWindowFacts()")
        end = src.index("No Android input. Synthetic frame-id mismatch", start)
        cls.source = src[start:end]

    def test_only_observes_window_types_focus_and_activity(self):
        for item in ("getWindows()", "window.getType()", "window.isFocused()",
                     "window.isActive()", "TYPE_APPLICATION", "TYPE_INPUT_METHOD",
                     "TYPE_ACCESSIBILITY_OVERLAY", "TYPE_SYSTEM"):
            self.assertIn(item, self.source)

    def test_zero_window_list_is_unavailable_not_clear(self):
        self.assertIn("windows != null && !windows.isEmpty()", self.source)
        self.assertIn('"READ_ONLY_WINDOW_FACTS_UNAVAILABLE"', self.source)
        self.assertIn('"authoritative_overlay_clear", false', self.source)
        self.assertIn('"blocking_overlay_classification_available", false', self.source)
        self.assertNotIn('"blocking_overlay_present", false', self.source)

    def test_automation_flags_restored(self):
        self.assertIn("priorFlags = serviceInfo.flags", self.source)
        self.assertIn("FLAG_RETRIEVE_INTERACTIVE_WINDOWS", self.source)
        self.assertIn("serviceInfo.flags = priorFlags", self.source)
        self.assertIn("automation.setServiceInfo(serviceInfo)", self.source)
        self.assertIn('"READ_ONLY_WINDOW_FLAGS_RESTORE_FAILED"', self.source)

    def test_no_ui_input_or_persistent_window_contents(self):
        for forbidden in ("device.click(", "device.swipe(", "device.pressBack(",
                          "injectInputEvent(", "takeScreenshot(", "getText(",
                          "getPackageName()", "getRoot()"):
            self.assertNotIn(forbidden, self.source)
        self.assertIn('assertEquals(0, report.getInt("action_attempts"))', self.source)
        self.assertIn('"window_pixels_persisted", false', self.source)


if __name__ == "__main__":
    unittest.main()
