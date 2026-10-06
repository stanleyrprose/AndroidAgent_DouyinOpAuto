import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
HOST = ROOT / "bridge" / "host-executor.sh"
START = ROOT / "scripts" / "start-health-loop.sh"


class HealthLoopSupervisionContractTest(unittest.TestCase):
    def test_host_executor_supervises_health_loop_without_new_daemon(self):
        text = HOST.read_text(encoding="utf-8")
        self.assertIn('HEALTH_LOOP_SUPERVISE_MS="${Y700_HEALTH_LOOP_SUPERVISE_MS:-60000}"', text)
        self.assertIn("ensure_health_loop()", text)
        self.assertIn('DEBIAN_EXEC="${Y700_DEBIAN_EXEC:-/data/local/y700-linux/exec.sh}"', text)
        self.assertIn('DEBIAN_START_HEALTH="${Y700_DEBIAN_START_HEALTH:-/opt/y700/workspaces/y700-agent/scripts/start-health-loop.sh}"', text)
        self.assertIn('\"$DEBIAN_EXEC\" /bin/bash \"$DEBIAN_START_HEALTH\"', text)
        self.assertIn('health-loop supervisor recovery_start', text)
        self.assertIn('health-loop supervisor recovery_ok', text)

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


if __name__ == "__main__":
    unittest.main()
