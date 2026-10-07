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
START_HEALTH = ROOT / "scripts" / "start-health-loop.sh"


class CloudflaredSelfHealContractTests(unittest.TestCase):
    def test_remote_probe_is_authoritative_even_when_local_connections_are_stale(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn("network=UNKNOWN", text)
        self.assertIn('remote_probe_ready "$probe_http"', text)
        self.assertIn("200|204) return 0", text)
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

    def test_prod_runtime_holds_kernel_wakelock_for_remote_control(self) -> None:
        text = START_RUNTIME.read_text()
        self.assertIn("Y700_REMOTE_WAKE_LOCK_NAME:-y700-remote-control", text)
        self.assertIn("WAKE_LOCK=/sys/power/wake_lock", text)
        self.assertIn("WAKE_UNLOCK=/sys/power/wake_unlock", text)
        self.assertIn("acquire_remote_wake_lock", text)
        self.assertIn("REMOTE_WAKE_LOCK_ACQUIRE_FAILED", text)
        self.assertIn("release_wake_lock_on_failure", text)

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
        self.assertIn("next_retry_epoch=0", text)
        self.assertIn('required_grace_cycles="$DISCONNECTED_GRACE_CYCLES"', text)
        self.assertIn('if [ "$disconnected_cycles" -lt "$required_grace_cycles" ]; then', text)
        self.assertLess(
            text.index("NETWORK_PATH_AVAILABLE mode=$network"),
            text.index('if [ "$disconnected_cycles" -lt "$required_grace_cycles" ]; then'),
        )

    def test_connectivity_loop_is_decoupled_and_bounded(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn("Y700_HEALTH_LOOP_INTERVAL_SEC:-10", text)
        self.assertIn("Y700_HEALTH_CHECK_INTERVAL_SEC:-60", text)
        self.assertIn("Y700_HEALTH_CHECK_TIMEOUT_SEC:-10", text)
        self.assertIn('if [ "$remote_ready" -eq 1 ]', text)
        self.assertIn('timeout --signal=TERM "$HEALTH_CHECK_TIMEOUT_SEC"', text)
        self.assertIn('sleep "$LOOP_INTERVAL_SEC"', text)

    def test_remote_plane_retry_budget_is_bounded_for_control_plane_slo(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn("Y700_CLOUDFLARED_BACKOFF_BASE_SEC:-15", text)
        self.assertIn("Y700_CLOUDFLARED_BACKOFF_MAX_SEC:-30", text)
        self.assertIn("Y700_CLOUDFLARED_DISCONNECTED_GRACE_CYCLES:-1", text)
        self.assertIn("Y700_CLOUDFLARED_REMOTE_VERIFY_ATTEMPTS:-3", text)
        self.assertIn("Y700_CLOUDFLARED_REMOTE_VERIFY_DELAY_SEC:-2", text)

    def test_health_check_does_not_depend_on_bridge_root_exec(self) -> None:
        text = HEALTH_CHECK.read_text()
        self.assertNotIn("bridge/root-exec.sh", text)
        self.assertIn("/sys/class/power_supply/battery/temp", text)

    def test_health_loop_invokes_restart_via_bash(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn('/bin/bash "$CF_RESTART"', text)

    def test_restart_helper_is_executable(self) -> None:
        self.assertTrue(os.access(RESTART, os.X_OK))

    def test_health_loop_script_is_executable(self) -> None:
        self.assertTrue(os.access(HEALTH_LOOP, os.X_OK))

    def test_health_loop_launcher_is_mode_independent(self) -> None:
        text = START_HEALTH.read_text()
        self.assertIn('nohup /bin/bash "$SCRIPT"', text)

    def test_restart_bounded_stop_escalates_stalled_old_process(self) -> None:
        text = RESTART.read_text()
        self.assertIn("pid_is_cloudflared", text)
        self.assertIn('kill -TERM "$old"', text)
        self.assertIn("CLOUDFLARED_STOP_ESCALATE", text)
        self.assertIn('kill -KILL "$old"', text)
        self.assertIn("CLOUDFLARED_STOP_FAILED", text)
        self.assertLess(
            text.index('kill -KILL "$old"'),
            text.index("nohup /root/.codexpro/bin/cloudflared"),
        )

    def test_restart_never_kills_pidfile_process_without_cloudflared_identity(self) -> None:
        text = RESTART.read_text()
        self.assertIn("CLOUDFLARED_PID_MISMATCH", text)
        self.assertIn("/root/.codexpro/bin/cloudflared", text)

    def test_restart_fails_if_spawned_cloudflared_dies(self) -> None:
        text = RESTART.read_text()
        self.assertIn('kill -0 "$new_pid"', text)
        self.assertIn("CLOUDFLARED_START_FAILED", text)

    def test_health_loop_self_updates_after_stable_release_change(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn('SCRIPT_SHA="$(sha256sum "$SCRIPT_PATH"', text)
        self.assertIn("maybe_self_update", text)
        self.assertIn("HEALTH_LOOP_SELF_UPDATE", text)
        self.assertIn('exec /bin/bash "$SCRIPT_PATH"', text)
        self.assertLess(text.index("maybe_self_update\n  publish_heartbeat"), text.index('network="$("$NETWORK_STATUS"'))

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
