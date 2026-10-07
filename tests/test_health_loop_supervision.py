import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
HOST = ROOT / "bridge" / "host-executor.sh"
START = ROOT / "scripts" / "start-health-loop.sh"


class HealthLoopSupervisionContractTest(unittest.TestCase):
    def test_host_executor_supervises_health_loop_without_new_daemon(self):
        text = HOST.read_text(encoding="utf-8")
        self.assertIn('HEALTH_LOOP_SUPERVISE_MS="${Y700_HEALTH_LOOP_SUPERVISE_MS:-10000}"', text)
        self.assertIn("ensure_health_loop()", text)
        self.assertIn('DEBIAN_EXEC="${Y700_DEBIAN_EXEC:-/data/local/y700-linux/exec.sh}"', text)
        self.assertIn('DEBIAN_START_HEALTH="${Y700_DEBIAN_START_HEALTH:-/opt/y700/workspaces/y700-agent/scripts/start-health-loop.sh}"', text)
        self.assertIn('\"$DEBIAN_EXEC\" /bin/bash \"$DEBIAN_START_HEALTH\"', text)
        self.assertIn('health-loop supervisor action=', text)
        self.assertIn('*ALREADY_RUNNING*) return 0', text)

    def test_start_health_loop_repairs_stale_pidfile_from_proc(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("process_matches()", text)
        self.assertIn("for proc in /proc/[0-9]*/cmdline", text)
        self.assertIn('RECOVERED_RUNNING pid=$found', text)
        self.assertIn('MULTIPLE_HEALTH_LOOPS', text)
        self.assertLess(
            text.index('RECOVERED_RUNNING pid=$found'),
            text.index('nohup "$SCRIPT"'),
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


if __name__ == "__main__":
    unittest.main()
