"""Rev3.7 exact android_ui claim recovery and emergency reset boundary.

Resource-only reconciliation supports owner_kind=LEGACY without inventing
a Capability Job. It never finalizes BUSINESS outcomes, creates another
backend, or retries effects. Any release requires positive stop/quiescence
proof followed by a canonical locked exact-claim re-read.

All destructive/admin operations stay CLOSED until the complete PRD is
implemented and separately accepted. This file is a dormant source draft.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import fcntl
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from automation import resource_arbiter, state_integrity
from automation.authoritative_state_reader import (
    observe_authoritative_state, AuthorityUnavailable,
)

_RESOURCE_RECOVERY_ACCEPTED = False
_EMERGENCY_ADMIN_ACCEPTED = False
_ADMIN_AUTH_ROOT = Path("/opt/y700/runtime/trusted-admin-reset")


class ResourceRecoveryRefused(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ExactStopProof:
    claim_id: str
    owner_id: str
    owner_kind: str
    backend_job_id: str
    backend_not_running_positive: bool
    owner_process_not_running_positive: bool
    subordinate_ui_mutators_absent_positive: bool
    unsafe_effect_unresolved: bool
    boot_identity_verified: bool

    def safe_to_release(self) -> bool:
        # BUSINESS outcome may remain RECONCILE_REQUIRED after UI is truly
        # quiescent. Never use publication uncertainty as a resource lock.
        return (
            self.backend_not_running_positive is True
            and self.owner_process_not_running_positive is True
            and self.subordinate_ui_mutators_absent_positive is True
            and self.boot_identity_verified is True
        )


def _exact_claim(claim_id: str) -> dict[str, Any]:
    if not isinstance(claim_id, str) or not claim_id.startswith("ui-claim-"):
        raise ResourceRecoveryRefused("RESOURCE_CLAIM_ID_INVALID")
    try:
        claim = resource_arbiter.read_claim()
    except resource_arbiter.ResourceError as exc:
        raise ResourceRecoveryRefused("RESOURCE_CLAIM_STATE_UNAVAILABLE") from exc
    if claim is None or claim.get("claim_id") != claim_id:
        raise ResourceRecoveryRefused("EXACT_RESOURCE_CLAIM_NOT_FOUND")
    if claim.get("owner_kind") not in {"LEGACY", "CAPABILITY", "ADMIN"}:
        raise ResourceRecoveryRefused("RESOURCE_CLAIM_OWNER_UNKNOWN")
    for key in ("owner_id", "backend_job_id"):
        if not isinstance(claim.get(key), str) or not claim[key]:
            raise ResourceRecoveryRefused("RESOURCE_CLAIM_IDENTITY_INVALID")
    return claim


def preview_reconcile_resource(
    *, claim_id: str,
    proof: ExactStopProof | None,
) -> dict[str, Any]:
    """Read-only planning, never release a claim on the age of its PID."""
    try:
        claim = _exact_claim(claim_id)
    except ResourceRecoveryRefused as exc:
        return {
            "status": "BLOCKED",
            "reason_code": exc.code,
            "release_performed": False,
            "capability_outcome_mutated": False,
        }
    same_identity = (
        isinstance(proof, ExactStopProof)
        and proof.claim_id == claim["claim_id"]
        and proof.owner_id == claim["owner_id"]
        and proof.owner_kind == claim["owner_kind"]
        and proof.backend_job_id == claim["backend_job_id"]
    )
    eligible = same_identity and proof.safe_to_release()
    return {
        "status": "READ_ONLY_RESOURCE_RECONCILE",
        "claim_id": claim_id,
        "owner_kind": claim["owner_kind"],
        "capability_job_id": claim.get("capability_job_id"),
        "reason_code": "POSITIVE_STOP_PROOF_OBSERVED"
                       if eligible else "RESOURCE_QUIESCENCE_UNPROVEN",
        "eligible_for_explicit_maintenance": bool(eligible),
        "release_performed": False,
        "effect_retried": False,
        "capability_outcome_mutated": False,
    }


def observe_trusted_exact_stop_proof(claim_id: str) -> ExactStopProof:
    """Read only kernel+Backend+native source facts; never trust a flag."""
    from automation.resource_stop_observer import (
        inspect_exact_stop_readonly,
    )
    current = _exact_claim(claim_id)
    source = inspect_exact_stop_readonly(claim_id)
    if source.get("status") != "READ_ONLY_EXACT_STOP_INSPECTION":
        raise ResourceRecoveryRefused(
            source.get("reason_code", "RESOURCE_STOP_PROOF_UNAVAILABLE"))
    if (source.get("claim_id") != current["claim_id"]
            or source.get("backend_job_id") != current["backend_job_id"]
            or source.get("owner_kind") != current["owner_kind"]):
        raise ResourceRecoveryRefused("RESOURCE_STOP_IDENTITY_MISMATCH")
    # Deliberately distinct axes: BUSINESS effect may be unresolved and
    # still permit resource-only release AFTER total mutator quiescence.
    return ExactStopProof(
        claim_id=claim_id,
        owner_id=current["owner_id"],
        owner_kind=current["owner_kind"],
        backend_job_id=current["backend_job_id"],
        backend_not_running_positive=(
            source.get("backend_not_running_positive") is True),
        owner_process_not_running_positive=(
            source.get("owner_process_not_running_positive") is True),
        subordinate_ui_mutators_absent_positive=(
            source.get("subordinate_ui_mutators_absent_positive") is True),
        unsafe_effect_unresolved=True,
        boot_identity_verified=(
            source.get("boot_identity_verified") is True),
    )


def reconcile_resource_exact(
    *, claim_id: str, audit_reason: str = "NORMAL_RECONCILE_RESOURCE",
) -> dict[str, Any]:
    """Normal deterministic cleanup; no ADMIN authentication required.

    The source gate and exact positive proof remain mandatory; this
    operation never terminalizes a Capability or retries Publisher.
    """
    return release_exact_after_acceptance(
        claim_id=claim_id, audit_reason=audit_reason)


def release_exact_after_acceptance(
    *, claim_id: str,
    audit_reason: str,
) -> dict[str, Any]:
    """One-shot maintenance only; NEVER silently reacquire or regenerate."""
    if not _RESOURCE_RECOVERY_ACCEPTED:
        raise ResourceRecoveryRefused("RESOURCE_RECOVERY_RELEASE_GATE_CLOSED")
    if not isinstance(audit_reason, str) or not audit_reason.strip():
        raise ResourceRecoveryRefused("RESOURCE_RECOVERY_REASON_REQUIRED")
    lock = resource_arbiter.LOCK_PATH
    fd = os.open(lock, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        claim = _exact_claim(claim_id)
        # Never accept caller-provided positive-stop booleans. Reobserve
        # real kernel/Backend/native facts WHILE holding canonical flock.
        proof = observe_trusted_exact_stop_proof(claim_id)
        diagnostic = preview_reconcile_resource(
            claim_id=claim_id, proof=proof)
        if not diagnostic.get("eligible_for_explicit_maintenance"):
            raise ResourceRecoveryRefused("RESOURCE_QUIESCENCE_UNPROVEN")
        # Maintain one resource owner: claim identity cannot change under
        # the canonical flock between preflight and durable release.
        if _exact_claim(claim_id) != claim:
            raise ResourceRecoveryRefused("RESOURCE_CLAIM_CHANGED")
        resource_arbiter._append_audit({
            "phase": "RESOURCE_RECOVERY_RELEASE_PREPARED",
            "timestamp": resource_arbiter._now_iso(),
            "claim_id": claim_id,
            "owner_id": claim["owner_id"],
            "owner_kind": claim["owner_kind"],
            "reason": audit_reason[:160],
            "positive_stop_proof": True,
        })
        resource_arbiter.CLAIM_PATH.unlink()
        resource_arbiter._fsync_dir(resource_arbiter.CLAIM_PATH.parent)
        resource_arbiter._append_audit({
            "phase": "RESOURCE_RECOVERY_COMPLETED",
            "timestamp": resource_arbiter._now_iso(),
            "claim_id": claim_id,
            "owner_kind": claim["owner_kind"],
            "reason": audit_reason[:160],
        })
        return {
            "status": "EXACT_CLAIM_RELEASED",
            "claim_id": claim_id,
            "business_outcome_mutated": False,
            "new_backend_created": False,
        }
    except BlockingIOError as exc:
        raise ResourceRecoveryRefused("RESOURCE_STILL_OWNED") from exc
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _verify_admin_reset_authority(
    claim: Mapping[str, Any], reason: str,
) -> str:
    """Bounded root-owned one-shot operator evidence, not CLI admin=true."""
    from automation.publisher_boundary_guard import _strict_json
    from automation.trusted_ingress_approval import _utc
    from automation.authoritative_state_reader import observe_authoritative_state
    import stat
    if not isinstance(reason, str) or not 0 < len(reason) <= 160:
        raise ResourceRecoveryRefused("ADMIN_RESET_REASON_INVALID")
    try:
        directory = _ADMIN_AUTH_ROOT.lstat()
        if (not stat.S_ISDIR(directory.st_mode)
                or directory.st_uid != 0
                or stat.S_IMODE(directory.st_mode) != 0o700):
            raise ResourceRecoveryRefused("ADMIN_AUTH_DIRECTORY_UNTRUSTED")
        authority = _strict_json(
            _ADMIN_AUTH_ROOT / (claim["claim_id"] + ".json"))
        now = datetime.now(timezone.utc)
        issued = _utc(authority.get("authorized_at"))
        expires = _utc(authority.get("expires_at"))
        current = observe_authoritative_state()
    except Exception as exc:
        raise ResourceRecoveryRefused(
            "ADMIN_AUTHORITY_UNAVAILABLE") from exc
    if not (
        authority.get("admin_authorization_version") == 1
        and authority.get("source") == "Y700_TRUSTED_LOCAL_CONTROLLER"
        and authority.get("operation") == "FORCE_RESET_UI_RUNTIME"
        and authority.get("claim_id") == claim["claim_id"]
        and authority.get("owner_id") == claim["owner_id"]
        and authority.get("backend_job_id") == claim["backend_job_id"]
        and authority.get("claim_generation") == claim.get(
            "claim_generation")
        and authority.get("reason_sha256") == hashlib.sha256(
            reason.encode("utf-8")).hexdigest()
        and authority.get("boot_id") == current.boot_id
        and isinstance(authority.get("principal"), dict)
        and authority["principal"].get("role") == "ADMIN"
        and isinstance(authority["principal"].get("principal_id"), str)
        and len(authority["principal"]["principal_id"]) > 0
        and authority.get("single_use") is True
        and isinstance(authority.get("nonce"), str)
        and len(authority["nonce"]) >= 16
        and issued <= now < expires
        and (expires - issued).total_seconds() <= 600
    ):
        raise ResourceRecoveryRefused("ADMIN_AUTHORITY_MISMATCH")
    return authority["nonce"]


def _consume_admin_reset_authorization(
    claim: Mapping[str, Any], nonce: str, reason: str,
) -> None:
    """Durable one-shot nonce consumption BEFORE epoch/stop side effects."""
    import hashlib
    from automation.capability_job_store import _atomic_new, _root_dir, SUBMISSIONS
    root = SUBMISSIONS / "admin-reset-consumptions"
    _root_dir(root)
    key = hashlib.sha256(
        (str(claim["claim_id"]) + ":" + str(claim["owner_id"])
         + ":" + str(claim.get("claim_generation")) + ":" + nonce)
        .encode("utf-8")
    ).hexdigest()
    try:
        _atomic_new(root / (key + ".json"), {
            "admin_reset_consumption_version": 1,
            "claim_id": claim["claim_id"],
            "owner_id": claim["owner_id"],
            "backend_job_id": claim["backend_job_id"],
            "claim_generation": claim.get("claim_generation"),
            "reason_sha256": hashlib.sha256(
                reason.encode("utf-8")).hexdigest(),
            "nonce_sha256": hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
            "consumed_before_root_effect": True,
        })
    except (CapabilityStoreError, OSError) as exc:
        # A previous attempt might have crashed AFTER consuming the grant.
        # Never re-execute a stop/reset under that same authorization.
        raise ResourceRecoveryRefused(
            "ADMIN_RESET_GRANT_ALREADY_USED_OR_UNAVAILABLE") from exc


def emergency_force_reset_after_acceptance(
    *, claim_id: str, reason: str,
    stop_exact_backend: Callable[[Mapping[str, Any]], None],
    proof_after_stop: Callable[[], ExactStopProof],
) -> dict[str, Any]:
    """Admin escape hatch: bump epoch BEFORE any unsafe stop attempt.

    Still MUST positive-prove UI quiescence before releasing a claim.
    An unresolved unsafe effect remains RECONCILE_REQUIRED.
    """
    if not _EMERGENCY_ADMIN_ACCEPTED:
        raise ResourceRecoveryRefused("ADMIN_FORCE_RESET_GATE_CLOSED")
    claim = _exact_claim(claim_id)
    grant_nonce = _verify_admin_reset_authority(claim, reason)
    if not callable(stop_exact_backend) or not callable(proof_after_stop):
        raise ResourceRecoveryRefused("ADMIN_BACKEND_STOP_ADAPTER_UNAVAILABLE")
    # A missing/corrupt root-owned SOT is not permission to bootstrap
    # a fresh epoch or perform emergency Android mutations.
    try:
        observe_authoritative_state()
    except AuthorityUnavailable as exc:
        raise ResourceRecoveryRefused("STATE_INTEGRITY_UNAVAILABLE") from exc
    # A one-shot authorization is consumed BEFORE bumping epoch or
    # attempting the original backend stop. Never replay partial resets.
    _consume_admin_reset_authorization(claim, grant_nonce, reason)
    # Durable epoch bump first, before any backend stop or UI-reset effect.
    try:
        state_integrity.bump_epoch(
            "ADMIN_FORCE_RESET_REQUESTED:" + reason[:120])
    except state_integrity.StateIntegrityError as exc:
        raise ResourceRecoveryRefused("STATE_INTEGRITY_UNAVAILABLE") from exc
    resource_arbiter._append_audit({
        "phase": "ADMIN_FORCE_RESET_REQUESTED",
        "timestamp": resource_arbiter._now_iso(),
        "claim_id": claim_id,
        "owner_kind": claim["owner_kind"],
        "reason": reason[:160],
    })
    try:
        stop_exact_backend(claim)
    except Exception:
        # Do NOT release on a best-effort stop failure.
        pass
    proof = proof_after_stop()
    if not isinstance(proof, ExactStopProof) or not proof.safe_to_release():
        return {
            "status": "DEVICE_UI_RUNTIME_UNSAFE",
            "reason_code": "QUIESCENCE_NOT_POSITIVELY_PROVEN",
            "claim_retained": True,
            "recommended_action": "REBOOT_OR_REPAIR_RUNTIME",
        }
    # No re-entrant lock: this separate bounded recovery function acquires
    # the canonical flock and re-reads exact claim.
    return release_exact_after_acceptance(
        claim_id=claim_id,
        audit_reason="ADMIN_FORCE_RESET:" + reason[:120],
    )
