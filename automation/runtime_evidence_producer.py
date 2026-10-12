"""Rev3.7 foreground privileged runtime evidence producer.

This is NOT a daemon or alternate Agent. Future authenticated local
controller calls this foreground helper to persist factual runtime
observations; Gateway only reads evidence from pre_admission_authority and
runtime_authority. No user input can supply permission/readiness booleans.

Deployment, principal verifier and physical app-compatibility acceptance
remain release-gated; this code is not used to open Gateway or D-G3.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import os
import re
from typing import Any, Mapping

from automation.authoritative_state_reader import observe_authoritative_state
from automation.capability_job_store import (
    CAP_JOBS, _atomic_replace, _atomic_new, _read_json, _sha,
    _root_dir, _need,
)
from automation.capability_catalog import load_catalog
from automation.resource_arbiter import read_claim, ResourceError
from automation.runtime_authority import EVIDENCE_ROOT
from automation.pre_admission_authority import ROOT as PRE_ADMISSION_ROOT
from automation.trusted_ingress_approval import (
    inspect_before_admission, IngressAuthorizationUnavailable,
    _root_owned_record, _utc,
)
from automation.recovery_inventory import inspect_startup_inventory_readonly

_EVIDENCE_WRITER_ACCEPTED = False
CLOCK_ROOT = Path("/opt/y700/runtime/trusted-clock")
PRINCIPAL_ROOT = Path("/opt/y700/runtime/trusted-principals")
CAPABILITY_PROBE_ROOT = Path("/opt/y700/runtime/capability-probes")
# Independently signed-off physical probes have not passed acceptance.
_CAPABILITY_PROBE_SOURCE_ACCEPTED = False
_JOB = re.compile(r"^cap-[0-9a-f]{48}$")


class EvidenceProductionUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise EvidenceProductionUnavailable(code)


def _accepted_runtime_probe(name: str, catalog_row: Mapping[str, Any]) -> dict[str, Any]:
    """Independent device/Bridge health, not a request-selected boolean."""
    if not _CAPABILITY_PROBE_SOURCE_ACCEPTED:
        raise EvidenceProductionUnavailable(
            "CAPABILITY_PROBE_SOURCE_NOT_ACCEPTED")
    from automation.authoritative_state_reader import observe_authoritative_state
    current = observe_authoritative_state()
    support = catalog_row.get("support_contract")
    _require(isinstance(support, dict)
             and isinstance(support.get("runtime_probe"), str)
             and isinstance(support.get("device_contracts"), list),
             "CAPABILITY_SUPPORT_CONTRACT_INVALID")
    allowed = {
        "android_device_observe_probe_v1",
        "android_ui_workflow_probe_v1",
        "android_root_exec_probe_v1",
        "tiktok_publish_probe_v1",
    }
    probe_id = support["runtime_probe"]
    _require(probe_id in allowed, "CAPABILITY_PROBE_ID_UNTRUSTED")
    evidence = _root_owned_record(
        CAPABILITY_PROBE_ROOT / (probe_id + ".json"))
    measured = evidence.get("observed_boottime_ms")
    _require(
        evidence.get("runtime_probe_version") == 1
        and evidence.get("source") == "Y700_TRUSTED_DEVICE_BRIDGE_PROBE"
        and evidence.get("capability") == name
        and evidence.get("probe_id") == probe_id
        and evidence.get("boot_id") == current.boot_id
        and evidence.get("state_epoch") == current.state_epoch
        and evidence.get("revision") == current.revision
        and evidence.get("device_contract") in support["device_contracts"]
        and type(measured) is int
        and 0 <= current.observed_boottime_ms - measured <= 1000,
        "CAPABILITY_PROBE_EVIDENCE_STALE")
    profile = catalog_row.get("execution_profile")
    _require(isinstance(profile, dict)
             and isinstance(profile.get("readiness_requirements"), list),
             "CAPABILITY_EXECUTION_PROFILE_INVALID")
    measured_checks = evidence.get("readiness_requirements")
    _require(isinstance(measured_checks, dict)
             and all(type(measured_checks.get(item)) is bool
                     for item in profile["readiness_requirements"]),
             "CAPABILITY_PROBE_DEPENDENCIES_UNAVAILABLE")
    for key in ("adapter_present", "runtime_compatible",
                "runtime_available", "runtime_degraded"):
        _require(type(evidence.get(key)) is bool,
                 "CAPABILITY_PROBE_FACTS_UNAVAILABLE")
    # BUSINESS App identity must match the pinned Catalog contract.
    if name == "tiktok.publish":
        app = catalog_row.get("app_ui_contract")
        _require(isinstance(app, dict)
                 and app.get("acceptance_status") == "ACCEPTED"
                 and isinstance(app.get("signing_cert_sha256"), str)
                 and len(app["signing_cert_sha256"]) == 64
                 and type(evidence.get("app_version_code")) is int
                 and evidence["app_version_code"]
                     in app.get("accepted_version_codes", [])
                 and evidence.get("app_signing_cert_sha256")
                     == app["signing_cert_sha256"]
                 and evidence.get("app_ui_contract_version")
                     == app.get("ui_contract_version")
                 and evidence.get("app_ui_contract_match") is True,
                 "APP_UI_CONTRACT_NOT_ACCEPTED")
    return evidence


def _ready_facts(
    name: str, *, capability_job_id: str | None = None,
) -> dict[str, bool]:
    """Conservative local facts, never infer TikTok/Settings UI acceptance."""
    catalog = load_catalog()
    _require(name in catalog, "CAPABILITY_NOT_REGISTERED")
    actual = catalog[name]
    claim = read_claim()  # unavailable/corrupt claim is fatal, not free.
    recovered = inspect_startup_inventory_readonly()
    _require(recovered.get("status") == "READ_ONLY_STARTUP_INVENTORY",
             "RUNTIME_RECOVERY_INVENTORY_UNAVAILABLE")
    # A synchronously running exact current Backend is not equivalent
    # to another unreconciled owner. Exclude self ONLY when its durable
    # state has positive non-uncertain evidence, never on job ID alone.
    untrusted_job = False
    for row in recovered.get("active_jobs", []):
        if row.get("status") not in {
            "RECONCILE_REQUIRED", "TERMINAL_ARCHIVE_PENDING",
        }:
            continue
        job_id = row.get("capability_job_id")
        if (capability_job_id is not None
                and job_id == capability_job_id
                and row.get("status") == "RECONCILE_REQUIRED"):
            path = CAP_JOBS / "active" / capability_job_id
            status = _read_json(path / "state.json")
            effect_path = path / "effect-boundary.json"
            safe_self = (
                status.get("phase") in {
                    "BACKEND_BOUND", "WAITING_RESOURCE",
                    "BACKEND_SUBMITTED", "RUNNING_SAFE",
                }
                and status.get("effect_uncertain") is False
                and status.get("mutation_uncertain") is False
                and not effect_path.exists()
            )
            if safe_self:
                continue
        untrusted_job = True
        break
    # Supported != ready. Only an independently accepted physical/runtime
    # probe of this exact capability can establish positive readiness.
    probe = _accepted_runtime_probe(name, actual)
    profile = actual["execution_profile"]
    requirements = probe["readiness_requirements"]
    dependencies = all(
        requirements.get(item) is True
        for item in profile["readiness_requirements"]
    )
    return {
        "adapter_present": probe["adapter_present"] is True,
        # Accepted Catalog configuration is not live device evidence:
        # the current root-owned physical probe must ALSO affirm the
        # app/signing/UI contract, including after TikTok auto-updates.
        "app_ui_contract_match": (
            True if name in {
                "android.device.observe", "android.root.exec",
            } else (
                probe.get("app_ui_contract_match") is True
                if name == "android.ui.workflow"
                else (
                    actual["app_ui_contract"].get("acceptance_status")
                        == "ACCEPTED"
                    and probe.get("app_ui_contract_match") is True
                )
            )
        ),
        "runtime_compatible": probe["runtime_compatible"] is True,
        "reconcile_required": bool(untrusted_job),
        "resource_busy": claim is not None and (
            capability_job_id is None
            or claim.get("capability_job_id") != capability_job_id),
        "dependencies_ready": dependencies,
        "runtime_available": probe["runtime_available"] is True,
        "runtime_degraded": bool(
            untrusted_job or probe["runtime_degraded"]),
    }


def _clock_verified(boot_id: str, observed_ms: int) -> bool:
    try:
        clock = _root_owned_record(CLOCK_ROOT / "clock-health.json")
    except (OSError, ValueError, IngressAuthorizationUnavailable):
        return False
    at = clock.get("observed_boottime_ms")
    return bool(
        clock.get("clock_health_version") == 1
        and clock.get("source") == "Y700_TRUSTED_CLOCK_SENSOR"
        and clock.get("boot_id") == boot_id
        and clock.get("synchronized") is True
        and type(at) is int and 0 <= observed_ms - at <= 30000
    )


def _authenticated_principal(
    request: Mapping[str, Any], policy: Mapping[str, Any],
) -> tuple[bool, bool]:
    """Root-owned first-party principal; NEVER caller-provided booleans."""
    capability = request.get("capability")
    payload = request.get("payload")
    if (capability == "tiktok.publish"
            and isinstance(payload, Mapping)
            and payload.get("publish_mode") == "COMMIT"):
        proof = inspect_before_admission(
            request=request, effective_policy=policy,
            current_clock_health="HEALTHY")
        _require(proof.get("authenticated_control_plane_fact") is True,
                 "INGRESS_AUTHORIZATION_UNAVAILABLE")
        return True, True
    data = _root_owned_record(
        PRINCIPAL_ROOT / (_sha(request) + ".json"))
    current = datetime.now(timezone.utc)
    expires_at = _utc(data.get("expires_at"))
    _require(
        data.get("principal_contract_version") == 1
        and data.get("source") == "TRUSTED_FIRST_PARTY_CONTROLLER"
        and data.get("request_sha256") == _sha(request)
        and data.get("effective_policy_sha256") == _sha(policy)
        and data.get("authenticated") is True
        and isinstance(data.get("principal_id"), str)
        and len(data["principal_id"]) > 0
        and current < expires_at
        and (expires_at - current).total_seconds() <= 3600,
        "PRINCIPAL_IDENTITY_UNVERIFIED",
    )
    return True, data.get("explicit_approval_verified") is True


def _document(
    *,
    request: Mapping[str, Any], policy: Mapping[str, Any],
    capability_job_id: str | None = None,
) -> dict[str, Any]:
    state = observe_authoritative_state()
    _require(os.geteuid() == 0, "RUNTIME_EVIDENCE_REQUIRES_ROOT")
    runtime = _ready_facts(
        str(request.get("capability", "")),
        capability_job_id=capability_job_id)
    verified_clock = _clock_verified(
        state.boot_id, state.observed_boottime_ms)
    _require(verified_clock, "CLOCK_SUSPECT")
    authenticated, approved = _authenticated_principal(request, policy)
    identity = {
        "identity_authenticated": authenticated,
        "effective_policy_allows": bool(
            authenticated and policy.get("version") == 1),
        "current_approval_valid": approved,
    }
    return {
        "producer": "Y700_TRUSTED_PRE_ADMISSION_OBSERVER",
        "evidence_version": 1,
        "request_sha256": _sha(request),
        "effective_policy_sha256": _sha(policy),
        "capability": request.get("capability"),
        "boot_id": state.boot_id,
        "state_epoch": state.state_epoch,
        "revision": state.revision,
        "observed_boottime_ms": state.observed_boottime_ms,
        # Until accepted system time synchronization evidence exists,
        # release-gated issuer cannot claim HEALTY.
        "clock_health": "HEALTHY" if verified_clock else "UNKNOWN",
        "runtime_facts": runtime,
        "identity_facts": identity,
    }


def _write_restricted(folder: Path, filename: str,
                      record: Mapping[str, Any]) -> None:
    _root_dir(folder)
    target = folder / filename
    _require(os.geteuid() == 0
             and folder.stat().st_uid == 0
             and not folder.is_symlink(),
             "RUNTIME_EVIDENCE_ROOT_UNTRUSTED")
    # All evidence is ephemeral observation, NOT approval or an effect
    # journal. Replacing previous measurement cannot extend a TTL.
    if target.exists():
        old = _read_json(target)
        _require(
            old.get("request_sha256") == record.get("request_sha256")
            and old.get("effective_policy_sha256")
                == record.get("effective_policy_sha256"),
            "RUNTIME_EVIDENCE_IDENTITY_CONFLICT")
        _atomic_replace(target, record)
    else:
        _atomic_new(target, record)


def publish_pre_admission_readonly(
    *, request: Mapping[str, Any],
    effective_policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Future accepted root foreground ingress emits one exact measurement."""
    if not _EVIDENCE_WRITER_ACCEPTED:
        raise EvidenceProductionUnavailable(
            "RUNTIME_EVIDENCE_WRITER_NOT_ACCEPTED")
    _require(isinstance(request, Mapping)
             and isinstance(effective_policy, Mapping),
             "RUNTIME_EVIDENCE_CONTRACT_INVALID")
    # _document independently reads a first-party root-owned principal
    # and a fresh trusted-clock proof. It does not trust request booleans.
    facts = _document(request=request, policy=effective_policy)
    key = facts["request_sha256"] + ".json"
    _write_restricted(PRE_ADMISSION_ROOT, key, facts)
    return {
        "status": "PRE_ADMISSION_EVIDENCE_WRITTEN",
        "request_sha256": facts["request_sha256"],
        "effective_policy_sha256": facts["effective_policy_sha256"],
        "ui_mutation_attempts": 0,
        "production_dispatch_authorized": False,
    }


