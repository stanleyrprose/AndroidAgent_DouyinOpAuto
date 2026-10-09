"""Rev3.7 Sprint 1A in-memory read-only frame/locator/JIT receipt harness.

This module NEVER emits UI actions or authorizes production visual mutations.
It models capture -> candidate frame token -> exact locator binding ->
independent current-device JIT snapshot and CLOCK_BOOTTIME. No caller may
stretch the frozen route age limit. Production D-G3 remains CLOSED.
"""
from __future__ import annotations

import secrets
from typing import Any, Callable, Mapping

from automation import frame_guard, visual_route_gate

Capture = Callable[[], Mapping[str, Any]]
Locate = Callable[[Mapping[str, Any]], Mapping[str, Any]]
ObserveCurrent = Callable[[], Mapping[str, Any]]
Clock = Callable[[], int]

_REQUIRED_CAPTURE = {
    "source", "observed_boot_id", "capture_start_boottime_ms",
    "capture_end_boottime_ms", "display_id", "rotation", "width",
    "height", "foreground",
}


def _need(value: bool, code: str = "FRAME_UNAVAILABLE") -> None:
    if not value:
        raise frame_guard.FrameGuardError(code)


def _route_settings(contract: Mapping[str, Any]) -> tuple[int, str, str]:
    """Static adapter contract only; fixture calibration does not approve D-G3."""
    _need(isinstance(contract, Mapping), "RUNTIME_CONTRACT_MISMATCH")
    _need(contract.get("route_version") == 1, "RUNTIME_CONTRACT_MISMATCH")
    _need(contract.get("calibration_evidence_accepted") is True, "FRAME_AGE_UNCALIBRATED")
    limit = contract.get("max_frame_age_ms")
    _need(type(limit) is int and 0 < limit <= 10000, "RUNTIME_CONTRACT_MISMATCH")
    route_id = contract.get("route_id")
    locator_version = contract.get("locator_contract_version")
    _need(isinstance(route_id, str) and bool(route_id), "RUNTIME_CONTRACT_MISMATCH")
    _need(isinstance(locator_version, str) and bool(locator_version), "RUNTIME_CONTRACT_MISMATCH")
    return limit, route_id, locator_version


def candidate_frame_token(
    captured: Mapping[str, Any],
    proof: Mapping[str, Any],
    contract: Mapping[str, Any],
    *,
    frame_id: str | None = None,
) -> dict[str, Any]:
    """Issue an *offline candidate* only; not a production mutation authority.

    Capture time is anchored to START, never END, to avoid underestimating age.
    Epoch/revision come from the existing trusted semantic proof, not caller
    supplied capture metadata. Boot identity must match that proof.
    """
    max_age, _, _ = _route_settings(contract)
    _need(isinstance(captured, Mapping) and set(captured) == _REQUIRED_CAPTURE)
    _need(isinstance(proof, Mapping))
    _need(isinstance(proof.get("state_epoch"), str) and bool(proof["state_epoch"]))
    _need(type(proof.get("revision")) is int and proof["revision"] >= 0)
    _need(isinstance(proof.get("observed_boot_id"), str) and bool(proof["observed_boot_id"]))
    _need(captured.get("observed_boot_id") == proof["observed_boot_id"], "FRAME_BOOT_MISMATCH")
    start, end = captured.get("capture_start_boottime_ms"), captured.get("capture_end_boottime_ms")
    _need(type(start) is int and type(end) is int and 0 <= start < end)
    for name in ("display_id", "rotation", "width", "height"):
        _need(type(captured.get(name)) is int)
    _need(captured["display_id"] >= 0)
    _need(0 <= captured["rotation"] <= 3)
    _need(captured["width"] > 0 and captured["height"] > 0)
    fg = captured.get("foreground")
    _need(isinstance(fg, Mapping) and set(fg) == {"package", "activity"})
    _need(all(isinstance(fg[k], str) and bool(fg[k]) for k in ("package", "activity")))
    _need(captured.get("source") in frame_guard.SOURCES)
    if frame_id is None:
        frame_id = "frame-" + secrets.token_hex(16)
    _need(isinstance(frame_id, str) and frame_id.startswith("frame-") and len(frame_id) > 6)
    return {
        "frame_token_version": 1,
        "frame_id": frame_id,
        "source": captured["source"],
        "observed_boot_id": proof["observed_boot_id"],
        "captured_boottime_ms": start,
        "state_epoch": proof["state_epoch"],
        "revision": proof["revision"],
        "display_id": captured["display_id"],
        "rotation": captured["rotation"],
        "width": captured["width"],
        "height": captured["height"],
        "foreground": dict(fg),
        "max_age_ms": max_age,
    }


