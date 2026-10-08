import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def observation(checked=True):
    return {
        "package": "com.example",
        "display_width": 1904,
        "display_height": 3040,
        "elements": [
            {
                "node_id": "root",
                "parent_id": None,
                "resource_id": None,
                "class": "android.widget.FrameLayout",
                "package": "com.example",
                "clickable": False,
                "enabled": True,
                "selected": False,
                "checked": False,
                "bounds": [0, 0, 1904, 3040],
            },
            {
                "node_id": "switch",
                "parent_id": "root",
                "resource_id": "android:id/switch_widget",
                "class": "android.widget.Switch",
                "package": "com.example",
                "clickable": True,
                "enabled": True,
                "selected": False,
                "checked": checked,
                "bounds": [100, 200, 300, 320],
            },
        ],
    }


class Rev36CoreV2Tests(unittest.TestCase):
    def modules(self, root: Path):
        env = {
            "Y700_RUNTIME": str(root),
            "Y700_UI_STATE_DIR": str(root / "ui-state"),
        }
        with patch.dict(os.environ, env, clear=False):
            import automation.resource_arbiter as ra
            import automation.state_integrity as si
            import automation.ui_core_v2 as core
            ra = importlib.reload(ra)
            si = importlib.reload(si)
            core = importlib.reload(core)
        return ra, si, core

    def driver(self, observed, calls):
        def run(actions, label):
            calls.append([a["action"] for a in actions])
            if len(actions) == 2 and actions[0]["action"] == "health":
                current = observed.pop(0) if len(observed) > 1 else observed[0]
                return {
                    "status": "PASS",
                    "preflight": {"current_package": "com.example"},
                    "actions": [
                        {
                            "action_id": actions[0]["action_id"],
                            "action": "health",
                            "status": "PASS",
                            "data": {
                                "screen_on": True,
                                "keyguard_blocking": False,
                                "current_package": "com.example",
                            },
                        },
                        {
                            "action_id": actions[1]["action_id"],
                            "action": "observe",
                            "status": "PASS",
                            "data": current,
                        },
                    ],
                }
            action = actions[0]
            return {
                "status": "PASS",
                "preflight": {"current_package": "com.example"},
                "actions": [{
                    "action_id": action.get("action_id"),
                    "action": action["action"],
                    "status": "PASS",
                    "data": {
                        "ok": True,
                        "postcondition_passed": True,
                        "postcondition_kind": "DRIVER_DISPATCH_ACK",
                    },
                }],
            }
        return run

    def req(self, action, guard=None):
        value = {
            "protocol_version": 2,
            "job_id": "rev36-core-test",
            "session_id": "session-1",
            "actions": [action],
            "state_guard": {"mode": "AUTO", "max_age_ms": 30000},
        }
        if guard is not None:
            value["resource_guard"] = guard
        return value

    def run_core(self, core, req, driver, journal):
        return core.run(
            req,
            driver_run=driver,
            activity_read=lambda label: (
                "mResumedActivity: ActivityRecord{ x com.example/.MainActivity }"
            ),
            journal_append=journal.append,
            checkpoint_write=lambda index, safe: None,
            cancel_check=lambda: False,
            now_iso=lambda: "2026-10-07T00:00:00+00:00",
        )

    def test_a23_missing_resource_guard_blocks_before_attempt(self):
        with tempfile.TemporaryDirectory() as td:
            ra, si, core = self.modules(Path(td))
            calls = []
            journal = []
            req = self.req({
                "action_id": "home",
                "action": "pressHome",
                "side_effect": "REVERSIBLE_LOCAL",
            })
            result = self.run_core(
                core, req, self.driver([observation()], calls), journal
            )
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["action_attempts"], 0)
            self.assertEqual(result["error"]["code"], "RESOURCE_OWNERSHIP_REQUIRED")
            self.assertEqual(si.load_state()["revision"], 0)
            self.assertEqual(calls, [])
            self.assertFalse(any(x.get("phase") == "MUTATION_PREPARED" for x in journal))

    def test_a31_press_home_is_prepared_committed_and_increments_revision(self):
        with tempfile.TemporaryDirectory() as td:
            ra, si, core = self.modules(Path(td))
            calls = []
            journal = []
            snap = {
                "fingerprint_version": "semantic-v1",
                "scope": "FOREGROUND",
                "screen": {
                    "interactive": True,
                    "keyguard_locked": False,
                    "blocking_overlay_present": False,
                    "blocking_overlay_owner_package": None,
                    "blocking_overlay_class": None,
                },
                "foreground": {
                    "package": "com.example",
                    "activity": "com.example.MainActivity",
                },
            }
            old_proof = si.issue_token(
                snap,
                fingerprint_profile_id="semantic-v1.foreground-base.v1",
            )
            with ra.acquire_android_ui(
                owner_kind="LEGACY",
                owner_id="legacy:test",
                backend_type="test",
                backend_job_id="backend-1",
                request_sha256=ra.request_identity({"x": 1}),
            ) as guard:
                req = self.req({
                    "action_id": "home",
                    "action": "pressHome",
                    "side_effect": "REVERSIBLE_LOCAL",
                }, guard.as_dict())
                result = self.run_core(
                    core, req, self.driver([observation(), observation()], calls), journal
                )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(si.load_state()["revision"], 1)
            phases = [row.get("phase") for row in journal]
            self.assertLess(
                phases.index("MUTATION_PREPARED"),
                phases.index("MUTATION_COMMITTED"),
            )
            committed = next(x for x in journal if x.get("phase") == "MUTATION_COMMITTED")
            self.assertEqual(committed["revision_before"], 0)
            self.assertEqual(committed["revision_after"], 1)
            self.assertEqual(committed["postcondition"], "PASS")
            self.assertEqual(committed["postcondition_kind"], "DRIVER_DISPATCH_ACK")
            self.assertEqual(committed["fingerprint_version"], "semantic-v1")
            self.assertEqual(committed["resource_claim_id"], guard.claim_id)
            prepared = next(x for x in journal if x.get("phase") == "MUTATION_PREPARED")
            self.assertEqual(prepared["fingerprint_version"], "semantic-v1")
            self.assertEqual(prepared["resource_claim_id"], guard.claim_id)
            with self.assertRaisesRegex(si.StateIntegrityError, "STALE_STATE_REVISION"):
                si.assert_token(
                    old_proof,
                    snap,
                    expected_profile_id="semantic-v1.foreground-base.v1",
                )

    def test_driver_pass_without_postcondition_is_reconcile_and_revision_stays_old(self):
        with tempfile.TemporaryDirectory() as td:
            ra, si, core = self.modules(Path(td))
            calls = []
            journal = []

            def missing_postcondition(actions, label):
                if len(actions) == 2 and actions[0]["action"] == "health":
                    return self.driver([observation(), observation()], calls)(actions, label)
                action = actions[0]
                calls.append([action["action"]])
                return {
                    "status": "PASS",
                    "preflight": {"current_package": "com.example"},
                    "actions": [{
                        "action_id": action.get("action_id"),
                        "action": action["action"],
                        "status": "PASS",
                        "data": {"ok": True},
                    }],
                }

            with ra.acquire_android_ui(
                owner_kind="LEGACY",
                owner_id="legacy:test",
                backend_type="test",
                backend_job_id="backend-postcondition",
                request_sha256=ra.request_identity({"x": "post"}),
            ) as guard:
                req = self.req({
                    "action_id": "home",
                    "action": "pressHome",
                    "side_effect": "REVERSIBLE_LOCAL",
                }, guard.as_dict())
                result = self.run_core(core, req, missing_postcondition, journal)

            self.assertEqual(result["status"], "RECONCILE_REQUIRED")
            self.assertEqual(result["error"]["code"], "MUTATION_OUTCOME_UNKNOWN")
            self.assertEqual(si.load_state()["revision"], 0)
            self.assertTrue(any(x.get("phase") == "MUTATION_PREPARED" for x in journal))
            self.assertTrue(any(x.get("phase") == "MUTATION_AMBIGUOUS" for x in journal))
            self.assertFalse(any(x.get("phase") == "MUTATION_COMMITTED" for x in journal))

    def test_revision_is_durable_before_mutation_committed_append(self):
        with tempfile.TemporaryDirectory() as td:
            ra, si, core = self.modules(Path(td))
            calls = []
            journal = []
            revision_written = {"value": False}
            real_advance = core.state_integrity.advance_revision

            def tracked_advance():
                pair = real_advance()
                revision_written["value"] = True
                return pair

            def append_checked(row):
                if row.get("phase") == "MUTATION_COMMITTED":
                    self.assertTrue(revision_written["value"])
                    self.assertEqual(si.load_state()["revision"], 1)
                journal.append(row)

            with ra.acquire_android_ui(
                owner_kind="LEGACY",
                owner_id="legacy:test",
                backend_type="test",
                backend_job_id="backend-order",
                request_sha256=ra.request_identity({"x": "order"}),
            ) as guard:
                req = self.req({
                    "action_id": "home",
                    "action": "pressHome",
                    "side_effect": "REVERSIBLE_LOCAL",
                }, guard.as_dict())
                with patch.object(core.state_integrity, "advance_revision", tracked_advance):
                    result = core.run(
                        req,
                        driver_run=self.driver([observation(), observation()], calls),
                        activity_read=lambda label: (
                            "mResumedActivity: ActivityRecord{ x com.example/.MainActivity }"
                        ),
                        journal_append=append_checked,
                        checkpoint_write=lambda index, safe: None,
                        cancel_check=lambda: False,
                        now_iso=lambda: "2026-10-07T00:00:00+00:00",
                    )

            self.assertEqual(result["status"], "PASS")
            self.assertTrue(revision_written["value"])
            self.assertEqual(si.load_state()["revision"], 1)

    def test_manual_element_drift_blocks_before_dispatch(self):
        with tempfile.TemporaryDirectory() as td:
            ra, si, core = self.modules(Path(td))
            calls = []
            journal = []
            with ra.acquire_android_ui(
                owner_kind="LEGACY",
                owner_id="legacy:test",
                backend_type="test",
                backend_job_id="backend-2",
                request_sha256=ra.request_identity({"x": 2}),
            ) as guard:
                req = self.req({
                    "action_id": "toggle",
                    "action": "click",
                    "selector": {"resource_id": "android:id/switch_widget"},
                    "fingerprint_profile_id": "settings.switch.element-base.v1",
                    "side_effect": "REVERSIBLE_LOCAL",
                }, guard.as_dict())
                result = self.run_core(
                    core,
                    req,
                    self.driver([observation(True), observation(False)], calls),
                    journal,
                )
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["action_attempts"], 0)
            self.assertEqual(result["error"]["code"], "STALE_STATE_HASH")
            self.assertEqual(si.load_state()["revision"], 0)
            self.assertFalse(any(x.get("phase") == "MUTATION_PREPARED" for x in journal))
            self.assertEqual(calls, [["health", "observe"], ["health", "observe"]])


    def test_prepared_mutation_with_unknown_driver_liveness_retains_claim(self):
        from automation import ui_job
        base = {
            "status": "PASS",
            "actions": [{"action_id": "home", "status": "PASS"}],
        }
        result = ui_job.enforce_driver_session_liveness(
            base,
            mutation_prepared=True,
            session_terminal=False,
            job_id="job-1",
            session_id="session-1",
        )
        self.assertEqual(result["status"], "RECONCILE_REQUIRED")
        self.assertTrue(result["retain_resource_claim"])
        self.assertEqual(result["error"]["code"], "DRIVER_SESSION_LIVENESS_UNKNOWN")
        self.assertEqual(result["actions"], base["actions"])

    def test_terminal_driver_session_does_not_force_claim_retention(self):
        from automation import ui_job
        base = {"status": "PASS", "actions": []}
        result = ui_job.enforce_driver_session_liveness(
            base,
            mutation_prepared=True,
            session_terminal=True,
            job_id="job-1",
            session_id="session-1",
        )
        self.assertIs(result, base)
        self.assertNotIn("retain_resource_claim", result)


if __name__ == "__main__":
    unittest.main()
