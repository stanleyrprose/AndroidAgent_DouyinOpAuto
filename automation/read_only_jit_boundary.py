"""Rev3.7 host-only read-only JIT evidence composer.

Connects authoritative Debian state, an *independently observed* Android
hardware/window adapter, and frame_guard without issuing UI mutations.
It intentionally does not install a callback into the production Driver:
an untrusted callback cannot make visual dispatch safe or bypass D-G3.

Windows from UiAutomation were unavailable on the real Y700 as of the freeze;
a focused WindowManager line is not a complete classified window inventory.
Hence no current route can claim an authoritative 'overlay_clear' fact.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping
import time

from automation import frame_guard, visual_route_gate
from automation.authoritative_state_reader import (
    AuthorityUnavailable,
    observe_authoritative_state,
    validate_against_authority,
)
from automation.overlay_window_policy import (
    OverlayStatus, classify_window_facts_readonly,
)


@dataclass(frozen=True)
class InternalRoute:
    route_id: str
    overlay_contract_id: str
    foreground_package: str
    locator_contract_version: str
    max_frame_age_ms: int | None
    empirical_calibration_accepted: bool


# Not populated from workflow JSON / model suggestions / runtime config.
# No empirical route-age calibration was accepted for D-G3.
_ROUTING: dict[str, InternalRoute] = {
    "tiktok.create.readonly.v1": InternalRoute(
        "tiktok.create.readonly.v1",
        "tiktok.create.observe.v1",
        "com.zhiliaoapp.musically",
        "tiktok-create-target.v1",
        None,
        False,
    ),
    "android.settings.readonly.v1": InternalRoute(
        "android.settings.readonly.v1",
        "android.settings.observe.v1",
        "com.android.settings",
        "android-settings-target.v1",
        None,
        False,
    ),
}


AndroidObserve = Callable[[], Mapping[str, Any]]


def _receipt(reason: str, *, stage: str,
             observations: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "BLOCKED",
        "error_code": reason,
        "failure_stage": stage,
        "dg3_status": "OPEN",
        "production_dispatch_authorized": False,
        "visual_dispatch_allowed": False,
        "action_attempts": 0,
        "mutating_driver_invoked": False,
    }
    if observations:
        # Only reduced metrics, no sensitive OS/window inventory or raw epochs.
        for key in ("frame_age_ms", "state_observation_age_ms",
                    "blocking_window_seen", "locator_contract_version"):
            if key in observations:
                result[key] = observations[key]
    return result


def _needed(condition: bool, code: str, stage: str) -> None:
    if not condition:
        raise _JitUnavailable(code, stage)


class _JitUnavailable(Exception):
    def __init__(self, code: str, stage: str):
        super().__init__(code)
        self.code = code
        self.stage = stage


def _boot_clock_ms() -> int:
    try:
        return time.clock_gettime_ns(time.CLOCK_BOOTTIME) // 1_000_000
    except (OSError, AttributeError) as exc:
        raise _JitUnavailable("BOOTTIME_UNAVAILABLE", "FRAME_FRESHNESS") from exc


def compose_readonly_jit(
    *,
    route_id: str,
    frame: Mapping[str, Any],
    locator: Mapping[str, Any],
    observe_android: AndroidObserve,
) -> dict[str, Any]:
    """Collect independent host and Android observations without an action.

    observe_android must be bound by the trusted host adapter, never supplied
    by workflow JSON. This read-only composer cannot mint a signed FrameToken
    or a production permission. The actual Driver will independently reject
    visual mutation until its native on-dispatch SOT/overlay/JIT gates exist.
    """
    if visual_route_gate.is_visual_mutation_accepted():
        return _receipt("READ_ONLY_DIAGNOSTIC_UNAVAILABLE_ON_ACTIVE_RELEASE",
                        stage="DRIVER_DISPATCH")
    route = _ROUTING.get(route_id)
    if route is None:
        return _receipt("RUNTIME_CONTRACT_MISMATCH", stage="FRAME_ACQUISITION")
    try:
        _needed(isinstance(frame, Mapping) and isinstance(locator, Mapping),
                "FRAME_UNAVAILABLE", "FRAME_ACQUISITION")
        _needed(callable(observe_android), "ANDROID_OBSERVER_UNAVAILABLE",
                "UI_OBSERVATION")
        state_before = observe_authoritative_state()
        validate_against_authority(frame, state_before)

        # Android facts are reobserved AFTER initial state read, never copied
        # from the frame or locator request.
        physical = observe_android()
        _needed(isinstance(physical, Mapping), "ANDROID_OBSERVER_UNAVAILABLE",
                "UI_OBSERVATION")
        state_after = observe_authoritative_state()
        _needed(
            (state_before.boot_id, state_before.state_epoch, state_before.revision)
            == (state_after.boot_id, state_after.state_epoch, state_after.revision),
            "FRAME_REVISION_STALE", "FRAME_FRESHNESS",
        )
        validate_against_authority(frame, state_after)

        fg = physical.get("foreground")
        _needed(isinstance(fg, Mapping)
                and fg.get("package") == route.foreground_package
                and isinstance(fg.get("activity"), str) and bool(fg.get("activity")),
                "FRAME_FOREGROUND_DRIFT", "UI_OBSERVATION")
        _needed(physical.get("boot_id") == state_after.boot_id,
                "FRAME_BOOT_MISMATCH", "FRAME_FRESHNESS")
        _needed(type(physical.get("observed_boottime_ms")) is int
                and state_before.observed_boottime_ms
                <= physical["observed_boottime_ms"]
                <= state_after.observed_boottime_ms,
                "ANDROID_OBSERVATION_CLOCK_UNTRUSTED", "UI_OBSERVATION")
        _needed(physical.get("screen_interactive") is True
                and physical.get("keyguard_locked") is False,
                "FRAME_STALE", "UI_OBSERVATION")

        # Overlay classifier is action-specific, incomplete inventory ->
        # UNAVAILABLE. The caller cannot force false/clear.
        overlay = classify_window_facts_readonly(
            contract_id=route.overlay_contract_id,
            foreground_package=route.foreground_package,
            inventory=physical.get("windows"),
            target_bounds=locator.get("bounds"),
            semantic_modal_guard_clear=physical.get("semantic_modal_guard_clear"),
        )
        if overlay.status == OverlayStatus.UNAVAILABLE:
            raise _JitUnavailable(
                "OVERLAY_CLASSIFICATION_UNAVAILABLE", "UI_OBSERVATION"
            )
        if overlay.status == OverlayStatus.BLOCKED:
            raise _JitUnavailable(
                "UNEXPECTED_BLOCKING_OVERLAY", "UI_OBSERVATION"
            )

        # Route age is a static policy input. There is deliberately no
        # permissive fallback in the absence of accepted real measurements.
        _needed(route.empirical_calibration_accepted
                and type(route.max_frame_age_ms) is int,
                "FRAME_AGE_UNCALIBRATED", "FRAME_FRESHNESS")

        current = {
            "boot_id": state_after.boot_id,
            "state_epoch": state_after.state_epoch,
            "revision": state_after.revision,
            "display_id": physical.get("display_id"),
            "rotation": physical.get("rotation"),
            "width": physical.get("width"),
            "height": physical.get("height"),
            "foreground": dict(fg),
            "screen_interactive": physical.get("screen_interactive"),
            "keyguard_locked": physical.get("keyguard_locked"),
            # This comes only from strict classified complete window facts,
            # never from caller-supplied false or an empty UiAutomation list.
            "blocking_overlay_present": False,
        }
        metrics = frame_guard.validate_frame_guard(
            frame, locator, current,
            expected_max_age_ms=route.max_frame_age_ms,
            now_boottime_ms=_boot_clock_ms(),
            expected_locator_contract_version=route.locator_contract_version,
        )
        return {
            **_receipt("PRODUCTION_DISPATCH_NOT_AUTHORIZED",
                       stage="DRIVER_DISPATCH"),
            "status": "MATCHED_READ_ONLY",
            "frame_age_ms": metrics["frame_age_at_dispatch_ms"],
            "locator_contract_version": metrics["locator_contract_version"],
        }
    except AuthorityUnavailable as exc:
        return _receipt(exc.code, stage="STATE_INTEGRITY")
    except _JitUnavailable as exc:
        return _receipt(exc.code, stage=exc.stage)
    except frame_guard.FrameGuardError as exc:
        return _receipt(exc.code, stage=exc.failure_stage)
    except (TypeError, ValueError, AttributeError, KeyError):
        return _receipt("JIT_EVIDENCE_MALFORMED", stage="FRAME_FRESHNESS")
    except Exception:
        # Any Android observer failure remains zero-attempt and does not
        # silently fall back to a different dispatch primitive.
        return _receipt("JIT_OBSERVATION_UNAVAILABLE", stage="UI_OBSERVATION")
