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
        self.assertIn("OcrV2RealDatasetBenchmarkTest", text)
        self.assertIn("/data/local/y700-agent/workspaces/y700-agent/bridge/android-runtime-env.sh", text)
        self.assertIn("/system/bin/su 2000 -c", text)
        self.assertIn("/system/bin/am instrument -w -r", text)
        self.assertIn("com.stanley.y700automation/files/ocr-v2-evidence", text)
        self.assertIn('all(status == "PASS"', text)

    def test_evidence_uses_target_app_private_directory(self):
        base = (
            ROOT
            / "mac/android-automation/app/src/androidTest/java/com/stanley/y700automation/PersistentOcrV2TestBase.java"
        ).read_text(encoding="utf-8")
        self.assertIn("getTargetContext()", base)
        self.assertNotIn("getInstrumentation().getContext()", base)

    def test_runner_does_not_accept_arbitrary_class_text(self):
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("choices=sorted(ALLOWED_CLASSES)", text)


if __name__ == "__main__":
    unittest.main()
