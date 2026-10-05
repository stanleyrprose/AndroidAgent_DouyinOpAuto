from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENROLL = ROOT / "scripts" / "enroll-device-unlock-pin.sh"
UNLOCK = ROOT / "bridge" / "secure-unlock.sh"
ANDROIDCTL = ROOT / "bridge" / "androidctl.sh"


class DeviceUnlockContractTests(unittest.TestCase):
    def test_enrollment_never_uses_bridge_for_secret_transport(self) -> None:
        text = ENROLL.read_text()
        self.assertIn("/proc/1/root", text)
        self.assertIn("read -r -s", text)
        self.assertIn("chmod 600", text)
        self.assertNotIn("root-exec.sh", text)

    def test_secret_is_runtime_only_and_not_literal(self) -> None:
        text = UNLOCK.read_text()
        self.assertIn("/data/local/y700-agent/secrets/device_unlock.pin", text)
        self.assertNotIn("device_unlock.pin=", text)
        self.assertIn("DEVICE_UNLOCK_BLOCKED_FAILURE_LATCH", text)

    def test_androidctl_exposes_secure_unlock_without_replacing_legacy_unlock(self) -> None:
        text = ANDROIDCTL.read_text()
        self.assertIn("unlock-secure)", text)
        self.assertIn("unlock-secret-status)", text)
        self.assertIn("wm dismiss-keyguard", text)


if __name__ == "__main__":
    unittest.main()
