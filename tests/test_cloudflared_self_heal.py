from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HEALTH_LOOP = ROOT / "scripts" / "health-loop.sh"
RESTART = ROOT / "bootstrap" / "restart-cloudflared-y700.sh"


class CloudflaredSelfHealContractTests(unittest.TestCase):
    def test_health_loop_restarts_only_when_cloudflared_pid_is_not_live(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn('pid_matches "$CF_PID" cloudflared', text)
        self.assertIn('if ! pid_matches "$CF_PID" cloudflared; then', text)
        self.assertIn('CLOUDFLARED_SELF_HEAL_OK', text)
        self.assertNotIn('pkill cloudflared', text)

    def test_restart_fails_if_spawned_cloudflared_dies(self) -> None:
        text = RESTART.read_text()
        self.assertIn('kill -0 "$new_pid"', text)
        self.assertIn('CLOUDFLARED_START_FAILED', text)
        self.assertIn('/proc/$new_pid/cmdline', text)


if __name__ == "__main__":
    unittest.main()
