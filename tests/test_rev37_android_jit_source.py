"""Rev3.7 JIT Android fixture safety + Driver independent hard-stop checks.

These source tests complement actual Android Instrumentation; they do not
claim production D-G3 acceptance or Android live-state SOT observation.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "mac/android-automation/app/src/androidTest/java/"
       "com/stanley/y700automation/vision/Rev37JitFrameGuard.java")
TEST = (ROOT / "mac/android-automation/app/src/androidTest/java/"
        "com/stanley/y700automation/vision/Rev37JitFrameGuardInstrumentedTest.java")
DRIVER = (ROOT / "mac/android-automation/app/src/androidTest/java/"
          "com/stanley/y700automation/AutomationInstrumentedTest.java")
RELEASE = ROOT / "automation/visual_route_gate.py"


class JitFrameGuardSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.java = SRC.read_text(encoding="utf-8")
        cls.tests = TEST.read_text(encoding="utf-8")
        cls.driver = DRIVER.read_text(encoding="utf-8")
        cls.release = RELEASE.read_text(encoding="utf-8")

    def test_fixture_guard_not_production_dispatch_authority(self):
        self.assertIn('public static Verdict verifyForProductionDispatch(', self.java)
        self.assertIn('return denied(CLOSED);', self.java)
        self.assertIn('static Verdict compareFixtureReadOnly(', self.java)
        self.assertIn('.put("production_dispatch_authorized", false)', self.java)
        self.assertIn('.put("dg3_status", "OPEN")', self.java)
        self.assertIn('.put("ui_mutation_attempts", 0)', self.java)
        self.assertIn('DG3_PRODUCTION_ENABLED = False', self.release)

    def test_runtime_driver_remains_separately_closed(self):
        self.assertIn('interactiveVisionMutationRequiresDg3(action)', self.driver)
        self.assertIn('VISION_DRIVER_GATE_CLOSED', self.driver)
        self.assertIn('VISION_DRIVER_GATE_CLOSED', self.java)

    def test_jit_compares_all_critical_dimensions(self):
        for token in (
            '"observed_boot_id"', '"state_epoch"', '"revision"',
            '"display_id"', '"rotation"', '"width"', '"height"',
            '"foreground"', '"package"', '"activity"',
            '"screen_interactive"', '"keyguard_locked"',
            '"blocking_overlay_present"', '"captured_boottime_ms"',
            '"frame_id"', '"locator_contract_version"', '"target_identity"',
            '"max_age_ms"', '"ambiguous"', '"bounds"',
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.java)
        self.assertIn('nowBootMs - captured > fixtureMaxFrameAgeMs', self.java)
        self.assertIn('nowBootMs < captured', self.java)

    def test_no_ui_mutation_apis_in_fixture(self):
        for code in (self.java, self.tests):
            self.assertNotIn('device.click(', code)
            self.assertNotIn('performClick(', code)
            self.assertNotIn('executeShellCommand(', code)
            self.assertNotIn('input tap', code)
            self.assertNotIn('ACTION_DOWN', code)
            self.assertNotIn('pressBack(', code)

    def test_negative_cases_required_in_android_instrumentation(self):
        for test in (
            'expiredFrameAndFutureTimestampRejected',
            'locatorFrameMismatchAndVersionMismatch',
            'rejectBootMismatchEpochAndRevisionAdvance',
            'rejectRotationGeometryDisplayAndForegroundDrift',
            'rejectKeyguardOverlayAndNoninteractive',
            'rejectAmbiguousAndOutOfFrameTarget',
            'frameRouteAgeCannotBeOverridden',
            'malformedOrMissingDataCannotProduceReadOnlyMatch',
            'healthyFixtureReadOnlyButProductionAlwaysBlocked',
        ):
            with self.subTest(test=test):
                self.assertIn('void ' + test + '()', self.tests)


if __name__ == "__main__":
    unittest.main()
