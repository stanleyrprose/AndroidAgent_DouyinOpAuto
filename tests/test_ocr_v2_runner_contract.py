import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "run_ocr_v2_instrumentation.py"


class OcrV2RunnerContractTest(unittest.TestCase):
    def test_runner_is_allow_listed_and_uses_absolute_android_paths(self):
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("ALLOWED_CLASSES", text)
        self.assertIn("OcrV2ContractTest", text)
        self.assertIn("OcrV2StressTest", text)
        self.assertIn("/system/bin/su 2000 -c", text)
        self.assertIn("/system/bin/am instrument -w -r", text)
        self.assertIn("ocr-v2-evidence", text)
        self.assertIn('all(status == "PASS"', text)

    def test_runner_does_not_accept_arbitrary_class_text(self):
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("choices=sorted(ALLOWED_CLASSES)", text)


if __name__ == "__main__":
    unittest.main()
