import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
HOST = ROOT / "bridge" / "host-executor.sh"
START = ROOT / "scripts" / "start-health-loop.sh"


class HealthLoopSupervisionContractTest(unittest.TestCase):
    def test_host_executor_no_longer_supervises_health_loop(self):
        text = HOST.read_text(encoding="utf-8")
        self.assertIn('[ -n "$ONESHOT" ] || ONESHOT=1', text)
        self.assertNotIn("ensure_health_loop()", text)
        self.assertNotIn("HEALTH_LOOP_SUPERVISE_MS", text)
        self.assertIn("ON_DEMAND_DEFERRED_SCREEN_OFF", text)

    def test_boot_does_not_start_resident_bridge_or_health_loop(self):
        boot = (ROOT / "scripts" / "boot-start.sh").read_text(encoding="utf-8")
        self.assertNotIn("/runtime/start-host-executor.sh", boot)
        self.assertNotIn("/scripts/start-health-loop.sh", boot)
        self.assertIn("/scripts/start-prod-runtime.sh", boot)

    def test_health_report_accepts_idle_bridge(self):
        health = (ROOT / "scripts" / "health-check.sh").read_text(encoding="utf-8")
        self.assertIn("bridge=IDLE", health)
        self.assertNotIn('[ "$bridge_instances" -ne 1 ]', health)

    def test_start_health_loop_repairs_stale_pidfile_from_proc(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("process_matches()", text)
        self.assertIn("for proc in /proc/[0-9]*/cmdline", text)
        self.assertIn('RECOVERED_RUNNING pid=$found', text)
        self.assertIn('MULTIPLE_HEALTH_LOOPS', text)
        self.assertLess(
            text.index('RECOVERED_RUNNING pid=$found'),
            text.index('nohup /bin/bash "$SCRIPT"'),
        )

    def test_start_health_loop_replaces_live_stale_version(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn('VERSION=/opt/y700/runtime/state/health-loop.version', text)
        self.assertIn('CURRENT_SHA="$(sha256sum "$SCRIPT"', text)
        self.assertIn('version_matches()', text)
        self.assertIn('STALE_HEALTH_LOOP pid=$p', text)
        self.assertIn('stop_stale "$p"', text)
        self.assertIn('HEALTH_LOOP_START_UNVERIFIED', text)

    def test_health_loop_publishes_pid_script_sha_and_heartbeat(self):
        text = (ROOT / "scripts" / "health-loop.sh").read_text(encoding="utf-8")
        self.assertIn('VERSION_STATE="$STATE_DIR/health-loop.version"', text)
        self.assertIn('HEARTBEAT_STATE="$STATE_DIR/health-loop.heartbeat"', text)
        self.assertIn("printf '%s %s\\n'", text)
        self.assertIn("printf '%s %s %s\\n'", text)
        self.assertIn('"$$" "$SCRIPT_SHA"', text)
        self.assertIn('publish_version', text)
        self.assertIn('publish_heartbeat', text)

    def test_supervisor_restarts_live_but_stale_health_loop(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn('HEARTBEAT=/opt/y700/runtime/state/health-loop.heartbeat', text)
        self.assertIn('Y700_HEALTH_LOOP_HEARTBEAT_STALE_SEC:-35', text)
        self.assertIn('heartbeat_fresh()', text)
        self.assertIn('version_matches "$p" && heartbeat_fresh "$p"', text)
        self.assertIn('version_matches "$found" && heartbeat_fresh "$found"', text)

    def test_health_loop_exit_only_removes_its_own_pidfile(self):
        text = (ROOT / "scripts" / "health-loop.sh").read_text(encoding="utf-8")
        self.assertIn("cleanup_pid()", text)
        self.assertIn('owner="$(cat "$PID" 2>/dev/null || true)"', text)
        self.assertIn('if [ "$owner" = "$BASHPID" ]; then', text)
        self.assertIn('trap cleanup_pid EXIT', text)
        self.assertNotIn("trap 'rm -f \"$PID\"' EXIT", text)

    def test_stale_health_loop_escalates_from_term_to_kill(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn('STALE_HEALTH_LOOP_TERM_TIMEOUT pid=$p escalating=KILL', text)
        self.assertIn('kill -KILL "$p"', text)
        self.assertLess(text.index('kill "$p"'), text.index('kill -KILL "$p"'))

    def test_new_health_loop_requires_fresh_heartbeat_before_acceptance(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn(
            'if ! process_matches "$p" || ! version_matches "$p" || ! heartbeat_fresh "$p"; then',
            text,
        )


if __name__ == "__main__":
    unittest.main()
