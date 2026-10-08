"""Rev3.7 real Android read-only context probe parsing and fail-closed tests."""
import importlib.util
import json
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/v07/probe-android-frame-context.py"
spec = importlib.util.spec_from_file_location("rev37_context_probe", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def context(phase="PRE", *, boot="12345678-aaaa-bbbb-cccc-123456789012",
            rotation=1, geometry="3040x1904", foreground="com.example/.MainActivity",
            power="Awake", restricted="false", uptime="100.00") -> str:
    return (
        f"PHASE={phase}\n"
        f"BOOT={boot}\n"
        f"UPTIME={uptime} 300.00\n"
        f"WINDOW=init=1904x3040 440dpi cur={geometry} app=3040x1904\n"
        f"ROTATION=mDisplayRotation=ROTATION_{rotation * 90}\n"
        f"FOREGROUND=    topResumedActivity=ActivityRecord{{abcd u0 {foreground} t123, isEmbedded=false}}\n"
        f"WAKE=mWakefulness={power}\n"
        f"INPUT_RESTRICTED=mInputRestricted={restricted}\n"
    )


def sample(**post_overrides):
    post_overrides.setdefault("uptime", "102.20")
    return (
        context() +
        "CAPTURE_START=101.50 300.00\n"
        "CAPTURE_END=102.00 300.00\n"
        "CAPTURE_RC=0\n" +
        context("POST", **post_overrides)
    )


class DeviceContextProbeTests(unittest.TestCase):
    def test_read_only_command_no_pixel_persistence_or_input(self):
        script = probe.android_read_only_command()
        self.assertIn("screencap -p >/dev/null", script)
        self.assertIn("/proc/sys/kernel/random/boot_id", script)
        self.assertIn("/proc/uptime", script)
        self.assertIn("mDisplayRotation", script)
        self.assertIn("topResumedActivity", script)
        for forbidden in ("input tap", "input swipe", "am start", "uiautomator dump", "screencap -p /", "pm install"):
            self.assertNotIn(forbidden, script)

    def test_stable_device_capture_returns_advisory_only(self):
        result = probe.parse_context_probe(sample())
        self.assertEqual(result["status"], "OBSERVED_READ_ONLY")
        self.assertIs(result["context_stable"], True)
        self.assertEqual(result["capture_ms"], 500)
        self.assertEqual(result["post_capture_context_ms"], 200)
        self.assertEqual(result["pre_capture_context_ms"], 1500)
        self.assertFalse(result["production_gate_passed"])
        self.assertFalse(result["visual_dispatch_allowed"])
        self.assertFalse(result["frame_token_issued"])
        self.assertFalse(result["keyguard_unlocked_verified"])
        self.assertFalse(result["state_epoch_revision_observed"])
        self.assertEqual(result["ui_mutation_attempts"], 0)
        self.assertNotIn("com.example", json.dumps(result))

    def test_screen_drift_detected_without_actions(self):
        result = probe.parse_context_probe(sample(foreground="com.other/.Detail"))
        self.assertIs(result["context_stable"], False)
        self.assertEqual(result["context_drift_fields"], ["foreground"])
        self.assertEqual(result["ui_mutation_attempts"], 0)

    def test_rotation_geometry_and_lockscreen_drift_detected(self):
        result = probe.parse_context_probe(sample(
            rotation=0, geometry="1904x3040", restricted="true", power="Asleep"
        ))
        self.assertEqual(
            result["context_drift_fields"],
            ["rotation", "display_geometry", "wake", "input_restricted"],
        )
        self.assertFalse(result["screen_interactive_post"])
        self.assertFalse(result["visual_dispatch_allowed"])

    def test_invalid_boot_rejected(self):
        with self.assertRaisesRegex(probe.ContextProbeError, "FRAME_BOOT_MISMATCH"):
            probe.parse_context_probe(sample(boot="abcdef12-aaaa-bbbb-cccc-123456789012"))

    def test_malformed_capture_and_wrong_time_order_rejected(self):
        for row in (
            sample().replace("CAPTURE_RC=0", "CAPTURE_RC=1"),
            sample().replace("CAPTURE_END=102.00", "CAPTURE_END=103.00"),
            sample().replace("CAPTURE_START=101.50", "CAPTURE_START=90.00"),
            sample().replace("ROTATION=mDisplayRotation=ROTATION_90", "ROTATION=not-supported"),
            sample() + "FOREGROUND=duplicate\n",
            sample().replace("PHASE=POST", "PHASE=PRE"),
        ):
            with self.subTest(case=row[-90:]):
                with self.assertRaises(probe.ContextProbeError):
                    probe.parse_context_probe(row)

    def test_no_raw_foreground_in_output_and_no_implicit_dg3_pass(self):
        result = probe.parse_context_probe(sample(foreground="com.secret.app/.Private"))
        rendered = json.dumps(result)
        self.assertNotIn("com.secret", rendered)
        self.assertIn('"dg3_status": "OPEN"', rendered)
        self.assertIn('"frame_age_at_locator_ms": "NOT_MEASURED"', rendered)


if __name__ == "__main__":
    unittest.main()
