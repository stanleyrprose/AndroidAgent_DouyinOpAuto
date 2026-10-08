#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

from automation import frame_guard, resource_arbiter, state_integrity


class CoreV2Error(RuntimeError):
    pass


DriverRun = Callable[[list[dict[str, Any]], str], dict[str, Any]]
ActivityRead = Callable[[str], str]
JournalAppend = Callable[[dict[str, Any]], None]
CheckpointWrite = Callable[[int, bool], None]
CancelCheck = Callable[[], bool]
NowIso = Callable[[], str]

_MUTATING = {
    "click", "longClick", "inputText", "clearText", "swipe", "scroll",
    "pressBack", "pressHome", "tapObserved", "appForceStop", "appLaunch",
}


_VISION_LOCATOR_TYPES = {"vision_template", "vision_text"}

# Trusted only when provided by the host's own capture/locator pipeline. The
# workflow JSON must never supply a callback or claim its own D-G3 acceptance.
VisualEvidenceProvider = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def action_may_use_visual_locator(action: dict[str, Any]) -> bool:
    """Detect vision fallbacks that the driver could execute implicitly."""
    if action.get("route_class") == "VISION_ASSISTED_UI":
        return True
    # Popup recovery can itself resolve a visual candidate even when the
    # primary selector is semantic; gate the entire mutating action.
    if "vision_recovery" in action:
        return True
    selector = action.get("selector")
    if not isinstance(selector, dict):
        return False
    if selector.get("type") in _VISION_LOCATOR_TYPES:
        return True
    fallback = selector.get("fallback")
    return isinstance(fallback, list) and any(
        isinstance(item, dict) and item.get("type") in _VISION_LOCATOR_TYPES
        for item in fallback
    )


def _jit_visual_guard(
    action: dict[str, Any],
    proof: dict[str, Any],
    provider: VisualEvidenceProvider | None,
) -> dict[str, Any]:
    """Fail closed before PREPARED; never trust evidence from workflow JSON.

    Provider must read independent live device state at the action boundary.
    Deliberately no provider is registered in ui_job production until D-G3.
    """
    if action.get("side_effect") == "EXTERNAL_IRREVERSIBLE":
        raise frame_guard.FrameGuardError("VISION_IRREVERSIBLE_DENIED")
    if provider is None:
        raise frame_guard.FrameGuardError("VISION_ROUTE_GATE_CLOSED")
    evidence = provider(action, proof)
    if not isinstance(evidence, dict):
        raise frame_guard.FrameGuardError("FRAME_UNAVAILABLE")
    if evidence.get("dg3_accepted") is not True:
        raise frame_guard.FrameGuardError("VISION_ROUTE_GATE_CLOSED")
    if evidence.get("state_token_revision") != proof.get("revision"):
        raise frame_guard.FrameGuardError("FRAME_REVISION_STALE")
    expected_age = evidence.get("route_max_frame_age_ms")
    # The provider's age calibration must come from a frozen route/action
    # contract, not from action, selector, request, frame, or locator.
    if not isinstance(evidence.get("route_id"), str) or not evidence["route_id"]:
        raise frame_guard.FrameGuardError("FRAME_UNAVAILABLE")
    metrics = frame_guard.validate_frame_guard(
        evidence.get("frame"),
        evidence.get("locator"),
        evidence.get("current"),
        expected_max_age_ms=expected_age,
        now_boottime_ms=evidence.get("now_boottime_ms"),
        expected_locator_contract_version=evidence.get("locator_contract_version"),
    )
    if evidence["frame"].get("revision") != proof["revision"]:
        raise frame_guard.FrameGuardError("FRAME_REVISION_STALE")
    if evidence["frame"].get("state_epoch") != proof.get("state_epoch"):
        raise frame_guard.FrameGuardError("FRAME_STALE")
    if evidence["frame"].get("observed_boot_id") != proof.get("observed_boot_id"):
        raise frame_guard.FrameGuardError("FRAME_BOOT_MISMATCH")
    result = {"route_id": evidence["route_id"], **metrics}
    for name in (
        "capture_latency_ms", "locator_latency_ms",
        "frame_age_at_locator_ms", "recapture_count",
    ):
        value = evidence.get(name)
        if type(value) is not int or value < 0:
            raise frame_guard.FrameGuardError("FRAME_UNAVAILABLE")
        result[name] = value
    return result


