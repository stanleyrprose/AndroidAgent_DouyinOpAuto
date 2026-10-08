"""Read-only frame probe parser regressions (no Android calls)."""
import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/v07/probe-android-frame-latency.py"
spec = importlib.util.spec_from_file_location("frame_latency_probe", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class FrameLatencyProbeTests(unittest.TestCase):
    SAMPLE_TEXT = (
        "SAMPLE 0 100.00 100.30 0\n"
        "SAMPLE 1 100.32 100.58 0\n"
        "SAMPLE 2 100.61 100.90 0\n"
    )

    def test_parser_only_accepts_monotonic_successful_capture(self):
        self.assertEqual(probe.parse_probe_output(self.SAMPLE_TEXT, 3), [300, 260, 290])

    def test_reject_failure_and_corrupt_or_incomplete_sample(self):
        cases = (
            self.SAMPLE_TEXT.replace("100.30 0", "100.30 1"),
            self.SAMPLE_TEXT.replace("SAMPLE 2", "SAMPLE 3"),
            self.SAMPLE_TEXT.replace("100.61", "100.51"),
            self.SAMPLE_TEXT.replace("100.90", "100.60"),
            "SAMPLE 0 100.00 100.30 0\n",
            self.SAMPLE_TEXT + "some unsolicited output\n",
        )
        for text in cases:
            with self.subTest(text=text):
                with self.assertRaises(probe.CaptureProbeError):
                    probe.parse_probe_output(text, 3)

    def test_count_limit_and_no_on_device_artifacts(self):
        for count in (2, 31, -1, True):
            with self.assertRaises(probe.CaptureProbeError):
                probe.build_android_probe(count)
        cmd = probe.build_android_probe(20)
        self.assertIn("screencap -p >/dev/null", cmd)
        self.assertIn("read start unused < /proc/uptime", cmd)
        self.assertIn("BOOT_CHANGED", cmd)
        self.assertNotIn("input tap", cmd)
        self.assertNotIn("rm -", cmd)

    def test_dg3_remains_open_even_with_valid_samples(self):
        fake = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=self.SAMPLE_TEXT, stderr=""
        )
        with mock.patch.object(probe.subprocess, "run", return_value=fake) as run:
            row = probe.run_probe(3)
        self.assertEqual(row["status"], "MEASURED_READ_ONLY")
        self.assertIs(row["production_gate_passed"], False)
        self.assertEqual(row["capture_ms"]["p95_nearest_rank"], 300)
        self.assertEqual(row["capture_ms"]["median"], 290)
        self.assertEqual(row["ui_mutation_attempts"], 0)
        self.assertEqual(row["frame_age_at_dispatch_ms"], "NOT_MEASURED")
        self.assertEqual(row["pixel_retention"], "NONE")
        self.assertEqual(run.call_args.args[0][0], "bash")

    def test_bridge_error_fails_closed(self):
        fake = subprocess.CompletedProcess(
            args=[], returncode=42, stdout="BOOT_CHANGED", stderr=""
        )
        with mock.patch.object(probe.subprocess, "run", return_value=fake):
            with self.assertRaisesRegex(probe.CaptureProbeError, "CAPTURE_PROBE_HOST_FAILED"):
                probe.run_probe(3)


if __name__ == "__main__":
    unittest.main()
