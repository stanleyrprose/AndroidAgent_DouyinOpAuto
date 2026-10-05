from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HEALTH_LOOP = ROOT / "scripts" / "health-loop.sh"
HEALTH_CHECK = ROOT / "scripts" / "health-check.sh"
NETWORK = ROOT / "scripts" / "network-status.sh"
RESTART = ROOT / "bootstrap" / "restart-cloudflared-y700.sh"


class CloudflaredSelfHealContractTests(unittest.TestCase):
    def test_offline_network_suspends_remote_plane_without_restart(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn('if [ "$network" = OFFLINE ]; then', text)
        self.assertIn('write_connectivity_state OFFLINE "$tunnel_process" SUSPENDED_NO_NETWORK 0 0', text)
        offline_pos = text.index('if [ "$network" = OFFLINE ]; then')
        resume_pos = text.index('NETWORK_ONLINE remote-plane-resume')
        offline = text[offline_pos:resume_pos]
        self.assertNotIn('"$CF_RESTART"', offline)
        self.assertIn('failures=0', offline)
        self.assertIn('next_retry_epoch=0', offline)

    def test_online_dead_tunnel_uses_bounded_exponential_backoff(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn('elif [ "$now" -ge "$next_retry_epoch" ]; then', text)
        self.assertIn('backoff=$((BASE_BACKOFF_SEC * (1 << shift)))', text)
        self.assertIn('[ "$backoff" -le "$MAX_BACKOFF_SEC" ] || backoff="$MAX_BACKOFF_SEC"', text)
        self.assertIn('write_connectivity_state ONLINE OFFLINE BACKOFF', text)

    def test_live_cloudflared_is_not_restarted(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn('if pid_matches "$CF_PID" cloudflared; then', text)
        self.assertNotIn('pkill cloudflared', text)

    def test_health_semantics_keep_local_runtime_healthy_without_network(self) -> None:
        text = HEALTH_CHECK.read_text()
        self.assertIn('"network":network', text)
        self.assertIn('"remote_plane":remote_plane', text)
        self.assertNotIn('[ "$codex" = OFFLINE ] || [ "$bridge" = OFFLINE ]', text)
        self.assertIn('[ "$network" = ONLINE ]', text)

    def test_network_probe_checks_cloudflare_reachability(self) -> None:
        text = NETWORK.read_text()
        self.assertIn('https://www.cloudflare.com/cdn-cgi/trace', text)
        self.assertIn('--connect-timeout', text)
        self.assertIn('--max-time', text)

    def test_restart_fails_if_spawned_cloudflared_dies(self) -> None:
        text = RESTART.read_text()
        self.assertIn('kill -0 "$new_pid"', text)
        self.assertIn('CLOUDFLARED_START_FAILED', text)


if __name__ == "__main__":
    unittest.main()
