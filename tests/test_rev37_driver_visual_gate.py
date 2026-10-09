"""Rev3.7 driver-side D-G3 gate: static contract until APK bench tests exist."""
import unittest
from pathlib import Path

DRIVER = Path(__file__).resolve().parents[1] / (
    "mac/android-automation/app/src/androidTest/java/"
    "com/stanley/y700automation/AutomationInstrumentedTest.java"
)


class DriverGateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DRIVER.read_text(encoding="utf-8")

    def test_interactive_gate_runs_before_java_action_dispatch(self):
        interactive_start = self.text.index("private void runInteractiveCoreV2(")
        interactive_end = self.text.index("private JSONObject ensureUiPreflight(")
        section = self.text[interactive_start:interactive_end]
        self.assertIn("interactiveVisionMutationRequiresDg3(action)", section)
        self.assertIn("VISION_DRIVER_GATE_CLOSED", section)
        self.assertIn('.put("attempts", 0)', section)
        self.assertLess(
            section.index("interactiveVisionMutationRequiresDg3(action)"),
            section.index("executeWithRetry(action, actionIndex)"),
        )

    def test_gate_includes_implicit_template_ocr_and_popup_recovery(self):
        start = self.text.index("private boolean interactiveVisionMutationRequiresDg3(")
        end = self.text.index("private boolean isMutationAction(", start)
        section = self.text[start:end]
        self.assertIn("isMutationAction", section)
        for term in ("vision_recovery", "vision_template", "vision_text", "fallback", "VISION_ASSISTED_UI"):
            self.assertIn(term, section)
        self.assertNotIn('dg3_accepted', section)
        self.assertNotIn("optBoolean", section)

    def test_legacy_benchmark_action_path_stays_independent(self):
        start = self.text.index("if (request.optBoolean(\"interactive_core_v2\", false))")
        tail = self.text[start:self.text.index("JSONArray actions = request.optJSONArray", start)]
        self.assertIn("runInteractiveCoreV2(request, result, workflowStart)", tail)


if __name__ == "__main__":
    unittest.main()
