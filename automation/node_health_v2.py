"""Rev3.7 on-demand stage health schema v2 (source-only candidate).

Health is a diagnostic snapshot, never execution authorization.
"alive" means only a read-only host process observation; "ready" needs
fresh independently verified support/permission/readiness evidence.

Stages remain UNKNOWN until their exact accepted observer receipts exist.
No background daemon, no passive template training, no network probe,
no Android UI input, and no implicit repairs or admission.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import os
import stat

from automation.authoritative_state_reader import (
    observe_authoritative_state, AuthorityUnavailable,
)
from automation.capability_catalog import (
    load_catalog, CatalogUnavailable, public_definition,
)
from automation.capability_axes import inspect_capability_readonly
from automation.capability_job_store import CapabilityStoreError, _read_json
from automation.recovery_inventory import inspect_startup_inventory_readonly
from automation.resource_arbiter import ResourceError, read_claim

_STAGES = (
    "connectivity", "observation", "frame", "freshness",
    "localization", "permission", "dispatch",
    "postcondition", "verification",
)
_STAGE_PROBES = Path("/opt/y700/runtime/health-stage-probes")
_HEALTH_OUTPUT = Path("/opt/y700/runtime/node-health.json")
_HEALTH_PERSISTENCE_ACCEPTED = False
_STAGE_PRODUCER_ACCEPTED = False


def _stage(name: str, *, status: str = "UNKNOWN",
           reason: str = "INDEPENDENT_STAGE_EVIDENCE_UNAVAILABLE",
           source: str = "NONE", age_ms: int | None = None) -> dict[str, Any]:
    return {
        "stage": name, "status": status,
        "reason_code": reason, "evidence_source": source,
        "evidence_age_ms": age_ms,
        "execution_authorized": False,
    }


def _fixed_stage_evidence(
    stage_name: str, observed_boottime_ms: int,
) -> dict[str, Any] | None:
    """Future accepted root-only source, never a caller-supplied probe."""
    from automation.publisher_boundary_guard import (
        PublisherBoundaryError, _strict_json,
    )
    if not _STAGE_PRODUCER_ACCEPTED:
        return None
    path = _STAGE_PROBES / (stage_name + ".json")
    try:
        parent = path.parent.lstat()
        if (not stat.S_ISDIR(parent.st_mode)
                or parent.st_uid != 0
                or stat.S_IMODE(parent.st_mode) != 0o700):
            return None
        receipt = _strict_json(path)
        seen = receipt.get("observed_boottime_ms")
        if not (
            receipt.get("stage_health_version") == 1
            and receipt.get("stage") == stage_name
            and receipt.get("source") == "Y700_ACCEPTED_STAGE_OBSERVER"
            and receipt.get("result") in {"PASS", "FAIL"}
            and type(seen) is int
            and 0 <= observed_boottime_ms - seen <= 1500
        ):
            return None
        return {
            "stage": stage_name,
            "status": "PASS" if receipt["result"] == "PASS" else "FAIL",
            "reason_code": receipt.get("reason_code")
                           if receipt["result"] == "FAIL" else None,
            "evidence_source": "Y700_ACCEPTED_STAGE_OBSERVER",
            "evidence_age_ms": observed_boottime_ms - seen,
            "execution_authorized": False,
        }
    except (OSError, ValueError, KeyError, PublisherBoundaryError):
        return None


def inspect_node_health_readonly() -> dict[str, Any]:
    """Non-authorizing structured health; UNKNOWN is first-class."""
    observed = None
    sot_reason = None
    try:
        observed = observe_authoritative_state()
    except AuthorityUnavailable as exc:
        sot_reason = exc.code
    try:
        claim = read_claim()
        claim_busy = claim is not None
        claim_reason = "ANDROID_UI_CLAIM_BUSY" if claim_busy else None
    except ResourceError:
        claim_busy = None
        claim_reason = "ANDROID_UI_CLAIM_UNAVAILABLE"

    crash = inspect_startup_inventory_readonly()
    recovery_ok = crash.get("status") == "READ_ONLY_STARTUP_INVENTORY"
    unresolved = (
        not recovery_ok
        or any(row.get("status") in {
            "RECONCILE_REQUIRED", "TERMINAL_ARCHIVE_PENDING",
        } for row in crash.get("active_jobs", []))
        or crash.get("staging_count", 0) != 0
    )
    try:
        catalog = load_catalog()
    except CatalogUnavailable:
        catalog = {}

    stage_data: dict[str, dict[str, Any]] = {
        key: _stage(key) for key in _STAGES
    }
    if observed is not None:
        # SOT observation is a positive local fact, not a Bridge-v2
        # connectivity or visual frame/locator acceptance.
        stage_data["observation"] = _stage(
            "observation", status="PASS", reason="SOT_READ_ONLY_OBSERVED",
            source="ROOT_OWNED_STATE_INTEGRITY")
        # Candidate stage probes remain diagnostic only, and must have
        # a separately accepted producer. Here no stage can self-approve.
        for key in _STAGES:
            if key == "observation":
                continue
            candidate = _fixed_stage_evidence(
                key, observed.observed_boottime_ms)
            if candidate is not None:
                stage_data[key] = candidate
    else:
        stage_data["observation"] = _stage(
            "observation", status="FAIL",
            reason=sot_reason or "SOT_UNAVAILABLE",
            source="ROOT_OWNED_STATE_INTEGRITY")
    # Permission cannot be verified from a support Catalog or diagnostics
    # file alone. Keep stage UNKNOWN if authority is not accepted.
    permission_result = stage_data["permission"]
    permission_ok = (
        permission_result.get("status") == "PASS"
        and permission_result.get("evidence_source")
            == "Y700_ACCEPTED_STAGE_OBSERVER"
    )
    failed = [k for k, v in stage_data.items()
              if v.get("status") == "FAIL"]
    successes = [k for k, v in stage_data.items()
                 if v.get("status") == "PASS"]
    unobserved = [k for k, v in stage_data.items()
                  if v.get("status") == "UNKNOWN"]
    overall = (
        "BLOCKED_RECONCILE" if unresolved else
        "BUSY" if claim_busy is True else
        "UNAVAILABLE" if observed is None else
        "DEGRADED" if failed else
        "UNKNOWN" if unobserved or not permission_ok else
        "UNKNOWN"  # code-release gates are still CLOSED
    )
    capabilities = []
    for name, definition in sorted(catalog.items()):
        support = inspect_capability_readonly(
            name, runtime_facts={}, trusted_policy_facts={},
            catalog_advertised=definition.get("enabled") is True,
        )
        capabilities.append({
            "capability": name,
            "definition": public_definition(definition),
            "support": support.support.as_dict(),
            "permission": support.permission.as_dict(),
            "readiness": support.readiness.as_dict(),
        })
    return {
        "health_schema_version": 2,
        "status": overall,
        "host_alive_observed": os.getpid() > 0,
        "runtime_ready": False,
        "dg3_status": "OPEN",
        "business_commit_authorized": False,
        "failure_stage": failed[0] if failed else (
            "RECOVERY" if unresolved else None),
        "last_success_stage": successes[-1] if successes else None,
        "reason_code": (
            "UNRESOLVED_RESOURCE_OR_BACKEND" if unresolved
            else claim_reason if claim_reason
            else sot_reason if sot_reason
            else "STAGE_EVIDENCE_INCOMPLETE"
        ),
        "stage_observations": [stage_data[k] for k in _STAGES],
        "stage_unknown_count": len(unobserved),
        "capabilities": capabilities,
        "capability_catalog_entry_count": len(catalog),
        "unresolved_reconcile": unresolved,
        "android_ui_claim_busy": claim_busy,
        "release_state": "NOT_POSITIVELY_VERIFIED",
        "report_authorizes_execution": False,
        "observation_only": True,
    }


def persist_health_snapshot_after_acceptance() -> dict[str, Any]:
    """On-demand only; never the source of an execution permission token."""
    if not _HEALTH_PERSISTENCE_ACCEPTED:
        raise CapabilityStoreError("NODE_HEALTH_PERSISTENCE_GATE_CLOSED")
    from automation.capability_job_store import _atomic_replace, _atomic_new
    record = inspect_node_health_readonly()
    if _HEALTH_OUTPUT.exists():
        _atomic_replace(_HEALTH_OUTPUT, record)
    else:
        _atomic_new(_HEALTH_OUTPUT, record)
    return record