def classify_blocking_overlay(
    observation: dict[str, Any],
) -> tuple[bool, str | None, str | None]:
    foreground = observation.get("package")
    height = int(observation.get("display_height") or 0)
    roots = [
        row for row in (observation.get("elements") or [])
        if isinstance(row, dict) and row.get("parent_id") is None
    ]
    for row in roots:
        package = row.get("package")
        if not package or package == foreground:
            continue
        bounds = row.get("bounds")
        if not (
            isinstance(bounds, list) and len(bounds) == 4
            and all(isinstance(v, int) for v in bounds) and height > 0
        ):
            return True, str(package), str(row.get("class") or "unknown")
        _, top, _, bottom = bounds
        root_h = max(0, bottom - top)
        if package == "com.android.systemui" and (
            root_h <= int(height * 0.12) or top >= int(height * 0.88)
        ):
            continue
        if package == "com.zui.launcher" and top >= int(height * 0.85):
            continue
        if package == "com.google.android.inputmethod.latin" and top >= int(height * 0.35):
            continue
        return True, str(package), str(row.get("class") or "unknown")
    return False, None, None


def activity_component(text: str) -> str:
    match = re.search(r"([A-Za-z0-9_.]+)/(\.?[A-Za-z0-9_.$]+)", text)
    if not match:
        raise CoreV2Error("STATE_FINGERPRINT_UNAVAILABLE")
    package, activity = match.group(1), match.group(2)
    return package + activity if activity.startswith(".") else activity


def observe_state(
    *,
    action: dict[str, Any],
    label: str,
    driver_run: DriverRun,
    activity_read: ActivityRead,
) -> tuple[dict[str, Any], str]:
    driver = driver_run(
        [
            {"action_id": f"{label}-health", "action": "health"},
            {"action_id": f"{label}-observe", "action": "observe"},
        ],
        label,
    )
    actions = driver.get("actions") or []
    if driver.get("status") != "PASS" or len(actions) < 2:
        raise CoreV2Error("STATE_FINGERPRINT_UNAVAILABLE")
    health = actions[0].get("data") or {}
    observation = actions[1].get("data") or {}
    overlay, overlay_pkg, overlay_class = classify_blocking_overlay(observation)
    try:
        snapshot, profile_id = state_integrity.project_snapshot(
            observation,
            interactive=bool(health.get("screen_on")),
            keyguard_locked=bool(health.get("keyguard_blocking")),
            activity=activity_component(activity_read(label)),
            blocking_overlay_present=overlay,
            blocking_overlay_owner_package=overlay_pkg,
            blocking_overlay_class=overlay_class,
            action=action,
        )
    except state_integrity.StateIntegrityError as exc:
        raise CoreV2Error(str(exc)) from exc
    return snapshot, profile_id


def validate_state_guard(
    req: dict[str, Any],
    action: dict[str, Any],
    index: int,
    *,
    driver_run: DriverRun,
    activity_read: ActivityRead,
) -> dict[str, Any]:
    guard = req["state_guard"]
    if guard["mode"] == "AUTO":
        first, profile_id = observe_state(
            action=action,
            label=f"a{index:02d}-auto",
            driver_run=driver_run,
            activity_read=activity_read,
        )
        try:
            proof = state_integrity.issue_token(
                first,
                fingerprint_profile_id=profile_id,
                max_age_ms=int(guard.get("max_age_ms", 30000)),
            )
        except state_integrity.StateIntegrityError as exc:
            raise CoreV2Error(str(exc)) from exc
        current, current_profile = observe_state(
            action=action,
            label=f"a{index:02d}-jit",
            driver_run=driver_run,
            activity_read=activity_read,
        )
        if current_profile != profile_id:
            raise CoreV2Error("STATE_TOKEN_PROFILE_MISMATCH")
        try:
            state_integrity.assert_token(
                proof, current, expected_profile_id=profile_id
            )
        except state_integrity.StateIntegrityError as exc:
            raise CoreV2Error(str(exc)) from exc
        return proof

    proof = guard.get("token")
    current, profile_id = observe_state(
        action=action,
        label=f"a{index:02d}-token",
        driver_run=driver_run,
        activity_read=activity_read,
    )
    try:
        state_integrity.assert_token(
            proof, current, expected_profile_id=profile_id
        )
    except state_integrity.StateIntegrityError as exc:
        raise CoreV2Error(str(exc)) from exc
    return proof


def _blocked(
    req: dict[str, Any],
    results: list[dict[str, Any]],
    code: str,
    started: float,
) -> dict[str, Any]:
    return {
        "status": "BLOCKED",
        "job_id": req["job_id"],
        "session_id": req["session_id"],
        "protocol_version": 2,
        "actions": results,
        "action_attempts": 0,
        "error": {"code": code, "retryable": False},
        "host_duration_ms": round((time.monotonic() - started) * 1000, 1),
    }


