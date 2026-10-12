"""Rev3.7 exact-approval / irreversible effect boundary candidate.

A capability's unsafe effect MUST NOT start unless its unique immutable
effect-boundary record was durably crossed before Publisher COMMITTING.
This library persists proof only; it contains no publisher dispatch,
network action, button click, or production activation path.

Approval is bound to exact request/policy/artifact/visibility, consumed once,
and may not be repurposed for a changed content identity. Once boundary has
been crossed, uncertain effect is RECONCILE_REQUIRED, never ordinary retry.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from automation.capability_job_store import (
    AdmittedJob, CapabilityStoreError, _locked,
    _atomic_new, _atomic_replace, _append, _read_json, _sha, _need, _utc,
)

# Separate from the Gateway/Publisher release switches. Acceptance must
# explicitly review the true approval and Android action-boundary evidence.
_EFFECT_CROSSING_ACCEPTED = False

_BOUNDARY_PHASES = frozenset({
    "EFFECT_BOUNDARY_CROSSED", "EFFECT_OUTCOME_VERIFIED",
    "RECONCILE_REQUIRED",
})


@dataclass(frozen=True)
class EffectIdentity:
    capability_job_id: str
    backend_job_id: str
    request_sha256: str
    effective_policy_sha256: str
    content_sha256: str
    visibility: str
    approval_id: str

    def normalized(self) -> dict[str, Any]:
        return {
            "capability_job_id": self.capability_job_id,
            "backend_job_id": self.backend_job_id,
            "request_sha256": self.request_sha256,
            "effective_policy_sha256": self.effective_policy_sha256,
            "content_sha256": self.content_sha256,
            "visibility": self.visibility,
            "approval_id": self.approval_id,
        }


def _effect_from_trusted_evidence(
    job: AdmittedJob, *,
    backend: Mapping[str, Any],
    approval: Mapping[str, Any],
    effect: Mapping[str, Any],
) -> EffectIdentity:
    """Only trusted adapter / identity+policy SOT may provide these facts."""
    _need(
        backend.get("capability_job_id") == job.job_id
        and backend.get("request_sha256") == job.request_sha256
        and backend.get("backend_type") == "publisher"
        and backend.get("backend_binding_version") == 1
        and backend.get("backend_job_id")
            == f"{job.job_id}--publisher-01",
        "BACKEND_IDENTITY_MISMATCH",
    )
    identity = _read_json(job.path / "identity.json")
    request = _read_json(job.path / "request.json")
    _need(identity.get("capability_job_id") == job.job_id
          and identity.get("request_sha256") == job.request_sha256
          and _sha(request) == job.request_sha256,
          "REQUEST_MUTATED")
    payload = request.get("payload")
    _need(isinstance(payload, dict)
          and request.get("capability") == "tiktok.publish"
          and payload.get("publish_mode") == "COMMIT"
          and payload.get("visibility") == "PUBLIC"
          and payload.get("content_sha256") == effect.get("content_sha256")
          and payload.get("content_sha256") == approval.get("content_sha256")
          and payload.get("caption_sha256") == approval.get("caption_sha256"),
          "EFFECT_REQUEST_APPROVAL_DRIFT")
    policy = _read_json(job.path / "effective_policy.json")
    _need(_sha(policy) == job.effective_policy_sha256
          and identity.get("effective_policy_sha256")
              == job.effective_policy_sha256, "POLICY_MUTATED")
    _need(approval.get("approval_version") == 1
          and approval.get("approved") is True
          and approval.get("single_use") is True
          and approval.get("capability") == "tiktok.publish"
          and approval.get("capability_version") == "1.0"
          and approval.get("job_id") == job.job_id
          and approval.get("approval_id")
          and approval.get("request_sha256") == job.request_sha256
          and approval.get("effective_policy_sha256")
              == job.effective_policy_sha256,
          "APPROVAL_MISMATCH")
    for field in ("content_sha256", "visibility"):
        _need(isinstance(effect.get(field), str) and effect[field],
              "EFFECT_IDENTITY_UNAVAILABLE")
        _need(effect.get(field) == approval.get(field), "APPROVAL_MISMATCH")
    _need(effect.get("visibility") == "PUBLIC",
          "VISIBILITY_CONTRACT_INVALID")
    _need(effect.get("approval_id") == approval.get("approval_id"),
          "APPROVAL_MISMATCH")
    # Re-read a single-use approval under transition.lock IMMEDIATELY before
    # crossing the effect boundary; no stale preflight validity shortcut.
    try:
        now = datetime.now(timezone.utc)
        approved_at = datetime.fromisoformat(
            approval["approved_at"].replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(
            approval["expires_at"].replace("Z", "+00:00"))
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise CapabilityStoreError("APPROVAL_CLOCK_INVALID") from exc
    _need(approved_at.tzinfo is not None and expires_at.tzinfo is not None
          and approved_at.astimezone(timezone.utc) <= now
          < expires_at.astimezone(timezone.utc),
          "APPROVAL_EXPIRED")
    return EffectIdentity(
        capability_job_id=job.job_id,
        backend_job_id=backend["backend_job_id"],
        request_sha256=job.request_sha256,
        effective_policy_sha256=job.effective_policy_sha256,
        content_sha256=effect["content_sha256"],
        visibility=effect["visibility"],
        approval_id=approval["approval_id"],
    )


def record_approval(
    job: AdmittedJob, *,
    trusted_approval: Mapping[str, Any],
    trusted_clock_health: str,
) -> dict[str, Any]:
    """Write-once approval. Input MUST be an already verified trusted fact.

    A request-side 'approved': true is not a trusted fact. Production has no
    call path into this function until separate identity/policy verification.
    """
    _need(isinstance(trusted_approval, Mapping), "APPROVAL_UNAVAILABLE")
    _need(trusted_approval.get("approval_version") == 1
          and trusted_approval.get("approved") is True
          and trusted_approval.get("request_sha256") == job.request_sha256
          and trusted_approval.get("effective_policy_sha256")
          == job.effective_policy_sha256
          and isinstance(trusted_approval.get("content_sha256"), str)
          and isinstance(trusted_approval.get("approval_id"), str)
          and isinstance(trusted_approval.get("approval_nonce"), str)
          and bool(trusted_approval.get("approval_nonce"))
          and trusted_approval.get("nonce") == trusted_approval.get("approval_nonce")
          and trusted_approval.get("single_use") is True
          and trusted_approval.get("capability") == "tiktok.publish"
          and trusted_approval.get("capability_version") == "1.0"
          and trusted_approval.get("job_id") == job.job_id
          and isinstance(trusted_approval.get("approved_by"), dict)
          and bool(trusted_approval["approved_by"].get("principal_type"))
          and bool(trusted_approval["approved_by"].get("principal_id"))
          and isinstance(trusted_approval.get("expires_at"), str)
          and isinstance(trusted_approval.get("approved_at"), str)
          and trusted_approval.get("visibility") in {"PUBLIC", "PRIVATE", "FRIENDS"},
          "APPROVAL_MISMATCH")
    # Do not trust the caller's mere statement that the approval is
    # authentic. Re-open the root-owned exact one-URL ingress evidence and
    # compare every durable identity field against it before writing.
    from automation.trusted_ingress_approval import (
        IngressAuthorizationUnavailable,
        inspect_trusted_one_url_authorization,
    )
    try:
        expected = inspect_trusted_one_url_authorization(
            job, current_clock_health=trusted_clock_health)
    except IngressAuthorizationUnavailable as exc:
        raise CapabilityStoreError(exc.code) from exc
    pinned_fields = (
        "approval_version", "approval_id", "job_id", "capability",
        "capability_version", "request_sha256",
        "effective_policy_sha256", "content_sha256", "caption_sha256",
        "visibility", "approved_by", "approved_at", "expires_at",
        "single_use", "nonce", "approval_nonce",
    )
    _need(all(trusted_approval.get(field) == expected.get(field)
              for field in pinned_fields),
          "TRUSTED_INGRESS_APPROVAL_MISMATCH")
    entry = {field: expected[field] for field in pinned_fields}
    entry.update(
        approved=True,
        approval_state="RECORDED",
        recorded_at=_utc(),
    )
    with _locked(job.path / "transition.lock"):
        boundary_path = job.path / "effect-boundary.json"
        _need(not boundary_path.exists() and not boundary_path.is_symlink(),
              "EFFECT_ALREADY_ATTEMPTED")
        path = job.path / "approval.json"
        if path.exists() or path.is_symlink():
            # A repeated trusted ingress must not silently reuse a changed
            # principal, caption, nonce, expiry or approval provenance.
            # Compare the entire canonical record rather than five fields.
            original = _read_json(path)
            _need(isinstance(original.get("recorded_at"), str)
                  and _sha({k: v for k, v in original.items()
                            if k != "recorded_at"})
                      == _sha({k: v for k, v in entry.items()
                               if k != "recorded_at"}),
                  "APPROVAL_IMMUTABLE")
            return original
        _atomic_new(path, entry)
        return entry


def cross_effect_boundary(
    job: AdmittedJob, *,
    trusted_effect: Mapping[str, Any],
    approval_authority_verified: bool,
    state_jit_verified: bool,
    current_resource_guard: Mapping[str, Any],
) -> dict[str, Any]:
    """Prepare exact one effect boundary; NEVER dispatch the effect itself.

    Production caller MUST acquire durable resource guard and perform fresh
    Android/SOT/approval checks independently. A plain external invocation
    of this unconnected library does not imply an execution permission.
    """
    _need(_EFFECT_CROSSING_ACCEPTED,
          "EFFECT_BOUNDARY_RELEASE_GATE_CLOSED")
    _need(approval_authority_verified is True
          and state_jit_verified is True,
          "EFFECT_PRECONDITION_UNVERIFIED")
    _need(isinstance(current_resource_guard, Mapping)
          and current_resource_guard.get("resource") == "android_ui"
          and all(isinstance(current_resource_guard.get(k), str)
                  and current_resource_guard[k]
                  for k in ("claim_id", "owner_id")),
          "RESOURCE_GUARD_INVALID")
    with _locked(job.path / "transition.lock"):
        # A caller's 'resource_guard' or JIT boolean is never authoritative
        # on its own. Read the currently DURABLE canonical claim and the
        # root-owned semantic epoch/revision inside this same transition.
        from automation import resource_arbiter
        from automation.authoritative_state_reader import (
            AuthorityUnavailable, observe_authoritative_state,
        )
        from automation.capability_catalog import load_catalog
        try:
            claim = resource_arbiter.assert_guard(
                dict(current_resource_guard))
            current_sot = observe_authoritative_state()
        except resource_arbiter.ResourceError as exc:
            raise CapabilityStoreError("STALE_RESOURCE_OWNERSHIP") from exc
        except AuthorityUnavailable as exc:
            raise CapabilityStoreError(
                "STATE_INTEGRITY_UNAVAILABLE") from exc
        _need(claim.get("owner_kind") == "CAPABILITY"
              and claim.get("capability_job_id") == job.job_id
              and claim.get("request_sha256") == job.request_sha256,
              "RESOURCE_CLAIM_IDENTITY_MISMATCH")
        _need(isinstance(trusted_effect, Mapping)
              and trusted_effect.get("observed_boot_id")
                  == current_sot.boot_id
              and trusted_effect.get("state_epoch")
                  == current_sot.state_epoch
              and trusted_effect.get("revision")
                  == current_sot.revision,
              "STATE_SOT_JIT_MISMATCH")
        catalog = load_catalog()
        tiktok_contract = catalog["tiktok.publish"]
        app_contract = tiktok_contract["app_ui_contract"]
        _need(app_contract.get("acceptance_status") == "ACCEPTED"
              and tiktok_contract.get("enabled") is True
              and trusted_effect.get("app_ui_contract_version")
                  == app_contract.get("ui_contract_version")
              and trusted_effect.get("app_version_code")
                  in app_contract.get("accepted_version_codes", [])
              and trusted_effect.get("app_signing_cert_sha256")
                  == app_contract.get("signing_cert_sha256"),
              "APP_UI_CONTRACT_NOT_ACCEPTED")
        state = _read_json(job.path / "state.json")
        _need(not state.get("terminal"), "JOB_TERMINAL")
        _need(state.get("backend_submitted") is True,
              "BACKEND_NOT_SUBMITTED")
        # Durable effect consumption is permitted only after the EXACT
        # original Backend ACK has been fsynced. The job state flag alone
        # does not establish submit identity in a crash/replay scenario.
        execution = _read_json(job.path / "backend-execution.json")
        _need(execution.get("backend_execution_version") == 1
              and execution.get("capability_job_id") == job.job_id
              and execution.get("request_sha256") == job.request_sha256
              and execution.get("phase") == "SUBMITTED_ACKNOWLEDGED"
              and execution.get("submission_possible") is True
              and execution.get("attempt_serial") == 1,
              "BACKEND_DURABLE_SUBMISSION_UNVERIFIED")
        _need(not state.get("mutation_uncertain")
              and not state.get("effect_uncertain"),
              "RECONCILE_REQUIRED")
        backend = _read_json(job.path / "backend.json")
        _need(execution.get("backend_job_id")
                  == backend.get("backend_job_id")
              and backend.get("capability_job_id") == job.job_id
              and backend.get("request_sha256") == job.request_sha256,
              "BACKEND_SUBMISSION_IDENTITY_MISMATCH")
        _need(claim.get("backend_job_id") == backend.get("backend_job_id"),
              "RESOURCE_BACKEND_IDENTITY_MISMATCH")
        approval = _read_json(job.path / "approval.json")
        effect = _effect_from_trusted_evidence(
            job, backend=backend, approval=approval,
            effect=trusted_effect,
        )
        bound = effect.normalized()
        boundary_path = job.path / "effect-boundary.json"
        _need(not boundary_path.is_symlink(),
              "EFFECT_BOUNDARY_PATH_UNTRUSTED")
        if boundary_path.exists():
            previous = _read_json(boundary_path)
            _need(all(previous.get(k) == v for k, v in bound.items()),
                  "EFFECT_IDENTITY_CONFLICT")
            # Even same identity cannot issue another external effect
            # attempt. Reconcile exact existing effect instead.
            raise CapabilityStoreError("EFFECT_ALREADY_ATTEMPTED")
        cancel_path = job.path / "cancel.json"
        _need(not cancel_path.is_symlink(),
              "CANCEL_INTENT_PATH_UNTRUSTED")
        _need(not cancel_path.exists(),
              "CANCEL_BEFORE_EFFECT_BOUNDARY")
        _need(type(trusted_effect.get("revision")) is int
              and trusted_effect["revision"] >= 0
              and trusted_effect.get("fingerprint_version") == "semantic-v1"
              and trusted_effect.get("fingerprint_profile_id")
                  == "tiktok.publish-control.v1"
              and isinstance(trusted_effect.get("state_hash"), str)
              and len(trusted_effect["state_hash"]) == 64,
              "STATE_FINGERPRINT_UNAVAILABLE")
        boundary = {
            "effect_boundary_version": 1,
            "phase": "EFFECT_BOUNDARY_CROSSED",
            "capability": "tiktok.publish",
            "boundary": "before_final_publish",
            "crossed_at": _utc(),
            "crossed_boottime_ms": current_sot.observed_boottime_ms,
            "observed_boot_id": current_sot.boot_id,
            "state_epoch": current_sot.state_epoch,
            "approval_sha256": _sha(approval),
            "approval_nonce": approval["approval_nonce"],
            "revision": trusted_effect["revision"],
            "fingerprint_version": "semantic-v1",
            "fingerprint_profile_id": "tiktok.publish-control.v1",
            "state_hash": trusted_effect["state_hash"],
            "created_at": _utc(),
            **bound,
            "resource_guard": dict(current_resource_guard),
            "external_effect_attempts_allowed": 1,
            "external_effect_attempts_observed": 0,
            "effect_outcome": "UNKNOWN",
            "next_action": "RECONCILE_IF_UNCERTAIN",
        }
        # The one durable boundary is itself approval consumption; do not
        # persist a second mutable approval-used truth. Even a crash before
        # lifecycle update cannot authorize another external attempt.
        _atomic_new(boundary_path, boundary)
        _need(type(state.get("state_revision")) is int
              and state["state_revision"] >= 0,
              "STATE_STORE_CORRUPT")
        running_unsafe = dict(state)
        running_unsafe.update(
            lifecycle_state="RUNNING_UNSAFE",
            phase="RUNNING_UNSAFE",
            state_revision=state["state_revision"] + 1,
            phase_reason_code="EFFECT_BOUNDARY_CROSSED",
            updated_at=_utc(),
            effect_uncertain=True,
            terminal=False,
        )
        _atomic_replace(job.path / "state.json", running_unsafe)
        _append(job.path / "journal.jsonl", {
            "event": "EFFECT_BOUNDARY_CROSSED",
            "timestamp": running_unsafe["updated_at"],
            "approval_sha256": boundary["approval_sha256"],
            "backend_job_id": effect.backend_job_id,
        })
        return {
            "effect_boundary_version": 1,
            "phase": "EFFECT_BOUNDARY_CROSSED",
            "capability_job_id": job.job_id,
            "backend_job_id": effect.backend_job_id,
            "production_dispatch_authorized": False,
            "effect_attempts_performed_by_this_module": 0,
        }


def read_effect_boundary(job: AdmittedJob) -> dict[str, Any]:
    """Pure status; absence does not prove the external backend never ran."""
    path = job.path / "effect-boundary.json"
    _need(not path.is_symlink(), "EFFECT_BOUNDARY_PATH_UNTRUSTED")
    if not path.exists():
        return {
            "phase": "EFFECT_BOUNDARY_NOT_RECORDED",
            "backend_never_created_proven": False,
            "safe_to_retry_external_effect": False,
        }
    boundary = _read_json(path)
    _need(boundary.get("phase") in _BOUNDARY_PHASES,
          "EFFECT_BOUNDARY_CORRUPT")
    return {
        "phase": boundary["phase"],
        "backend_job_id": boundary.get("backend_job_id"),
        "effect_outcome": boundary.get("effect_outcome", "UNKNOWN"),
        "safe_to_retry_external_effect": False,
        "requires_reconcile": boundary["phase"]
            != "EFFECT_OUTCOME_VERIFIED",
    }


def classify_verification(
    *,
    boundary: Mapping[str, Any],
    verifier_completed: bool,
    verified_success: bool | None,
) -> dict[str, Any]:
    """Verifier failure after the effect is UNCERTAIN, never FAILED/retry."""
    _need(boundary.get("phase") == "EFFECT_BOUNDARY_CROSSED",
          "EFFECT_BOUNDARY_UNAVAILABLE")
    if verifier_completed is not True or verified_success is None:
        return {
            "outcome": "RECONCILE_REQUIRED",
            "terminal": False,
            "repeat_effect_allowed": False,
            "reason_code": "VERIFIER_OR_EFFECT_UNCERTAIN",
        }
    if verified_success is True:
        return {
            "outcome": "SUCCEEDED",
            "terminal": True,
            "repeat_effect_allowed": False,
            "reason_code": "EXACT_EFFECT_VERIFIED",
        }
    return {
        "outcome": "RECONCILE_REQUIRED",
        "terminal": False,
        "repeat_effect_allowed": False,
        "reason_code": "EFFECT_NOT_POSITIVELY_VERIFIED",
    }
