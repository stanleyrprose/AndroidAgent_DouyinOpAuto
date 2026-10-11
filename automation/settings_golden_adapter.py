"""Rev3.7 Settings Golden reversible UI workflow adapter (inactive).

Reuses previously observed Y700 Settings resource IDs and the existing
generic UI Core action schema. This is NOT an acceptance test invocation;
the adapter only assembles deterministic guarded steps and restore intent.
All execution remains disabled pending end-to-end Sprint 5 acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from automation.frozen_route_contracts import (
    select_frozen_route_readonly,
)

_SETTINGS = "com.android.settings"
_ROOT_SEARCH = f"{_SETTINGS}:id/search_bar_container"
_SEARCH_INPUT = "android:id/search_src_text"
_LIGHT_PARENT = f"{_SETTINGS}:id/dark_mode_white"
_DARK_PARENT = f"{_SETTINGS}:id/dark_mode_black"
_LIGHT_CHECK = f"{_SETTINGS}:id/dark_mode_white_check"
_DARK_CHECK = f"{_SETTINGS}:id/dark_mode_black_check"
# Must be explicitly opened by source-reviewed release after final acceptance.
_SETTINGS_GOLDEN_EXECUTION_ENABLED = False


class SettingsGoldenUnavailable(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SettingsMode:
    value: str
    checked_resource_id: str
    clickable_parent_id: str


_MODES = {
    "LIGHT": SettingsMode("LIGHT", _LIGHT_CHECK, _LIGHT_PARENT),
    "DARK": SettingsMode("DARK", _DARK_CHECK, _DARK_PARENT),
}


def classify_mode_checked(
    *,
    foreground_package: str,
    light_checked: bool | None,
    dark_checked: bool | None,
) -> SettingsMode:
    if foreground_package != _SETTINGS:
        raise SettingsGoldenUnavailable("SETTINGS_FOREGROUND_CHANGED")
    if (type(light_checked) is not bool or type(dark_checked) is not bool
            or light_checked == dark_checked):
        raise SettingsGoldenUnavailable("SETTINGS_MODE_AMBIGUOUS")
    return _MODES["LIGHT" if light_checked else "DARK"]


def _navigate() -> list[dict[str, Any]]:
    result_selector = {
        "class_name": "android.widget.LinearLayout",
        "clickable": True,
        "has_parent": {"resource_id": f"{_SETTINGS}:id/list_results"},
        "has_descendant": {
            "resource_id": "android:id/title", "text": "深色模式"},
    }
    return [
        {"action_id": "wait-settings", "action": "waitFor",
         "package": _SETTINGS, "timeout_ms": 8000},
        {"action_id": "wait-stable", "action": "waitStable",
         "timeout_ms": 5000},
        {"action_id": "open-search", "action": "click",
         "selector": {"resource_id": _ROOT_SEARCH, "clickable": True},
         "expect": {"selector": {
             "resource_id": _SEARCH_INPUT,
             "class_name": "android.widget.AutoCompleteTextView"},
             "unique": True}, "timeout_ms": 5000,
         "side_effect": "REVERSIBLE_LOCAL"},
        {"action_id": "type-search", "action": "inputText",
         "selector": {"resource_id": _SEARCH_INPUT,
                      "class_name": "android.widget.AutoCompleteTextView"},
         "text": "深色模式", "clear_first": True, "dismiss_ime": True,
         "side_effect": "REVERSIBLE_LOCAL"},
        {"action_id": "search-result", "action": "waitFor",
         "selector": result_selector, "unique": True,
         "timeout_ms": 8000},
        {"action_id": "open-result", "action": "click",
         "selector": result_selector,
         "expect": {"selector": {
             "resource_id": _LIGHT_CHECK}, "unique": True},
         "timeout_ms": 5000, "side_effect": "REVERSIBLE_LOCAL"},
        {"action_id": "stable-display", "action": "waitStable",
         "timeout_ms": 5000},
    ]


def _set_mode(target: SettingsMode, opposite: SettingsMode) -> list[dict[str, Any]]:
    return [
        {"action_id": "wait-target", "action": "waitFor",
         "selector": {"resource_id": target.clickable_parent_id,
                      "clickable": True}, "unique": True,
         "timeout_ms": 5000},
        {"action_id": "set-mode", "action": "click",
         "selector": {"resource_id": target.clickable_parent_id,
                      "clickable": True},
         "expect": {"selector": {
             "resource_id": target.checked_resource_id,
             "checked": True}, "unique": True},
         "side_effect": "REVERSIBLE_LOCAL", "timeout_ms": 5000},
        {"action_id": "assert-other-unchecked", "action": "assert",
         "selector": {
             "resource_id": opposite.checked_resource_id,
             "checked": False}},
    ]


def golden_change_restore_plan(
    *,
    current: SettingsMode,
    observed_revision: int,
    device_contract: str,
) -> dict[str, Any]:
    """Plan only; does not issue state token or click."""
    if current.value not in _MODES:
        raise SettingsGoldenUnavailable("SETTINGS_MODE_AMBIGUOUS")
    if type(observed_revision) is not int or observed_revision < 0:
        raise SettingsGoldenUnavailable("STATE_REVISION_UNAVAILABLE")
    opposite = _MODES["DARK" if current.value == "LIGHT" else "LIGHT"]
    selection = select_frozen_route_readonly(
        route_contract_id="settings.light-dark.v1",
        adapter_capability="android.ui.workflow",
        adapter_version="1.0",
        observed_target_state="SETTINGS_APPEARANCE_MATCH",
        observed_device_contract=device_contract,
        observed_revision=observed_revision,
        already_satisfied_verified=False,
        semantic_target_unique=True,
        visual_target_verified=False,
        host_primitive_ready=False,
        action_class="LOCAL_UI_MUTATION",
    )
    if selection["route_class"] != "SEMANTIC_UI":
        raise SettingsGoldenUnavailable("SETTINGS_ROUTE_UNAVAILABLE")
    return {
        "workflow_contract_version": 1,
        "initial_mode": current.value,
        "target_mode": opposite.value,
        "route": selection,
        "change": _navigate() + _set_mode(opposite, current),
        # Restoring across a crash requires a fresh navigation, resource
        # claim, state token and epoch/revision: never reuse old coordinates.
        "restore": _navigate() + _set_mode(current, opposite),
        "restore_requires_fresh_state_token": True,
        "restore_requires_current_claim": True,
        "app_relaunch_is_not_implicitly_authorized": True,
        "production_execution_enabled": False,
        "action_attempts": 0,
    }


def _foreground_from_observation(
    result: Mapping[str, Any], action_id: str,
) -> str:
    for row in result.get("actions", []):
        if not isinstance(row, dict) or row.get("action_id") != action_id:
            continue
        data = row.get("data")
        if (isinstance(data, dict)
                and isinstance(data.get("package"), str)
                and data["package"]):
            return data["package"]
    raise SettingsGoldenUnavailable("SETTINGS_FOREGROUND_EVIDENCE_UNAVAILABLE")


def _checked_from_find(result: Mapping[str, Any],
                       action_id: str) -> bool:
    """Require a typed, unambiguous checked property, never bool(None)."""
    for row in result.get("actions", []):
        if not isinstance(row, dict) or row.get("action_id") != action_id:
            continue
        data = row.get("data")
        element = data.get("element") if isinstance(data, dict) else None
        if isinstance(element, dict) and type(element.get("checked")) is bool:
            return element["checked"]
    raise SettingsGoldenUnavailable("SETTINGS_MODE_EVIDENCE_UNAVAILABLE")


def _run_bound_settings_actions(
    job: Any, *, step: str, actions: list[dict[str, Any]],
    guard: Mapping[str, Any],
    backend_job_id: str,
) -> dict[str, Any]:
    """Exact protocol-v2 subordinate job under the SAME current Claim.

    Does not run unless execute_settings_golden's separate release
    constant was accepted. No legacy direct UI driver path is used.
    """
    from automation import ui_job, resource_arbiter
    from automation.subjob_provenance import bind_subordinate_job
    from automation.capability_job_store import (
        _need, _root_dir, _atomic_new,
    )
    from pathlib import Path

    current = resource_arbiter.assert_guard(dict(guard))
    _need(current.get("backend_job_id") == backend_job_id
          and current.get("capability_job_id") == job.job_id
          and current.get("request_sha256") == job.request_sha256,
          "SETTINGS_RESOURCE_IDENTITY_MISMATCH")
    job_id = f"{backend_job_id}--settings-{step}-01"
    provenance = bind_subordinate_job(
        job, subjob_id=job_id, subjob_role="other-v1",
        mutation_expected=True, current_claim=guard,
        authoritative_claim_observer=current,
    )
    request = {
        "protocol_version": 2,
        "job_id": job_id,
        "max_duration_ms": 180000,
        "session_id": job_id + "-session-01",
        "auto_wake": False,
        "dismiss_keyguard": False,
        "resource_guard": dict(guard),
        "state_guard": {"mode": "AUTO", "max_age_ms": 5000},
        "actions": actions,
    }
    request_root = Path("/opt/y700/runtime/gateway-settings")
    _root_dir(request_root)
    request_path = request_root / (job_id + ".json")
    if request_path.exists() or request_path.is_symlink():
        raise SettingsGoldenUnavailable("SETTINGS_SUBJOB_RETRY_DENIED")
    # Use durable O_EXCL + fsync rather than a replaceable fixed .tmp
    # request; crash recovery must never silently replay this mutation.
    _atomic_new(request_path, request)
    # Any uncertain run keeps request evidence; no blind rerun/restore
    # under stale session/foreground activity or a new Claim ID.
    result = ui_job.run_workflow(request_path)
    if result.get("status") != "PASS":
        # Preserve the original request/provenance when completion is
        # unknown; never delete evidence and silently issue the same ID.
        raise SettingsGoldenUnavailable("SETTINGS_SUBJOB_RECONCILE_REQUIRED")
    # Durable completion receipt before returning to the parent Backend.
    # Do not store screenshots, raw selectors or a second mutation plan.
    _atomic_new(request_root / (job_id + ".receipt.json"), {
        "settings_subjob_receipt_version": 1,
        "capability_job_id": job.job_id,
        "backend_job_id": backend_job_id,
        "subjob_id": job_id,
        "subjob_status": "PASS",
        "claim_id": current.get("claim_id"),
        "owner_id": current.get("owner_id"),
        "request_path_retained": True,
        "replay_allowed": False,
    })
    # Leave the original request as an idempotency tombstone. A crash or
    # reconnect cannot re-execute a previously completed UI mutation.
    return result


def execute_settings_golden(
    job: Any, *,
    backend_job_id: str,
    current_resource_guard: Mapping[str, Any],
    device_contract: str,
) -> dict[str, Any]:
    """Reversible change/restore via existing UI Core, never direct input.

    Fresh initial checked properties are observed before choosing target.
    A durable baseline is recorded BEFORE the first Settings mode change.
    On any ambiguous mutation/restore the initial fact remains for explicit
    recovery; the adapter does not silently click with stale state.
    """
    if not _SETTINGS_GOLDEN_EXECUTION_ENABLED:
        raise SettingsGoldenUnavailable("SETTINGS_GOLDEN_RELEASE_GATE_CLOSED")
    from automation import resource_arbiter
    from automation.authoritative_state_reader import observe_authoritative_state
    from automation.capability_job_store import (
        _atomic_new, _locked, _read_json, _need, _utc,
    )

    current = resource_arbiter.assert_guard(dict(current_resource_guard))
    _need(current.get("owner_kind") == "CAPABILITY"
          and current.get("capability_job_id") == job.job_id
          and current.get("backend_job_id") == backend_job_id
          and current.get("request_sha256") == job.request_sha256,
          "SETTINGS_RESOURCE_IDENTITY_MISMATCH")
    _need(device_contract == "y700-android16-zui",
          "SETTINGS_DEVICE_CONTRACT_UNVERIFIED")
    _need(not (job.path / "effect-boundary.json").exists()
          and not (job.path / "result.json").exists()
          and not (job.path / "cancel.json").exists(),
          "SETTINGS_JOB_NOT_MUTABLE")

    # Initial navigation is reversible, but uses the same canonical
    # owner and a fresh AUTO StateToken at each mutation boundary.
    initial_actions = [
        {"action_id": "start-settings", "action": "appLaunch",
         "package": _SETTINGS, "side_effect": "REVERSIBLE_LOCAL"},
        *_navigate(),
        {"action_id": "initial-foreground", "action": "observe"},
        {"action_id": "initial-light", "action": "find",
         "selector": {"resource_id": _LIGHT_CHECK}},
        {"action_id": "initial-dark", "action": "find",
         "selector": {"resource_id": _DARK_CHECK}},
    ]
    initial_result = _run_bound_settings_actions(
        job, step="initial", actions=initial_actions,
        guard=current_resource_guard, backend_job_id=backend_job_id,
    )
    mode = classify_mode_checked(
        foreground_package=_foreground_from_observation(
            initial_result, "initial-foreground"),
        light_checked=_checked_from_find(initial_result, "initial-light"),
        dark_checked=_checked_from_find(initial_result, "initial-dark"),
    )
    observed = observe_authoritative_state()
    planned = golden_change_restore_plan(
        current=mode, observed_revision=observed.revision,
        device_contract=device_contract,
    )
    with _locked(job.path / "transition.lock"):
        _need(not (job.path / "settings-initial.json").exists(),
              "SETTINGS_REPLAY_DENIED")
        _atomic_new(job.path / "settings-initial.json", {
            "settings_golden_initial_version": 1,
            "capability_job_id": job.job_id,
            "backend_job_id": backend_job_id,
            "initial_mode": mode.value,
            "target_mode": planned["target_mode"],
            "resource_guard": dict(current_resource_guard),
            "observed_revision": observed.revision,
            "captured_at": _utc(),
            "restore_status": "NOT_YET_VERIFIED",
        })
    # The initial inspection left Settings on its inner dark-mode page.
    # Reenter the deterministic top-level route through guarded generic
    # Core primitives rather than assuming a prior instrumentation session
    # preserved its navigation hierarchy.
    change_actions = [
        {"action_id": "reset-settings", "action": "appForceStop",
         "package": _SETTINGS, "side_effect": "REVERSIBLE_LOCAL"},
        {"action_id": "launch-settings", "action": "appLaunch",
         "package": _SETTINGS, "side_effect": "REVERSIBLE_LOCAL"},
        *planned["change"],
    ]
    change_result = _run_bound_settings_actions(
        job, step="change", actions=change_actions,
        guard=current_resource_guard, backend_job_id=backend_job_id,
    )
    # The restoration is a distinct fresh Core v2 session. If Android
    # foreground/settings page drifted, Core fails closed; do not spoof
    # the original state token or send direct screen coordinates.
    restored = _run_bound_settings_actions(
        job, step="restore", actions=[
            {"action_id": "restore-relaunch", "action": "appForceStop",
             "package": _SETTINGS, "side_effect": "REVERSIBLE_LOCAL"},
            {"action_id": "restore-open", "action": "appLaunch",
             "package": _SETTINGS, "side_effect": "REVERSIBLE_LOCAL"},
            *planned["restore"],
        ],
        guard=current_resource_guard, backend_job_id=backend_job_id,
    )
    verify = _run_bound_settings_actions(
        job, step="verify", actions=[
            {"action_id": "restored-foreground", "action": "observe"},
            {"action_id": "restored-light", "action": "find",
             "selector": {"resource_id": _LIGHT_CHECK}},
            {"action_id": "restored-dark", "action": "find",
             "selector": {"resource_id": _DARK_CHECK}},
        ],
        guard=current_resource_guard, backend_job_id=backend_job_id,
    )
    final = classify_mode_checked(
        foreground_package=_foreground_from_observation(
            verify, "restored-foreground"),
        light_checked=_checked_from_find(verify, "restored-light"),
        dark_checked=_checked_from_find(verify, "restored-dark"),
    )
    _need(final.value == mode.value, "SETTINGS_RESTORE_NOT_VERIFIED")
    with _locked(job.path / "transition.lock"):
        _atomic_new(job.path / "settings-restore-result.json", {
            "settings_restore_result_version": 1,
            "capability_job_id": job.job_id,
            "backend_job_id": backend_job_id,
            "initial_mode": mode.value,
            "restored_mode": final.value,
            "restored_verified": True,
            "verified_at": _utc(),
        })
    return {
        "status": "VERIFIED",
        "initial_mode": mode.value,
        "restored_mode": final.value,
        "external_effect_attempts": 0,
        "resource_released_by_adapter": False,
    }
