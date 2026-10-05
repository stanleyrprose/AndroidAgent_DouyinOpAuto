from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HEALTH_LOOP = ROOT / "scripts" / "health-loop.sh"
HEALTH_CHECK = ROOT / "scripts" / "health-check.sh"
NETWORK = ROOT / "scripts" / "network-status.sh"
RESTART = ROOT / "bootstrap" / "restart-cloudflared-y700.sh"
START_RUNTIME = ROOT / "scripts" / "start-prod-runtime.sh"


class CloudflaredSelfHealContractTests(unittest.TestCase):
    def test_offline_network_suspends_remote_plane_without_restart(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn('write_connectivity_state OFFLINE "$tunnel_process" "$connections" SUSPENDED_NO_NETWORK 0 0', text)
        offline_pos = text.index('if [ "$network" = OFFLINE ]; then')
        resume_pos = text.index('NETWORK_PATH_AVAILABLE mode=$network remote-plane-resume')
        offline = text[offline_pos:resume_pos]
        self.assertNotIn('restart_cloudflared', offline)
        self.assertIn('disconnected_cycles=0', offline)

    def test_metrics_detect_process_alive_but_no_edge_connections(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn('cloudflared_tunnel_ha_connections', text)
        self.assertIn('DISCONNECTED_GRACE_CYCLES', text)
        self.assertIn('disconnected_cycles=$((disconnected_cycles + 1))', text)
        self.assertIn('RECOVERING', text)
        self.assertIn('restart_cloudflared', text)

    def test_online_restart_uses_bounded_exponential_backoff(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn('backoff=$((BASE_BACKOFF_SEC * (1 << shift)))', text)
        self.assertIn('[ "$backoff" -le "$MAX_BACKOFF_SEC" ] || backoff="$MAX_BACKOFF_SEC"', text)
        self.assertIn('next_retry_epoch=$((now + backoff))', text)

    def test_fixed_local_metrics_endpoint_is_configured(self) -> None:
        for path in (RESTART, START_RUNTIME):
            text = path.read_text()
            self.assertIn('--metrics 127.0.0.1:20241', text)

    def test_health_output_includes_connection_count(self) -> None:
        text = HEALTH_CHECK.read_text()
        self.assertIn('"tunnel_connections":int(tunnel_connections)', text)

    def test_network_status_prefers_default_route_and_treats_http_as_advisory(self) -> None:
        text = NETWORK.read_text()
        self.assertIn("ip route show default", text)
        self.assertIn("ONLINE_ROUTE_ONLY", text)
        self.assertIn('https://www.cloudflare.com/cdn-cgi/trace', text)
        self.assertIn('--connect-timeout', text)
        self.assertIn('--max-time', text)

    def test_route_only_state_is_treated_as_recoverable_network(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn('ONLINE|ONLINE_ROUTE_ONLY', text)
        self.assertIn('NETWORK_PATH_AVAILABLE mode=$network', text)

    def test_restart_fails_if_spawned_cloudflared_dies(self) -> None:
        text = RESTART.read_text()
        self.assertIn('kill -0 "$new_pid"', text)
        self.assertIn('CLOUDFLARED_START_FAILED', text)


if __name__ == "__main__":
    unittest.main()