def publish_post_admission_readonly(
    *, capability_job_id: str, backend_job_id: str,
) -> dict[str, Any]:
    """Resample facts after resource wait for the EXACT existing job."""
    if not _EVIDENCE_WRITER_ACCEPTED:
        raise EvidenceProductionUnavailable(
            "RUNTIME_EVIDENCE_WRITER_NOT_ACCEPTED")
    _require(isinstance(capability_job_id, str)
             and _JOB.fullmatch(capability_job_id) is not None
             and isinstance(backend_job_id, str)
             and backend_job_id.startswith(capability_job_id + "--"),
             "RUNTIME_EVIDENCE_IDENTITY_INVALID")
    source = CAP_JOBS / "active" / capability_job_id
    _require(source.is_dir() and not source.is_symlink(),
             "RUNTIME_EVIDENCE_JOB_UNAVAILABLE")
    identity = _read_json(source / "identity.json")
    backend = _read_json(source / "backend.json")
    request = _read_json(source / "request.json")
    policy = _read_json(source / "effective_policy.json")
    _require(identity.get("capability_job_id") == capability_job_id
             and identity.get("request_sha256") == _sha(request)
             and identity.get("effective_policy_sha256") == _sha(policy)
             and backend.get("capability_job_id") == capability_job_id
             and backend.get("backend_job_id") == backend_job_id
             and backend.get("request_sha256") == _sha(request),
             "RUNTIME_EVIDENCE_JOB_IDENTITY_MISMATCH")
    doc = _document(
        request=request, policy=policy,
        capability_job_id=capability_job_id,
    )
    doc.update({
        "producer": "Y700_TRUSTED_RUNTIME_OBSERVER",
        "authority_evidence_version": 1,
        "producer_contract_version": 1,
        "capability_job_id": capability_job_id,
        "backend_job_id": backend_job_id,
    })
    doc.pop("evidence_version", None)
    doc.pop("capability", None)
    _write_restricted(
        EVIDENCE_ROOT, capability_job_id + ".json", doc)
    return {
        "status": "POST_ADMISSION_EVIDENCE_WRITTEN",
        "capability_job_id": capability_job_id,
        "backend_job_id": backend_job_id,
        "request_sha256": doc["request_sha256"],
        "ui_mutation_attempts": 0,
        "production_dispatch_authorized": False,
    }
