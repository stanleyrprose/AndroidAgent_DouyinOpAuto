from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from apps.tiktok import controller


class _Guard:
    def __init__(self, claim_id="ui-claim-test", owner_id="legacy:tiktok:test"):
        self.claim_id = claim_id
        self.owner_id = owner_id
        self.retained = False
        self.retain_reason = None
        self.bound = None
        self.cleared = []

    def bind_active_execution(self, *, ui_job_id, session_id):
        self.bound = (ui_job_id, session_id)

    def clear_active_execution(self, *, ui_job_id):
        self.cleared.append(ui_job_id)
        if self.bound and self.bound[0] == ui_job_id:
            self.bound = None

    def retain_for_reconcile(self, reason="LIVENESS_UNKNOWN"):
        self.retained = True
        self.retain_reason = reason

    def as_dict(self):
        return {
            "resource": "android_ui",
            "claim_id": self.claim_id,
            "owner_id": self.owner_id,
        }


class Rev36TikTokOwnershipTests(unittest.TestCase):
    def tearDown(self):
        controller._CURRENT_UI_GUARD.set(None)

    def test_nested_ui_lease_reuses_exact_claim_without_reacquire(self):
        calls = []
        guard = _Guard()

        @contextmanager
        def fake_acquire(**kwargs):
            calls.append(kwargs)
            yield guard

        with patch.object(controller.resource_arbiter, "acquire_android_ui", fake_acquire):
            with controller.ui_lease() as outer:
                with controller.ui_lease() as inner:
                    self.assertIs(outer, guard)
                    self.assertIs(inner, guard)
                    self.assertEqual(outer.as_dict(), inner.as_dict())

        self.assertEqual(len(calls), 1)

    def test_mutation_request_uses_protocol_v2_exact_guard_and_auto_state_guard(self):
        captured = {}
        guard = _Guard("ui-claim-exact", "legacy:tiktok:exact")

        def fake_run(path: Path):
            req = json.loads(path.read_text(encoding="utf-8"))
            captured.update(req)
            return {
                "status": "PASS",
                "job_id": req["job_id"],
                "session_id": req["session_id"],
                "protocol_version": 2,
                "actions": [{
                    "action_id": "home",
                    "action": "pressHome",
                    "status": "PASS",
                    "data": {"pressed": "HOME"},
                }],
            }

        with tempfile.TemporaryDirectory() as td:
            with patch.object(controller, "REQUEST_RUNTIME", Path(td)),                  patch.object(controller.ui_job, "run_workflow", fake_run):
                ctx_marker = controller._CURRENT_UI_GUARD.set(guard)
                try:
                    result = controller._run(
                        "ownership-test",
                        [{
                            "action_id": "home",
                            "action": "pressHome",
                            "side_effect": "REVERSIBLE_LOCAL",
                        }],
                    )
                finally:
                    controller._CURRENT_UI_GUARD.reset(ctx_marker)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(captured["protocol_version"], 2)
        self.assertEqual(captured["resource_guard"], guard.as_dict())
        self.assertEqual(captured["state_guard"]["mode"], "AUTO")
        self.assertEqual(captured["state_guard"]["max_age_ms"], 30000)
        self.assertEqual(guard.cleared, [captured["job_id"]])
        self.assertIsNone(guard.bound)
        self.assertEqual(captured["session_id"], result["session_id"])

    def test_observation_request_stays_v1_without_ownership_guard(self):
        captured = {}

        def fake_run(path: Path):
            req = json.loads(path.read_text(encoding="utf-8"))
            captured.update(req)
            return {
                "status": "PASS",
                "job_id": req["job_id"],
                "session_id": "session",
                "protocol_version": 1,
                "actions": [{
                    "action_id": "observe",
                    "action": "observe",
                    "status": "PASS",
                    "data": {"elements": []},
                }],
            }

        with tempfile.TemporaryDirectory() as td:
            with patch.object(controller, "REQUEST_RUNTIME", Path(td)),                  patch.object(controller.ui_job, "run_workflow", fake_run):
                controller._run(
                    "observe-test",
                    [{"action_id": "observe", "action": "observe"}],
                )

        self.assertEqual(captured["protocol_version"], 1)
        self.assertNotIn("resource_guard", captured)
        self.assertNotIn("state_guard", captured)

    def test_reconcile_required_releases_claim_after_synchronous_backend_returns(self):
        entered = []
        exited = []
        guard = _Guard()

        @contextmanager
        def fake_acquire(**kwargs):
            entered.append(kwargs)
            try:
                yield guard
            finally:
                exited.append(True)

        def fake_run(path: Path):
            req = json.loads(path.read_text(encoding="utf-8"))
            return {
                "status": "RECONCILE_REQUIRED",
                "job_id": req["job_id"],
                "session_id": "session",
                "protocol_version": 2,
                "actions": [],
                "error": {"code": "MUTATION_RESULT_AMBIGUOUS", "retryable": False},
            }

        with tempfile.TemporaryDirectory() as td:
            with patch.object(controller, "REQUEST_RUNTIME", Path(td)),                  patch.object(controller.resource_arbiter, "acquire_android_ui", fake_acquire),                  patch.object(controller.ui_job, "run_workflow", fake_run):
                with self.assertRaises(controller.TikTokCoreError):
                    controller._run(
                        "ambiguous",
                        [{
                            "action_id": "back",
                            "action": "pressBack",
                            "side_effect": "REVERSIBLE_LOCAL",
                        }],
                    )

        self.assertEqual(len(entered), 1)
        self.assertEqual(exited, [True])
        self.assertEqual(len(guard.cleared), 1)
        self.assertIsNone(guard.bound)
        self.assertFalse(guard.retained)


    def test_unknown_driver_liveness_retains_exact_claim(self):
        guard = _Guard()
        captured = []

        @contextmanager
        def fake_acquire(**kwargs):
            captured.append(kwargs)
            yield guard

        def fake_run(path: Path):
            req = json.loads(path.read_text(encoding="utf-8"))
            return {
                "status": "RECONCILE_REQUIRED",
                "job_id": req["job_id"],
                "session_id": "session",
                "protocol_version": 2,
                "retain_resource_claim": True,
                "actions": [],
                "error": {
                    "code": "DRIVER_SESSION_LIVENESS_UNKNOWN",
                    "retryable": False,
                },
            }

        with tempfile.TemporaryDirectory() as td:
            with patch.object(controller, "REQUEST_RUNTIME", Path(td)), \
                 patch.object(controller.resource_arbiter, "acquire_android_ui", fake_acquire), \
                 patch.object(controller.ui_job, "run_workflow", fake_run):
                with self.assertRaises(controller.TikTokCoreError):
                    controller._run(
                        "unknown-liveness",
                        [{
                            "action_id": "back",
                            "action": "pressBack",
                            "side_effect": "REVERSIBLE_LOCAL",
                        }],
                    )

        self.assertEqual(len(captured), 1)
        self.assertTrue(guard.retained)
        self.assertEqual(guard.retain_reason, "DRIVER_SESSION_LIVENESS_UNKNOWN")
        self.assertIsNotNone(guard.bound)
        self.assertEqual(guard.cleared, [])


if __name__ == "__main__":
    unittest.main()