def _driver_action_result(
    driver: dict[str, Any],
    action: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    rows = driver.get("actions") or []
    if rows:
        return rows[0]
    return {
        "action_id": action.get("action_id", f"action-{index}"),
        "action": action.get("action"),
        "status": "FAILED",
        "error": driver.get("error") or {
            "code": "DRIVER_CRASHED",
            "retryable": False,
        },
    }


def _prepared_row(
    req: dict[str, Any],
    action: dict[str, Any],
    index: int,
    claim: dict[str, Any],
    proof: dict[str, Any],
    request_sha: str,
    now_iso: NowIso,
) -> dict[str, Any]:
    return {
        "timestamp": now_iso(),
        "phase": "MUTATION_PREPARED",
        "job_id": req["job_id"],
        "session_id": req["session_id"],
        "action_index": index,
        "action_id": action.get("action_id"),
        "action": action.get("action"),
        "mutation_class": (
            "EXTERNAL_COMMIT"
            if action.get("side_effect") == "EXTERNAL_IRREVERSIBLE"
            else "LOCAL_UI_MUTATION"
        ),
        "resource_guard": req["resource_guard"],
        "resource_claim_id": req["resource_guard"]["claim_id"],
        "claim_generation": claim.get("claim_generation"),
        "state_epoch": proof["state_epoch"],
        "revision_before": int(proof["revision"]),
        "fingerprint_version": proof["fingerprint_version"],
        "state_hash_before": proof["state_hash"],
        "fingerprint_profile_id": proof["fingerprint_profile_id"],
        "request_sha256": request_sha,
    }


def _run_mutation(
    req: dict[str, Any],
    action: dict[str, Any],
    index: int,
    results: list[dict[str, Any]],
    *,
    started: float,
    request_sha: str,
    driver_run: DriverRun,
    activity_read: ActivityRead,
    journal_append: JournalAppend,
    checkpoint_write: CheckpointWrite,
    now_iso: NowIso,
    visual_evidence_provider: VisualEvidenceProvider | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    try:
        claim = resource_arbiter.assert_guard(req.get("resource_guard"))
    except resource_arbiter.ResourceError as exc:
        return None, _blocked(
            req, results, str(exc).split(":", 1)[0], started
        ), None

    try:
        proof = validate_state_guard(
            req,
            action,
            index,
            driver_run=driver_run,
            activity_read=activity_read,
        )
    except CoreV2Error as exc:
        return None, _blocked(
            req, results, str(exc).split(":", 1)[0], started
        ), None

    # A semantic selector with a vision fallback may become a visual click
    # inside the driver. Require fresh trusted evidence before even PREPARED.
    if action_may_use_visual_locator(action):
        try:
            visual_metrics = _jit_visual_guard(
                action, proof, visual_evidence_provider
            )
        except frame_guard.FrameGuardError as exc:
            journal_append({
                "timestamp": now_iso(),
                "phase": "VISUAL_DISPATCH_BLOCKED",
                "action_index": index,
                "action_id": action.get("action_id"),
                "error_code": exc.code,
                "failure_stage": exc.failure_stage,
                "action_attempts": 0,
            })
            terminal = _blocked(req, results, exc.code, started)
            terminal["error"]["failure_stage"] = exc.failure_stage
            return None, terminal, None
        journal_append({
            "timestamp": now_iso(),
            "phase": "FRAME_FRESHNESS_VERIFIED",
            "action_index": index,
            "action_id": action.get("action_id"),
            **visual_metrics,
        })

    journal_append(
        _prepared_row(
            req, action, index, claim, proof, request_sha, now_iso
        )
    )

    dispatch = json.loads(json.dumps(action))
    dispatch["retry"] = 0
    driver = driver_run(
        [dispatch], f"a{index:02d}-{dispatch['action']}"
    )
    action_result = _driver_action_result(driver, dispatch, index)

    action_data = action_result.get("data")
    postcondition_passed = (
        isinstance(action_data, dict)
        and action_data.get("postcondition_passed") is True
    )
    if action_result.get("status") != "PASS" or not postcondition_passed:
        ambiguity_code = (
            (action_result.get("error") or {}).get("code")
            if action_result.get("status") != "PASS"
            else "MUTATION_OUTCOME_UNKNOWN"
        ) or "MUTATION_RESULT_AMBIGUOUS"
        journal_append({
            "timestamp": now_iso(),
            "phase": "MUTATION_AMBIGUOUS",
            "action_index": index,
            "action_id": action.get("action_id"),
            "action": action.get("action"),
            "status": action_result.get("status"),
            "postcondition_passed": postcondition_passed,
            "reason": ambiguity_code,
            "retry_allowed": False,
        })
        terminal = {
            "status": "RECONCILE_REQUIRED",
            "job_id": req["job_id"],
            "session_id": req["session_id"],
            "protocol_version": 2,
            "actions": results + [action_result],
            "error": action_result.get("error") or {
                "code": ambiguity_code,
                "retryable": False,
            },
            "preflight": driver.get("preflight"),
            "host_duration_ms": round(
                (time.monotonic() - started) * 1000, 1
            ),
        }
        return action_result, terminal, driver.get("preflight")

    postcondition_kind = str(action_data.get("postcondition_kind") or "UNSPECIFIED")
    revision_before = int(proof["revision"])
    before, after = state_integrity.advance_revision()
    if before != revision_before or after != revision_before + 1:
        raise CoreV2Error("STATE_REVISION_ORDERING_FAILURE")

    journal_append({
        "timestamp": now_iso(),
        "phase": "MUTATION_COMMITTED",
        "job_id": req["job_id"],
        "session_id": req["session_id"],
        "action_index": index,
        "action_id": action.get("action_id"),
        "action": action.get("action"),
        "state_epoch": proof["state_epoch"],
        "revision_before": before,
        "revision_after": after,
        "postcondition": "PASS",
        "postcondition_kind": postcondition_kind,
        "fingerprint_version": proof["fingerprint_version"],
        "fingerprint_profile_id": proof["fingerprint_profile_id"],
        "resource_claim_id": req["resource_guard"]["claim_id"],
    })
    journal_append({
        "timestamp": now_iso(),
        "phase": "POSTCONDITION_PASS",
        "action_index": index,
        "action_id": action.get("action_id"),
        "action": action.get("action"),
        "side_effect": action.get("side_effect", "REVERSIBLE_LOCAL"),
        "status": "PASS",
        "safe_checkpoint": True,
    })
    checkpoint_write(index, True)
    return action_result, None, driver.get("preflight")


def run(
    req: dict[str, Any],
    *,
    driver_run: DriverRun,
    activity_read: ActivityRead,
    journal_append: JournalAppend,
    checkpoint_write: CheckpointWrite,
    cancel_check: CancelCheck,
    now_iso: NowIso,
    visual_evidence_provider: VisualEvidenceProvider | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    results: list[dict[str, Any]] = []
    first_preflight: dict[str, Any] | None = None
    request_sha = resource_arbiter.request_identity(req)

    for index, original_action in enumerate(req["actions"]):
        if cancel_check():
            return {
                "status": "CANCELLED",
                "job_id": req["job_id"],
                "session_id": req["session_id"],
                "protocol_version": 2,
                "actions": results,
                "host_duration_ms": round(
                    (time.monotonic() - started) * 1000, 1
                ),
            }

        action = json.loads(json.dumps(original_action))
        name = str(action["action"])

        if name not in _MUTATING:
            driver = driver_run([action], f"a{index:02d}-{name}")
            if first_preflight is None:
                first_preflight = driver.get("preflight")
            action_result = _driver_action_result(driver, action, index)
            results.append(action_result)
            journal_append({
                "timestamp": now_iso(),
                "phase": (
                    "POSTCONDITION_PASS"
                    if action_result.get("status") == "PASS"
                    else "ACTION_FAILED"
                ),
                "action_index": index,
                "action_id": action_result.get("action_id"),
                "action": name,
                "side_effect": "OBSERVE_ONLY",
                "status": action_result.get("status"),
                "safe_checkpoint": action_result.get("status") == "PASS",
            })
            if action_result.get("status") != "PASS":
                return {
                    "status": "FAILED",
                    "job_id": req["job_id"],
                    "session_id": req["session_id"],
                    "protocol_version": 2,
                    "actions": results,
                    "error": action_result.get("error"),
                    "preflight": first_preflight,
                    "host_duration_ms": round(
                        (time.monotonic() - started) * 1000, 1
                    ),
                }
            checkpoint_write(index, True)
            continue

        action_result, terminal, preflight = _run_mutation(
            req,
            action,
            index,
            results,
            started=started,
            request_sha=request_sha,
            driver_run=driver_run,
            activity_read=activity_read,
            journal_append=journal_append,
            checkpoint_write=checkpoint_write,
            now_iso=now_iso,
            visual_evidence_provider=visual_evidence_provider,
        )
        if first_preflight is None:
            first_preflight = preflight
        if terminal is not None:
            return terminal
        if action_result is not None:
            results.append(action_result)

    return {
        "status": "PASS",
        "job_id": req["job_id"],
        "session_id": req["session_id"],
        "protocol_version": 2,
        "driver_protocol_version": 1,
        "actions": results,
        "preflight": first_preflight,
        "host_duration_ms": round((time.monotonic() - started) * 1000, 1),
    }
