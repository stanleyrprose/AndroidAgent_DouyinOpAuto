"""Rev3.7 explicit same-backend reconciliation (foreground, no replay).

This is an implementation component; current capctl production reconcile
remains gated. It consumes trusted durable backend/resource/effect facts
and never creates a new backend or repeats a previously attempted effect.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from automation.backend_reconcile import (
    BackendObservation, BackendCondition, determine_capability_recovery,
)
from automation.capability_job_store import (
    AdmittedJob, CapabilityStore, CapabilityStoreError,
    _locked, _read_json, _need, _utc,
)
from automation.effect_boundary import read_effect_boundary


@dataclass(frozen=True)
class ReconcileProof:
    """From trusted exact backend/resource observers, NOT request JSON."""
    backend: BackendObservation
    resource_owner_safely_reconciled: bool
    effect_profile_positive_verified: bool
    effect_outcome_not_achieved_verified: bool
    backend_no_longer_mutating: bool


def inspect_reconcile_readonly(
    admitted: AdmittedJob, proof: ReconcileProof,
) -> dict[str, Any]:
    """Status from lower-level truths; cannot itself terminalize."""
    boundary = read_effect_boundary(admitted)
    if proof.backend.backend_job_id == "" or (
        proof.backend.request_sha256 != admitted.request_sha256
    ):
        return {
            "status": "RECONCILE_REQUIRED",
            "reason_code": "BACKEND_IDENTITY_MISMATCH",
            "external_retry_allowed": False,
            "execution_authorized": False,
        }
    has_boundary = boundary["phase"] != "EFFECT_BOUNDARY_NOT_RECORDED"
    state = _read_json(admitted.path / "state.json")
    classified = determine_capability_recovery(
        proof.backend,
        capability_phase=state.get("lifecycle_state", "UNKNOWN"),
        unknown_effect=has_boundary and not (
            proof.effect_profile_positive_verified
            or proof.effect_outcome_not_achieved_verified
        ),
        current_resource_ownership_uncertain=(
            proof.resource_owner_safely_reconciled is not True
        ),
    )
    reason = classified["reason_code"]
    if (has_boundary
            and proof.backend_no_longer_mutating is True
            and proof.resource_owner_safely_reconciled is True
            and proof.effect_profile_positive_verified is True):
        proposed = "VERIFIED"
        reason = "PROFILE_POSITIVE_EFFECT_VERIFIED"
    elif (has_boundary
          and proof.backend_no_longer_mutating is True
          and proof.resource_owner_safely_reconciled is True
          and proof.effect_outcome_not_achieved_verified is True):
        proposed = "OUTCOME_NOT_ACHIEVED"
        reason = "PROFILE_POSITIVE_OUTCOME_NOT_ACHIEVED"
    else:
        proposed = classified["proposed_phase"]
    return {
        "status": "RECONCILE_CLASSIFIED_READ_ONLY",
        "proposed_phase": proposed,
        "reason_code": reason,
        "backend_job_id": proof.backend.backend_job_id,
        "effect_boundary_crossed": has_boundary,
        "repeat_external_effect_allowed": False,
        "new_backend_allocated": False,
        "resource_release_performed": False,
        "capability_state_mutated": False,
    }


def reconcile_exact_final(
    admitted: AdmittedJob, proof: ReconcileProof, *,
    trusted_operator_reconcile_authorized: bool,
    store: CapabilityStore | None = None,
) -> dict[str, Any]:
    """Only terminalize a positively verified outcome. Never replay."""
    # This legacy API is retained for read-only compatibility only.
    # The flags in ReconcileProof and an operator-provided True boolean
    # can NEVER authorize a terminal state or external effect.
    _need(trusted_operator_reconcile_authorized is True,
          "RECONCILE_AUTHORIZATION_UNAVAILABLE")
    _need(proof.backend.backend_job_id != ""
          and proof.backend.request_sha256 == admitted.request_sha256,
          "BACKEND_IDENTITY_MISMATCH")
    proposal = inspect_reconcile_readonly(admitted, proof)
    from automation.capability_reconcile_runtime import (
        inspect_exact_outcome_readonly,
        reconcile_exact_after_acceptance,
    )
    durable = inspect_exact_outcome_readonly(
        admitted.job_id, store=store or CapabilityStore())
    if durable.get("status") not in {
        "POSITIVE_PROFILE_VERIFIER_OBSERVED",
        "POSITIVE_BACKEND_VERIFIER_OBSERVED",
        "TERMINAL_ARCHIVE_PENDING_READ_ONLY",
        "PUBLISHER_ARCHIVE_PENDING",
    }:
        return {
            "status": "RECONCILE_REQUIRED",
            "reason_code": durable.get(
                "reason_code", proposal.get("reason_code", "PROOF_UNAVAILABLE")),
            "capability_job_id": admitted.job_id,
            "terminal": False,
            "external_effect_retry_allowed": False,
            "backend_submitted": None,
        }
    # The canonical executor has its OWN frozen source-level release gate
    # and rechecks protected per-Backend receipts before any terminal
    # archive transition. The legacy proof object supplies NO authority.
    return reconcile_exact_after_acceptance(admitted.job_id)
