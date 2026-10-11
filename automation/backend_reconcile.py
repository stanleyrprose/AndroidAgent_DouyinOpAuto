"""Rev3.7 exact-backend outcome classification and explicit reconciliation.

Backend durable fact owns execution truth, never capability state.json.
Recovery may inspect the SAME deterministic backend ID but never allocate
a retry execution or automatically repeat an irreversible TikTok effect.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class BackendCondition(str, Enum):
    NEVER_CREATED = "NEVER_CREATED"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    ZOMBIE = "ZOMBIE"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"


@dataclass(frozen=True)
class BackendObservation:
    backend_job_id: str
    request_sha256: str
    condition: BackendCondition
    identity_verified: bool
    durable_terminal_verified: bool
    never_created_positive_proof: bool
    effect_boundary_crossed: bool
    effect_outcome_verified: bool
    observed_boot_id: str | None = None

    def safe_view(self) -> dict[str, Any]:
        return {
            "backend_job_id": self.backend_job_id,
            "condition": self.condition.value,
            "identity_verified": self.identity_verified,
            "durable_terminal_verified": self.durable_terminal_verified,
            "positive_never_created": self.never_created_positive_proof,
            "effect_outcome_verified": self.effect_outcome_verified,
        }


def classify_exact_backend(
    *,
    expected_backend_id: str,
    expected_request_sha256: str,
    facts: Mapping[str, Any],
) -> BackendObservation:
    """No list/search fallback. Facts must come from exact backend lookup."""
    if not isinstance(facts, Mapping) or not facts.get("lookup_complete"):
        return BackendObservation(
            expected_backend_id, expected_request_sha256,
            BackendCondition.UNKNOWN, False, False, False, False, False)
    identity_ok = (
        facts.get("backend_job_id") == expected_backend_id
        and facts.get("request_sha256") == expected_request_sha256
    )
    if facts.get("exists") is True and not identity_ok:
        condition = BackendCondition.IDENTITY_MISMATCH
    elif facts.get("exists") is False:
        # A claimed absence is only meaningful for the EXACT original
        # Backend ID and immutable request hash. Never let an adapter's
        # positive never-created bit bless an unknown/mismatched identity.
        condition = (
            BackendCondition.NEVER_CREATED
            if identity_ok
               and facts.get("durable_never_created_proof") is True
            else (BackendCondition.IDENTITY_MISMATCH
                  if not identity_ok else BackendCondition.UNKNOWN)
        )
    elif facts.get("exists") is not True:
        condition = BackendCondition.UNKNOWN
    else:
        claimed = facts.get("state")
        condition = (
            BackendCondition(claimed)
            if claimed in {c.value for c in BackendCondition}
            else BackendCondition.UNKNOWN
        )
    terminal = condition in {
        BackendCondition.SUCCEEDED,
        BackendCondition.FAILED,
        BackendCondition.CANCELLED,
    } and facts.get("durable_terminal_verified") is True
    # A positively proven NEVER_CREATED result still has a VERIFIED exact
    # Backend ID and request identity. Deliberately clearing identity_ok
    # here made downstream recovery contradict the witness it had just
    # checked, and could turn safe pre-submit inspection into UNKNOWN.
    return BackendObservation(
        backend_job_id=expected_backend_id,
        request_sha256=expected_request_sha256,
        condition=condition,
        identity_verified=identity_ok,
        durable_terminal_verified=terminal,
        never_created_positive_proof=(
            condition == BackendCondition.NEVER_CREATED
            and facts.get("durable_never_created_proof") is True
        ),
        effect_boundary_crossed=(
            facts.get("effect_boundary_crossed") is True
        ),
        effect_outcome_verified=(
            facts.get("effect_outcome_verified") is True
        ),
        observed_boot_id=(
            facts.get("observed_boot_id")
            if isinstance(facts.get("observed_boot_id"), str)
            else None
        ),
    )


def determine_capability_recovery(
    observation: BackendObservation, *,
    capability_phase: str,
    unknown_effect: bool,
    current_resource_ownership_uncertain: bool,
) -> dict[str, Any]:
    """Read-only classification, no transitions or implicit retries."""
    if observation.condition == BackendCondition.IDENTITY_MISMATCH:
        reason, phase = "JOB_CONTRACT_VIOLATION", "RECONCILE_REQUIRED"
    elif current_resource_ownership_uncertain:
        reason, phase = "RESOURCE_RECONCILE_REQUIRED", "RECONCILE_REQUIRED"
    elif unknown_effect or observation.effect_boundary_crossed and (
        not observation.effect_outcome_verified
    ):
        reason, phase = "EFFECT_RECONCILE_REQUIRED", "RECONCILE_REQUIRED"
    elif observation.condition in {
        BackendCondition.UNKNOWN,
        BackendCondition.STOPPED,
        BackendCondition.ZOMBIE,
    }:
        reason, phase = (
            "BACKEND_LIVENESS_UNRESOLVED", "RECONCILE_REQUIRED"
        )
    elif observation.condition == BackendCondition.NEVER_CREATED:
        if capability_phase in {
            "ADMITTED", "BACKEND_BOUND", "WAITING_RESOURCE",
            "BLOCKED_CLOCK_SUSPECT",
        } and observation.never_created_positive_proof:
            reason, phase = "PRE_SUBMIT_CONTINUATION_CANDIDATE", capability_phase
        else:
            reason, phase = "BACKEND_EXISTENCE_UNCERTAIN", "RECONCILE_REQUIRED"
    elif observation.condition == BackendCondition.RUNNING:
        reason, phase = "EXACT_BACKEND_RUNNING", "BACKEND_RUNNING"
    elif observation.durable_terminal_verified:
        if observation.condition == BackendCondition.SUCCEEDED and (
            not observation.effect_boundary_crossed
            or observation.effect_outcome_verified
        ):
            reason, phase = "BACKEND_TERMINAL_VERIFIED", "SUCCEEDED"
        elif observation.condition in {
            BackendCondition.FAILED, BackendCondition.CANCELLED,
        } and not observation.effect_boundary_crossed:
            reason, phase = "BACKEND_TERMINAL_VERIFIED", (
                observation.condition.value
            )
        else:
            reason, phase = "TERMINAL_EFFECT_UNCERTAIN", "RECONCILE_REQUIRED"
    else:
        reason, phase = "BACKEND_TERMINAL_PROOF_UNAVAILABLE", "RECONCILE_REQUIRED"
    return {
        "status": "READ_ONLY_RECOVERY_CLASSIFIED",
        "proposed_phase": phase,
        "reason_code": reason,
        "requires_explicit_reconcile": phase == "RECONCILE_REQUIRED",
        "external_effect_retry_allowed": False,
        "backend_reallocated": False,
        "backend_submitted": False,
        "resource_claim_mutated": False,
        "capability_state_mutated": False,
    }
