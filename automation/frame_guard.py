"""Rev3.7 frame/locator freshness contract (no mutation dispatch).

Caller-supplied age limits never authorize a longer freshness window: the
expected_max_age_ms argument must come from the versioned route contract.
No screenshot pixel bytes enter semantic-v1 fingerprinting.
"""
from __future__ import annotations

from typing import Any, Mapping

SOURCES = frozenset({"SCREENSHOT", "STREAM", "CAPTURE_API"})


class FrameGuardError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
        self.failure_stage = (
            "TARGET_LOCALIZATION" if code == "LOCATOR_AMBIGUOUS"
            else "FRAME_ACQUISITION" if code == "FRAME_UNAVAILABLE"
            else "FRAME_FRESHNESS"
        )
        self.action_attempts = 0
        self.retry_class = "REOBSERVE_ONLY"


def _required(condition: bool, code: str = "FRAME_UNAVAILABLE") -> None:
    if not condition:
        raise FrameGuardError(code)


def validate_frame_guard(
    frame: Mapping[str, Any],
    locator: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    expected_max_age_ms: int,
    now_boottime_ms: int,
    expected_locator_contract_version: str,
) -> dict[str, Any]:
    """Fail closed until exact frame, device state, and locator binding match.

    `current` must be read at the action boundary from trusted device/runtime
    observation, not copied from the screenshot token.
    """
    _required(isinstance(frame, Mapping) and isinstance(locator, Mapping))
    _required(isinstance(current, Mapping))
    _required(type(expected_max_age_ms) is int and 0 < expected_max_age_ms <= 10000)
    _required(type(now_boottime_ms) is int and now_boottime_ms >= 0)
    _required(isinstance(expected_locator_contract_version, str) and bool(expected_locator_contract_version))
    _required(frame.get("frame_token_version") == 1)
    frame_id = frame.get("frame_id")
    _required(isinstance(frame_id, str) and frame_id.startswith("frame-") and len(frame_id) > 6)
    _required(frame.get("source") in SOURCES)
    _required(type(frame.get("max_age_ms")) is int and frame["max_age_ms"] == expected_max_age_ms)
    _required(isinstance(frame.get("observed_boot_id"), str) and bool(frame["observed_boot_id"]))
    _required(isinstance(frame.get("state_epoch"), str) and bool(frame["state_epoch"]))
    for name in ("revision", "display_id", "captured_boottime_ms"):
        _required(type(frame.get(name)) is int and frame[name] >= 0)
    _required(type(frame.get("rotation")) is int and 0 <= frame["rotation"] <= 3)
    for name in ("width", "height"):
        _required(type(frame.get(name)) is int and frame[name] > 0)
    foreground = frame.get("foreground")
    _required(isinstance(foreground, Mapping))
    for name in ("package", "activity"):
        _required(isinstance(foreground.get(name), str) and bool(foreground[name]))

    _required(locator.get("frame_id") == frame_id, "LOCATOR_FRAME_MISMATCH")
    _required(locator.get("locator_contract_version") == expected_locator_contract_version, "LOCATOR_FRAME_MISMATCH")
    _required(isinstance(locator.get("target_identity"), str) and bool(locator["target_identity"]), "LOCATOR_AMBIGUOUS")
    bounds = locator.get("bounds")
    target = locator.get("semantic_target")
    if bounds is not None:
        _required(
            isinstance(bounds, (list, tuple)) and len(bounds) == 4
            and all(type(v) is int for v in bounds),
            "LOCATOR_AMBIGUOUS",
        )
        x1, y1, x2, y2 = bounds
        _required(
            0 <= x1 < x2 <= frame["width"]
            and 0 <= y1 < y2 <= frame["height"],
            "LOCATOR_AMBIGUOUS",
        )
    else:
        _required(isinstance(target, str) and bool(target.strip()), "LOCATOR_AMBIGUOUS")
    _required(locator.get("ambiguous") is not True, "LOCATOR_AMBIGUOUS")

    _required(current.get("boot_id") == frame["observed_boot_id"], "FRAME_BOOT_MISMATCH")
    _required(current.get("state_epoch") == frame["state_epoch"], "FRAME_STALE")
    _required(type(current.get("revision")) is int and current["revision"] == frame["revision"], "FRAME_REVISION_STALE")
    _required(current.get("display_id") == frame["display_id"], "FRAME_DISPLAY_CHANGED")
    _required(current.get("rotation") == frame["rotation"], "FRAME_ROTATION_CHANGED")
    _required(current.get("width") == frame["width"] and current.get("height") == frame["height"], "FRAME_DISPLAY_CHANGED")
    active = current.get("foreground")
    _required(isinstance(active, Mapping) and active == foreground, "FRAME_FOREGROUND_DRIFT")
    _required(current.get("screen_interactive") is True and current.get("keyguard_locked") is False, "FRAME_STALE")
    _required(current.get("blocking_overlay_present") is False, "FRAME_STALE")

    captured = frame["captured_boottime_ms"]
    _required(now_boottime_ms >= captured, "FRAME_STALE")
    age_ms = now_boottime_ms - captured
    _required(age_ms <= expected_max_age_ms, "FRAME_STALE")
    return {
        "frame_id": frame_id,
        "frame_age_at_dispatch_ms": age_ms,
        "max_frame_age_ms": expected_max_age_ms,
        "locator_contract_version": expected_locator_contract_version,
    }
