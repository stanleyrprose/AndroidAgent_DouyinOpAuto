from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HEALTH_LOOP = ROOT / "scripts" / "health-loop.sh"
HEALTH_CHECK = ROOT / "scripts" / "health-check.sh"
NETWORK = ROOT / "scripts" / "network-status.sh"
RESTART = ROOT / "bootstrap" / "restart-cloudflared-y700.sh"
START_RUNTIME = ROOT / "scripts" / "start-prod-runtime.sh"


class CloudflaredSelfHealContractTests(unittest.TestCase):
    def test_remote_probe_is_authoritative_even_when_local_connections_are_stale(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn("network=UNKNOWN", text)
        self.assertIn('remote_probe_ready "$probe_http"', text)
        self.assertIn("000|530) return 1", text)
        self.assertIn('write_connectivity_state "$network" "$tunnel_process" "$connections" READY 0 0 "$probe_http"', text)
        self.assertNotIn('if [ "$connections" -gt 0 ]; then', text)

    def test_restart_is_not_accepted_until_remote_plane_is_ready(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn("wait_remote_ready", text)
        self.assertIn("CLOUDFLARED_SELF_HEAL_OK connections=$connections probe_http=$probe_http", text)
        self.assertIn("schedule_backoff", text)

    def test_unknown_network_still_triggers_bounded_recovery(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn("disconnected_cycles=$((disconnected_cycles + 1))", text)
        self.assertIn("restart_cloudflared", text)
        self.assertIn("SUSPENDED_NO_NETWORK", text)

    def test_metrics_detect_process_alive_but_no_edge_connections(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn("cloudflared_tunnel_ha_connections", text)
        self.assertIn("DISCONNECTED_GRACE_CYCLES", text)
        self.assertIn("RECOVERING", text)
        self.assertIn("restart_cloudflared", text)

    def test_online_restart_uses_bounded_exponential_backoff(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn("backoff=$((BASE_BACKOFF_SEC * (1 << shift)))", text)
        self.assertIn('[ "$backoff" -le "$MAX_BACKOFF_SEC" ] || backoff="$MAX_BACKOFF_SEC"', text)
        self.assertIn("next_retry_epoch=$((now + backoff))", text)

    def test_fixed_local_metrics_endpoint_is_configured(self) -> None:
        for path in (RESTART, START_RUNTIME):
            text = path.read_text()
            self.assertIn("--metrics 127.0.0.1:20241", text)

    def test_health_output_includes_connection_count(self) -> None:
        text = HEALTH_CHECK.read_text()
        self.assertIn('"tunnel_connections":int(tunnel_connections)', text)

    def test_network_status_prefers_real_http_probe_before_route_fallback(self) -> None:
        text = NETWORK.read_text()
        self.assertIn("ip route show default", text)
        self.assertIn("ONLINE_ROUTE_ONLY", text)
        self.assertIn("https://www.cloudflare.com/cdn-cgi/trace", text)
        self.assertIn("--connect-timeout", text)
        self.assertIn("--max-time", text)
        self.assertLess(text.index("if http_probe_ok; then"), text.index("if has_default_route; then"))

    def test_offline_state_does_not_burn_restart_backoff(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn('ONLINE|ONLINE_ROUTE_ONLY|OFFLINE', text)
        self.assertIn('elif [ "$network" = OFFLINE ]; then', text)
        self.assertIn("SUSPENDED_NO_NETWORK", text)
        self.assertIn('write_connectivity_state "$network" "$tunnel_process" "$connections" SUSPENDED_NO_NETWORK 0 0', text)

    def test_network_recovery_bypasses_stale_backoff(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn("path_recovered=1", text)
        self.assertIn('disconnected_cycles="$DISCONNECTED_GRACE_CYCLES"', text)
        self.assertLess(
            text.index("NETWORK_PATH_AVAILABLE mode=$network"),
            text.index('if [ "$disconnected_cycles" -lt "$DISCONNECTED_GRACE_CYCLES" ]'),
        )

    def test_connectivity_loop_is_decoupled_from_full_health_check(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn("Y700_HEALTH_LOOP_INTERVAL_SEC:-15", text)
        self.assertIn("Y700_HEALTH_CHECK_INTERVAL_SEC:-60", text)
        self.assertIn('if [ "$remote_ready" -eq 1 ]', text)
        self.assertIn('sleep "$LOOP_INTERVAL_SEC"', text)

    def test_restart_fails_if_spawned_cloudflared_dies(self) -> None:
        text = RESTART.read_text()
        self.assertIn('kill -0 "$new_pid"', text)
        self.assertIn("CLOUDFLARED_START_FAILED", text)

    def test_health_loop_self_updates_after_stable_release_change(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn('SCRIPT_SHA="$(sha256sum "$SCRIPT_PATH"', text)
        self.assertIn("maybe_self_update", text)
        self.assertIn("HEALTH_LOOP_SELF_UPDATE", text)
        self.assertIn('exec "$SCRIPT_PATH"', text)
        self.assertLess(text.index("maybe_self_update\n  now="), text.index('network="$("$NETWORK_STATUS"'))

    def _run_network_status(self, curl_ok: bool, route_ok: bool) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp)
            (fake / "curl").write_text("#!/bin/sh\nexit %d\n" % (0 if curl_ok else 1))
            route = "echo 'default via 192.0.2.1 dev wlan0'\n" if route_ok else "true\n"
            (fake / "ip").write_text("#!/bin/sh\n" + route)
            os.chmod(fake / "curl", 0o755)
            os.chmod(fake / "ip", 0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fake}:/usr/bin:/bin"
            return subprocess.run(
                ["bash", str(NETWORK)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

    def test_network_status_runtime_http_success_without_default_route(self) -> None:
        result = self._run_network_status(curl_ok=True, route_ok=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "ONLINE")

    def test_network_status_runtime_route_only_fallback(self) -> None:
        result = self._run_network_status(curl_ok=False, route_ok=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "ONLINE_ROUTE_ONLY")

    def test_network_status_runtime_offline(self) -> None:
        result = self._run_network_status(curl_ok=False, route_ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.strip(), "OFFLINE")


if __name__ == "__main__":
    unittest.main()