def read_only_frame_locator_receipt(
    *,
    contract: Mapping[str, Any],
    semantic_proof: Mapping[str, Any],
    capture: Capture,
    locate: Locate,
    observe_current: ObserveCurrent,
    clock_boottime_ms: Clock,
) -> dict[str, Any]:
    """Exercise exact capture/locator/live-state ordering without any action.

    The locator must return an explicit frame_id exact match; it is never
    automatically rebound by this module. Unexpected adapter exceptions fail
    closed with NO action, not fake success. Caller output excludes pixels.
    """
    base = {
        "status": "BLOCKED",
        "scope": "READ_ONLY_FRAME_LOCATOR_RECEIPT",
        "dg3_status": "OPEN",
        "production_gate_passed": False,
        "visual_dispatch_allowed": False,
        "ui_mutation_attempts": 0,
        "pixel_retention": "NOT_PERFORMED_BY_HARNESS",
    }
    try:
        _need(visual_route_gate.is_visual_mutation_accepted() is False,
              "READ_ONLY_PROBE_NOT_ALLOWED_ON_ACTIVE_RELEASE")
        max_age, route_id, locator_version = _route_settings(contract)
        captured = capture()
        frame = candidate_frame_token(captured, semantic_proof, contract)
        locator = locate(dict(frame))
        _need(isinstance(locator, Mapping), "LOCATOR_AMBIGUOUS")
        _need(locator.get("frame_id") == frame["frame_id"], "LOCATOR_FRAME_MISMATCH")
        locator_time = clock_boottime_ms()
        _need(type(locator_time) is int, "FRAME_UNAVAILABLE")
        # Capture is signed in trusted Android code in a future integration;
        # the following validates consistency of adapter-provided metadata.
        _need(locator_time >= frame["captured_boottime_ms"], "FRAME_STALE")
        current = observe_current()
        now = clock_boottime_ms()  # JIT, after independent live read
        metrics = frame_guard.validate_frame_guard(
            frame, locator, current,
            expected_max_age_ms=max_age,
            now_boottime_ms=now,
            expected_locator_contract_version=locator_version,
        )
        _need(frame["revision"] == semantic_proof.get("revision"), "FRAME_REVISION_STALE")
        _need(frame["state_epoch"] == semantic_proof.get("state_epoch"), "FRAME_STALE")
        _need(frame["observed_boot_id"] == semantic_proof.get("observed_boot_id"),
              "FRAME_BOOT_MISMATCH")
        return {
            **base,
            "status": "VERIFIED_READ_ONLY",
            "route_id": route_id,
            "frame_id": frame["frame_id"],
            "frame_token_version": 1,
            "locator_contract_version": locator_version,
            "frame_age_at_locator_ms": locator_time - frame["captured_boottime_ms"],
            "frame_age_at_hypothetical_dispatch_ms": metrics["frame_age_at_dispatch_ms"],
            "max_frame_age_ms": max_age,
            "capture_latency_ms": captured["capture_end_boottime_ms"] -
                                  captured["capture_start_boottime_ms"],
            "locator_bound": True,
            "current_state_matched": True,
            "note": "Synthetic/adapter receipt; never a production D-G3 acceptance",
        }
    except frame_guard.FrameGuardError as exc:
        return {**base, "error_code": exc.code, "failure_stage": exc.failure_stage}
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return {**base, "error_code": "FRAME_UNAVAILABLE", "failure_stage": "FRAME_ACQUISITION"}
    except Exception:
        # Failing adapter/clock/location callbacks must not be mistaken for
        # evidence acceptance or trigger a different execution route.
        return {**base, "error_code": "FRAME_ADAPTER_FAILED", "failure_stage": "FRAME_ACQUISITION"}
