from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AndroidRuntimeEnvironmentContractTests(unittest.TestCase):
    def test_host_executor_restores_android_init_environment(self) -> None:
        text = (ROOT / "bridge" / "host-executor.sh").read_text()
        self.assertIn("load_android_runtime_environment", text)
        for expected in (
            "export ANDROID_ROOT=/system",
            "export ANDROID_DATA=/data",
            "export ANDROID_ART_ROOT=/apex/com.android.art",
            "export ANDROID_I18N_ROOT=/apex/com.android.i18n",
            "export ANDROID_TZDATA_ROOT=/apex/com.android.tzdata",
        ):
            self.assertIn(expected, text)
        self.assertIn("pidof zygote64", text)
        self.assertIn("/proc/$zygote_pid/environ", text)
        self.assertIn("BOOTCLASSPATH DEX2OATBOOTCLASSPATH", text)
        self.assertIn("SYSTEMSERVERCLASSPATH STANDALONE_SYSTEMSERVER_JARS", text)
        startup_call = text.index("load_android_runtime_environment\nSTARTED_AT")
        protocol_call = text.index("\nwrite_protocol\n", startup_call)
        self.assertLess(startup_call, protocol_call)


if __name__ == "__main__":
    unittest.main()
