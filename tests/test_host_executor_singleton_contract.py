from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class HostExecutorSingletonContractTests(unittest.TestCase):
    def test_executor_owns_atomic_singleton_lock_and_pidfile(self) -> None:
        text = (ROOT / "bridge" / "host-executor.sh").read_text()
        self.assertIn('LOCK_DIR="$RUNTIME/host-executor.lock"', text)
        self.assertIn("acquire_singleton", text)
        self.assertIn("duplicate_executor_exit", text)
        self.assertIn("$PIDFILE.tmp.$$", text)
        self.assertLess(text.index("acquire_singleton"), text.rindex('STARTED_AT="$(now_iso)"'))
        self.assertIn("trap release_singleton EXIT", text)
        self.assertIn("trap 'exit 143' TERM", text)
        self.assertNotIn("trap release_singleton EXIT HUP INT TERM", text)

    def test_restart_kills_all_matching_old_executors_not_only_pidfile(self) -> None:
        text = (ROOT / "scripts" / "restart-host-executor.sh").read_text()
        self.assertIn("for proc in /proc/[0-9]*", text)
        self.assertIn("/bridge/host-executor.sh", text)
        self.assertIn('[ "$pid" = "$self" ] && continue', text)
        self.assertNotIn("kill $old", text)
        self.assertIn('victims="$victims $pid"', text)
        self.assertIn('RESTART_BLOCKED_OLD_EXECUTOR_ALIVE', text)
        self.assertIn('kill -0 "$pid"', text)
        self.assertLess(
            text.index('RESTART_BLOCKED_OLD_EXECUTOR_ALIVE'),
            text.index('rm -rf /data/local/y700-agent/runtime/host-executor.lock'),
        )

    def test_start_uses_lock_owner_as_pid_authority(self) -> None:
        text = (ROOT / "scripts" / "start-host-executor.sh").read_text()
        self.assertIn('LOCK=/data/local/y700-agent/runtime/host-executor.lock', text)
        self.assertIn('cat "$LOCK/pid"', text)
        self.assertNotIn('echo $! > "$PIDFILE"', text)

    def test_health_reports_duplicate_executor_count(self) -> None:
        text = (ROOT / "scripts" / "health-check.sh").read_text()
        self.assertIn("count_host_executors", text)
        self.assertIn('android_bridge_instances', text)
        self.assertIn('[ "$bridge_instances" -ne 1 ]', text)


if __name__ == "__main__":
    unittest.main()
