import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class AndroidCommandPathContractTest(unittest.TestCase):
    def test_ui_job_uses_absolute_android_su_and_am(self):
        text = (ROOT / "automation" / "ui_job.py").read_text(encoding="utf-8")
        self.assertIn("/data/local/y700-agent/workspaces/y700-agent/bridge/android-runtime-env.sh", text)
        self.assertIn("/system/bin/su 2000 -c", text)
        self.assertIn("/system/bin/am instrument -w -r", text)
        self.assertNotIn("timeout {timeout_sec} su 2000 -c", text)

    def test_android_runtime_env_is_derived_from_zygote(self):
        text = (ROOT / "bridge" / "android-runtime-env.sh").read_text(encoding="utf-8")
        self.assertIn("pidof zygote64", text)
        self.assertIn("BOOTCLASSPATH=\"$(read_env BOOTCLASSPATH)\"", text)
        self.assertIn("DEX2OATBOOTCLASSPATH=\"$(read_env DEX2OATBOOTCLASSPATH)\"", text)
        self.assertIn("ANDROID_RUNTIME_ENV_ZYGOTE_UNAVAILABLE", text)
        self.assertIn("ANDROID_RUNTIME_ENV_MISSING_", text)
        self.assertIn("exec \"$@\"", text)

    def test_androidctl_launch_uses_absolute_android_commands(self):
        text = (ROOT / "bridge" / "androidctl.sh").read_text(encoding="utf-8")
        self.assertIn("/system/bin/cmd package resolve-activity", text)
        self.assertIn("/system/bin/su 2000 -c", text)
        self.assertIn("/system/bin/am start -W", text)


if __name__ == "__main__":
    unittest.main()
