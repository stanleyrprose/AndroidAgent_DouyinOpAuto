"""Rev3.7 source-owned producer for generation-bound UI stop receipts.

Only a separately accepted native/Bridge sensor can prove physical Android
mutator quiescence. This foreground adapter binds that independent evidence
to the CURRENT root-owned Claim generation and completed UI Core jobs,
then atomically records a reusable exact-Claim stop receipt.

No wake, click, backend retry, forced stop or release occurs. Both producer
and physical sensor acceptance remain FALSE during code development.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import re

from automation import resource_arbiter
from automation.authoritative_state_reader import observe_authoritative_state
from automation.capability_job_store import (
    _atomic_new, _atomic_replace, _read_json, _root_dir,
)
from automation.publisher_boundary_guard import _strict_json
from automation.resource_stop_observer import _NATIVE_STOP_ROOT

_NATIVE_SENSOR = Path("/opt/y700/runtime/native-ui-quiescence")
_UI_JOBS = Path("/opt/y700/ui-jobs")
_STOP_ISSUER_ACCEPTED = False
_NATIVE_STOP_SENSOR_ACCEPTED = False
_CLAIM_ID = re.compile(r"^ui-claim-[0-9a-f]{32}$")


class NativeStopReceiptUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _need(value: bool, code: str) -> None:
    if not value:
        raise NativeStopReceiptUnavailable(code)


def _ui_core_children_terminated(claim_id: str) -> tuple[bool, int]:
    """Check exact durable descendants, not an empty active-claim slot."""
    _need(_UI_JOBS.is_dir() and not _UI_JOBS.is_symlink(),
          "UI_CORE_JOBS_ROOT_UNAVAILABLE")
    count = 0
    scanned = 0
    for folder in _UI_JOBS.iterdir():
        scanned += 1
        _need(scanned <= 1000, "UI_CORE_JOB_INVENTORY_OVERSIZE")
        _need(folder.is_dir() and not folder.is_symlink(),
              "UI_CORE_JOB_DIRECTORY_UNTRUSTED")
        workflow = folder / "workflow.json"
        if not workflow.exists() or workflow.is_symlink():
            # Unknown job identity is not a completed subordinate.
            raise NativeStopReceiptUnavailable("UI_CORE_JOB_IDENTITY_UNKNOWN")
        row = _read_json(workflow)
        guard = row.get("resource_guard")
        if not isinstance(guard, dict) or guard.get("claim_id") != claim_id:
            continue
        count += 1
        result = _read_json(folder / "result.json")
        _need(result.get("status") in {"PASS", "FAILED", "CANCELLED"}
              and result.get("job_id") == row.get("job_id"),
              "UI_CORE_SUBJOB_TERMINAL_UNPROVEN")
    return True, count


def publish_generation_bound_stop_receipt(
    *, exact_claim: Mapping[str, Any],
    backend_job_id: str,
) -> dict[str, Any]:
    """No caller-provided 'stopped=true' or arbitrary native source path."""
    if not _STOP_ISSUER_ACCEPTED or not _NATIVE_STOP_SENSOR_ACCEPTED:
        raise NativeStopReceiptUnavailable("NATIVE_STOP_ISSUER_NOT_ACCEPTED")
    _need(isinstance(exact_claim, Mapping)
          and isinstance(backend_job_id, str)
          and backend_job_id, "NATIVE_STOP_IDENTITY_INVALID")
    claim = resource_arbiter.assert_guard(dict(exact_claim))
    claim_id = claim.get("claim_id")
    generation = claim.get("ui_execution_generation")
    _need(isinstance(claim_id, str)
          and _CLAIM_ID.fullmatch(claim_id) is not None
          and claim.get("backend_job_id") == backend_job_id
          and type(generation) is int and generation > 0
          and claim.get("active_ui_job_id") is None
          and claim.get("active_session_id") is None
          and claim.get("active_backend_type") is None
          and claim.get("reconcile_required") is not True,
          "NATIVE_STOP_CLAIM_NOT_QUIESCENT")
    before = observe_authoritative_state()
    physical = _strict_json(_NATIVE_SENSOR / (claim_id + ".json"))
    after = observe_authoritative_state()
    at = physical.get("observed_boottime_ms")
    _need(before.boot_id == after.boot_id
          and before.state_epoch == after.state_epoch
          and before.revision == after.revision
          and physical.get("native_quiescence_version") == 1
          and physical.get("source") == "Y700_ACCEPTED_NATIVE_DRIVER_AND_BRIDGE"
          and physical.get("claim_id") == claim_id
          and physical.get("owner_id") == claim.get("owner_id")
          and physical.get("backend_job_id") == backend_job_id
          and physical.get("ui_execution_generation") == generation
          and physical.get("boot_id") == after.boot_id
          and physical.get("state_epoch") == after.state_epoch
          and physical.get("native_ui_subjobs_absent") is True
          and physical.get("linux_child_mutators_absent") is True
          and physical.get("backend_terminal_positive") is True
          and type(at) is int
          and 0 <= after.observed_boottime_ms - at <= 1000,
          "NATIVE_STOP_PHYSICAL_PROOF_STALE")
    _, descendant_count = _ui_core_children_terminated(claim_id)
    # Recheck current Claim AFTER scanning all descendant receipts. If a
    # new UI execution began, its generation changed and the proof loses.
    current = resource_arbiter.assert_guard(dict(exact_claim))
    _need(current.get("ui_execution_generation") == generation
          and current.get("active_ui_job_id") is None
          and current.get("active_session_id") is None,
          "NATIVE_STOP_CLAIM_CHANGED")
    _root_dir(_NATIVE_STOP_ROOT)
    record = {
        "native_stop_receipt_version": 1,
        "source": "Y700_NATIVE_DRIVER_AND_BRIDGE",
        "claim_id": claim_id,
        "owner_id": current["owner_id"],
        "backend_job_id": backend_job_id,
        "boot_id": after.boot_id,
        "state_epoch": after.state_epoch,
        "ui_execution_generation": generation,
        "observed_boottime_ms": after.observed_boottime_ms,
        "native_ui_subjobs_absent": True,
        "linux_child_mutators_absent": True,
        "all_subordinates_terminal_positive": True,
        "backend_terminal_positive": True,
        "ui_core_descendant_count": descendant_count,
    }
    target = _NATIVE_STOP_ROOT / (claim_id + ".json")
    if target.exists() or target.is_symlink():
        previous = _read_json(target)
        _need(previous.get("claim_id") == claim_id
              and previous.get("owner_id") == current["owner_id"]
              and previous.get("backend_job_id") == backend_job_id
              and type(previous.get("ui_execution_generation")) is int
              and previous["ui_execution_generation"] <= generation,
              "NATIVE_STOP_RECEIPT_REBIND_DENIED")
        _atomic_replace(target, record)
    else:
        _atomic_new(target, record)
    return {
        "status": "NATIVE_STOP_RECEIPT_WRITTEN",
        "claim_id": claim_id,
        "ui_execution_generation": generation,
        "descendant_count": descendant_count,
        "business_outcome_mutated": False,
        "claim_released": False,
        "external_effect_attempts": 0,
    }
