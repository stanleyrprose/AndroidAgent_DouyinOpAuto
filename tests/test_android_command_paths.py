import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class AndroidCommandPathContractTest(unittest.TestCase):
    def test_ui_job_uses_absolute_android_su_and_am(self):
        text = (ROOT / "automation" / "ui_job.py").read_text(encoding="utf-8")
        self.assertIn("/system/bin/su 2000 -c", text)
        self.assertIn("/system/bin/am instrument -w -r", text)
        self.assertNotIn("timeout {timeout_sec} su 2000 -c", text)

    def test_androidctl_launch_uses_absolute_android_commands(self):
        text = (ROOT / "bridge" / "androidctl.sh").read_text(encoding="utf-8")
        self.assertIn("/system/bin/cmd package resolve-activity", text)
        self.assertIn("/system/bin/su 2000 -c", text)
        self.assertIn("/system/bin/am start -W", text)


if __name__ == "__main__":
    unittest.main()
