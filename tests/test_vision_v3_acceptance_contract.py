import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "run_vision_v3_acceptance.py"


class VisionV3AcceptanceContractTest(unittest.TestCase):
    def test_runner_covers_frozen_v3_gate(self):
        text = RUNNER.read_text(encoding="utf-8")
        for expected in (
            "semantic_only_no_regression",
            "invalid_recovery_fail_closed",
            "mixed_template_to_ocr",
            "known_popup_recovery",
            "known_popup_template_fallback",
            "stale_target_reresolve",
            "vision_commit_blocked",
            "metadata_only_route_evidence",
            "cold_start_passes",
            "cold_start_total",
            "duplicate_commit_actions",
        ):
            self.assertIn(expected, text)
        self.assertIn("for i in range(20)", text)
        self.assertIn("passes >= 19", text)
        self.assertIn("EXTERNAL_IRREVERSIBLE", text)
        self.assertIn("test_mutate_vision_before_action", text)
        self.assertIn("VISION_V3_POPUP_DISMISS", text)
        self.assertIn("test_benchmark_popup_template", text)
        self.assertIn("fcntl.LOCK_EX | fcntl.LOCK_NB", text)
        self.assertIn("/opt/y700/runtime/vision-v3-acceptance.lock", text)
        self.assertIn("GLOBAL_ACCEPTANCE_LOCK.open", text)
        self.assertNotIn('RUNTIME / ".acceptance.lock"', text)
        self.assertIn("VISION_V3_ACCEPTANCE_ALREADY_RUNNING", text)
        self.assertIn("mixed_route_proved_by_cold = passes > 0", text)
        self.assertIn("metadata_only_evidence_ok(candidate)", text)
        self.assertIn('"mixed_route_proof_source"', text)
        self.assertIn('"evidence_source_job_id"', text)


if __name__ == "__main__":
    unittest.main()
