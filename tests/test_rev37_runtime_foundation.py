"""Rev3.7 foundation tests; no production visual mutation is authorized."""
from __future__ import annotations

import copy
import unittest

from automation.frame_guard import FrameGuardError, validate_frame_guard
from automation.route_selection import RouteContractError, select_execution_route


FRAME = {
    "frame_token_version": 1,
    "frame_id": "frame-123",
    "source": "SCREENSHOT",
    "observed_boot_id": "boot-abc",
    "captured_boottime_ms": 1000,
    "state_epoch": "epoch-1",
    "revision": 42,
    "display_id": 0,
    "rotation": 1,
    "width": 1600,
    "height": 2560,
    "foreground": {"package": "com.example", "activity": "Main"},
    "max_age_ms": 1200,
}
LOCATOR = {
    "frame_id": "frame-123",
    "locator_contract_version": "visual-target.v1",
    "target_identity": "post_button",
    "bounds": [100, 100, 240, 240],
    "ambiguous": False,
}
CURRENT = {
    "boot_id": "boot-abc",
    "state_epoch": "epoch-1",
    "revision": 42,
    "display_id": 0,
    "rotation": 1,
    "width": 1600,
    "height": 2560,
    "foreground": {"package": "com.example", "activity": "Main"},
    "screen_interactive": True,
    "keyguard_locked": False,
    "blocking_overlay_present": False,
}
ROUTES = {
    "route_version": 1,
    "route_ids": {c: f"ui.{c.lower()}.v1" for c in (
        "VERIFIED_NOOP", "SEMANTIC_UI", "VISION_ASSISTED_UI",
        "HOST_PRIMITIVE", "BLOCKED",
    )},
    "host_primitive_allowed": True,
}
FACTS = {
    "target_state": "READY",
    "device_contract": "y700-android16-zui",
    "evidence_revision": 42,
    "target_proven": False,
    "semantic_resolved": False,
    "vision_guard_passed": False,
    "host_primitive_ready": False,
}


class FrameGuardTests(unittest.TestCase):
    def verify(self, frame=None, locator=None, current=None, now=1500, max_age=1200):
        return validate_frame_guard(
            copy.deepcopy(FRAME if frame is None else frame),
            copy.deepcopy(LOCATOR if locator is None else locator),
            copy.deepcopy(CURRENT if current is None else current),
            now_boottime_ms=now,
            expected_max_age_ms=max_age,
            expected_locator_contract_version="visual-target.v1",
        )

    def assert_blocked(self, code, **kwargs):
        with self.assertRaises(FrameGuardError) as caught:
            self.verify(**kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.action_attempts, 0)

    def test_same_frame_fresh(self):
        self.assertEqual(self.verify()["frame_age_at_dispatch_ms"], 500)

    def test_stale_age(self):
        self.assert_blocked("FRAME_STALE", now=2201)

    def test_future_capture_is_invalid(self):
        self.assert_blocked("FRAME_STALE", now=999)

    def test_locator_from_old_frame(self):
        locator = {**LOCATOR, "frame_id": "frame-other"}
        self.assert_blocked("LOCATOR_FRAME_MISMATCH", locator=locator)

    def test_revision_after_mutation_invalidates_frame(self):
        self.assert_blocked("FRAME_REVISION_STALE", current={**CURRENT, "revision": 43})

    def test_boot_changed(self):
        self.assert_blocked("FRAME_BOOT_MISMATCH", current={**CURRENT, "boot_id": "boot-rebooted"})

    def test_display_rotation_foreground_changed(self):
        self.assert_blocked("FRAME_ROTATION_CHANGED", current={**CURRENT, "rotation": 2})
        self.assert_blocked("FRAME_DISPLAY_CHANGED", current={**CURRENT, "width": 1000})
        self.assert_blocked("FRAME_FOREGROUND_DRIFT", current={
            **CURRENT, "foreground": {"package": "other", "activity": "Main"}
        })

    def test_overlay_or_keyguard_blocks(self):
        self.assert_blocked("FRAME_STALE", current={**CURRENT, "blocking_overlay_present": True})
        self.assert_blocked("FRAME_STALE", current={**CURRENT, "keyguard_locked": True})

    def test_ambiguous_locator_blocks(self):
        self.assert_blocked("LOCATOR_AMBIGUOUS", locator={**LOCATOR, "ambiguous": True})

    def test_stage_diagnostics_are_not_a_single_health_flag(self):
        with self.assertRaises(FrameGuardError) as bad_locator:
            self.verify(locator={**LOCATOR, "ambiguous": True})
        self.assertEqual(bad_locator.exception.failure_stage, "TARGET_LOCALIZATION")
        with self.assertRaises(FrameGuardError) as bad_frame:
            self.verify(frame={**FRAME, "max_age_ms": 0})
        self.assertEqual(bad_frame.exception.failure_stage, "FRAME_ACQUISITION")
        with self.assertRaises(FrameGuardError) as stale:
            self.verify(now=2201)
        self.assertEqual(stale.exception.failure_stage, "FRAME_FRESHNESS")

    def test_route_contract_cannot_be_relaxed(self):
        self.assert_blocked("FRAME_UNAVAILABLE", max_age=5000)
        self.assert_blocked("FRAME_UNAVAILABLE", frame={**FRAME, "max_age_ms": 99999})


class RouteSelectionTests(unittest.TestCase):
    def select(self, **kwargs):
        values = {**FACTS, **kwargs}
        return select_execution_route(contract=ROUTES, **values)

    def test_noop_first(self):
        self.assertEqual(self.select(target_proven=True, semantic_resolved=True)["route_class"], "VERIFIED_NOOP")

    def test_semantic_over_vision(self):
        self.assertEqual(self.select(semantic_resolved=True, vision_guard_passed=True, dg3_accepted=True)["route_class"], "SEMANTIC_UI")

    def test_no_gate_blocks_visual_route(self):
        self.assertEqual(self.select(vision_guard_passed=True)["route_class"], "BLOCKED")

    def test_dg3_allows_visual_route_only_for_local_mutations(self):
        self.assertEqual(self.select(vision_guard_passed=True, dg3_accepted=True)["route_class"], "VISION_ASSISTED_UI")
        self.assertEqual(self.select(vision_guard_passed=True, dg3_accepted=True,
                                     action_class="EXTERNAL_IRREVERSIBLE")["route_class"], "BLOCKED")

    def test_host_primitive_is_opt_in(self):
        self.assertEqual(self.select(host_primitive_ready=True)["route_class"], "HOST_PRIMITIVE")
        disabled = {**ROUTES, "host_primitive_allowed": False}
        self.assertEqual(select_execution_route(contract=disabled, **{**FACTS, "host_primitive_ready": True})["route_class"], "BLOCKED")

    def test_contract_schema_is_stable(self):
        got = self.select()
        self.assertEqual(set(got), {"route_version", "route_id", "route_class", "selected_for"})
        self.assertEqual(got["selected_for"]["evidence_revision"], 42)

    def test_invalid_static_table_fails_closed(self):
        with self.assertRaises(RouteContractError):
            select_execution_route(contract={"route_version": 1}, **FACTS)


if __name__ == "__main__":
    unittest.main()
