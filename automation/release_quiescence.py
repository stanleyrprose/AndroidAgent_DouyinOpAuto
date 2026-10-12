"""Rev3.7 read-only quiescence/upgrade blocker evidence.

A dormant, foreground-only release observer. It NEVER claims that no Android
mutator exists from absence of a Linux PID alone: native Android processes
and already-dispatched commands need an accepted independent observer.
Unresolved effect boundary, candidate owner drift, durable UI claim, or
any unreadable active job blocks upgrade. No subprocess, mutation, repair
or symlink switch is performed here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import json
import os
import stat

from automation.release_lifecycle import QuiescenceProof
from automation.release_integrity import (
    ReleaseIntegrityUnavailable, verify_signed_candidate_readonly,
)
from automation.resource_arbiter import read_claim, ResourceError
from automation.capability_job_store import (
    CapabilityStoreError, _read_json,
)
from automation.admission_fence import observe_admission_fence_readonly
from automation.publisher_boundary_guard import (
    _strict_json, PublisherBoundaryError,
)
from automation.authoritative_state_reader import (
    AuthorityUnavailable, observe_authoritative_state,
)

CAPABILITY_JOBS = Path("/opt/y700/capability-jobs/active")
CAPABILITY_STAGING = Path("/opt/y700/capability-jobs/.staging")
RELEASE_ADMISSION_HOLD = Path("/opt/y700/runtime/release-admissions-held.json")
NATIVE_QUIESCENCE_PATH = Path("/opt/y700/runtime/native-release-quiescence.json")
OFFLINE_GATES_PATH = Path("/opt/y700/runtime/release-offline-gates.json")
_NATIVE_QUIESCENCE_SOURCE_ACCEPTED = False
_OFFLINE_GATE_SOURCE_ACCEPTED = False


def inspect_upgrade_quiescence_readonly(
    *,
    candidate_dir: Path,
) -> dict[str, Any]:
    """Read only protected source receipts; no caller readiness booleans."""
    """Conservative evidence collection; NEVER itself grants upgrade."""
    reasons: list[str] = []
    candidate_verified = False
    try:
        candidate = verify_signed_candidate_readonly(candidate_dir)
        candidate_verified = (
            candidate.get("signature_verified") is True
            and candidate.get("all_listed_files_match") is True)
    except ReleaseIntegrityUnavailable as exc:
        reasons.append(exc.code)

    try:
        claim = read_claim()
        resolved_claim = claim is None
        if not resolved_claim:
            reasons.append("ANDROID_UI_CLAIM_UNRESOLVED")
    except ResourceError:
        resolved_claim = False
        reasons.append("ANDROID_UI_CLAIM_UNREADABLE")

    no_unsafe_jobs = True
    no_live_capability_jobs = True
    no_staging_jobs = True
    try:
        # Crash remnants in .staging may be an incomplete admission or an
        # unindexed durable identity. They cannot silently disappear just
        # because active/ is empty when an upgrade fence is installed.
        if not CAPABILITY_STAGING.is_dir() or CAPABILITY_STAGING.is_symlink():
            raise CapabilityStoreError("STAGING_JOBS_ROOT_UNAVAILABLE")
        staging_before = {
            child.name: (child.lstat().st_dev, child.lstat().st_ino)
            for child in CAPABILITY_STAGING.iterdir()
        }
        if len(staging_before) > 1000:
            raise CapabilityStoreError("STAGING_INVENTORY_OVERSIZE")
        if staging_before:
            no_staging_jobs = False
            no_unsafe_jobs = False
            reasons.append("ADMISSION_STAGING_NOT_RECONCILED")
        if not CAPABILITY_JOBS.is_dir() or CAPABILITY_JOBS.is_symlink():
            raise CapabilityStoreError("ACTIVE_JOBS_ROOT_UNAVAILABLE")
        active_before = {
            child.name: (child.lstat().st_dev, child.lstat().st_ino)
            for child in CAPABILITY_JOBS.iterdir()
        }
        if len(active_before) > 1000:
            raise CapabilityStoreError("ACTIVE_INVENTORY_OVERSIZE")
        for job in CAPABILITY_JOBS.iterdir():
            if not job.is_dir() or job.is_symlink():
                raise CapabilityStoreError("ACTIVE_JOBS_PATH_UNTRUSTED")
            no_live_capability_jobs = False
            # Even an apparently PRE-SUBMIT job is not automatically
            # quiescent: its exact backend might exist after crash.
            status = _read_json(job / "state.json")
            if (status.get("phase") in {
                    "RUNNING_UNSAFE", "BACKEND_SUBMITTING",
                    "RECONCILE_REQUIRED", "VERIFYING",
                } or (job / "effect-boundary.json").exists()):
                no_unsafe_jobs = False
            if (status.get("effect_uncertain")
                    or status.get("mutation_uncertain")):
                no_unsafe_jobs = False
        active_after = {
            child.name: (child.lstat().st_dev, child.lstat().st_ino)
            for child in CAPABILITY_JOBS.iterdir()
        }
        staging_after = {
            child.name: (child.lstat().st_dev, child.lstat().st_ino)
            for child in CAPABILITY_STAGING.iterdir()
        }
        if active_before != active_after or staging_before != staging_after:
            raise CapabilityStoreError("CAPABILITY_INVENTORY_CHANGED_DURING_SCAN")
    except (OSError, CapabilityStoreError) as exc:
        no_live_capability_jobs = False
        no_staging_jobs = False
        no_unsafe_jobs = False
        reasons.append("ACTIVE_JOBS_UNREADABLE")
    if not no_live_capability_jobs:
        reasons.append("CAPABILITY_JOBS_NOT_QUIESCENT")
    if not no_unsafe_jobs:
        reasons.append("UNRESOLVED_UNSAFE_CAPABILITY")

    # Production sources are fixed root-owned observer records, never a
    # caller-supplied bool. Missing accepted producer -> UNKNOWN/BLOCKED.
    native_absence_supported = False
    if _NATIVE_QUIESCENCE_SOURCE_ACCEPTED:
        try:
            current = observe_authoritative_state()
            proof = _strict_json(NATIVE_QUIESCENCE_PATH)
            observed = proof.get("observed_boottime_ms")
            native_absence_supported = (
                proof.get("native_quiescence_version") == 1
                and proof.get("source") == "Y700_NATIVE_DRIVER_AND_BRIDGE"
                and proof.get("boot_id") == current.boot_id
                and proof.get("state_epoch") == current.state_epoch
                and proof.get("revision") == current.revision
                and proof.get("all_android_mutators_absent") is True
                and proof.get("all_linux_subjobs_absent") is True
                and type(observed) is int
                and 0 <= current.observed_boottime_ms - observed <= 1000
            )
        except (OSError, ValueError, KeyError,
                PublisherBoundaryError, AuthorityUnavailable):
            native_absence_supported = False
    if not native_absence_supported:
        reasons.append("NATIVE_MUTATOR_ABSENCE_UNPROVEN")

    fence = observe_admission_fence_readonly(
        expected_release_id=candidate_dir.name)
    admissions_held = (
        fence.get("admissions_stopped_positive") is True
    )
    if not admissions_held:
        reasons.append("ADMISSION_FENCE_NOT_POSITIVELY_HELD")

    offline_accepted = False
    if _OFFLINE_GATE_SOURCE_ACCEPTED:
        try:
            proof = _strict_json(OFFLINE_GATES_PATH)
            offline_accepted = (
                proof.get("offline_gate_version") == 1
                and proof.get("candidate_release_id") == candidate_dir.name
                and proof.get("acceptance_status") == "PASSED"
                and proof.get("artifact_signatures_verified") is True
                and proof.get("fault_injection_complete") is True
                and proof.get("ui_regressions_complete") is True
                and proof.get("protocol_compatibility_complete") is True
            )
        except (OSError, ValueError, KeyError,
                PublisherBoundaryError):
            offline_accepted = False
    if not offline_accepted:
        reasons.append("OFFLINE_ACCEPTANCE_EVIDENCE_UNAVAILABLE")

    proof = QuiescenceProof(
        admissions_stopped=admissions_held,
        live_ui_mutators_absent=native_absence_supported,
        android_ui_claim_resolved=resolved_claim,
        unsafe_effects_resolved=no_unsafe_jobs,
        candidate_owner_mode_verified=candidate_verified,
        candidate_signature_verified=candidate_verified,
        offline_gates_passed=offline_accepted,
    )
    return {
        "status": ("READ_ONLY_QUIESCENCE_VERIFIED"
                   if proof.complete() and no_live_capability_jobs
                      and no_staging_jobs
                   else "BLOCKED"),
        "reason_codes": sorted(set(reasons)),
        "candidate_signature_verified": candidate_verified,
        "android_ui_claim_resolved": resolved_claim,
        "active_jobs_quiescent": no_live_capability_jobs,
        "staging_jobs_reconciled": no_staging_jobs,
        "unsafe_capability_outcomes_resolved": no_unsafe_jobs,
        "native_ui_mutators_absent_proven": native_absence_supported,
        "admission_fence_proven": admissions_held,
        "offline_gates_accepted": offline_accepted,
        "quiescence_complete": (
            proof.complete() and no_live_capability_jobs
            and no_staging_jobs
        ),
        "switch_authorized": False,
        "mutation_attempts": 0,
    }
