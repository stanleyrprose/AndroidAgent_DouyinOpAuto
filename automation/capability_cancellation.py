"""Rev3.7 durable cancel vs effect-boundary linearization.

cancel.json and effect-boundary.json are decided under the SAME per-job
transition.lock. The durable winner is the authority, not whichever CLI
returns first. A cancel after the irreversible boundary cannot reclassify
an effect as CANCELLED or grant a new Publish attempt.

No Android UI input, resource release, or backend cancellation is issued.
"""
from __future__ import annotations

from typing import Any, Mapping

from automation.capability_job_store import (
    AdmittedJob, CapabilityStoreError,
    _locked, _read_json, _atomic_new, _atomic_replace,
    _append, _need, _utc,
)


def request_cancel(
    job: AdmittedJob, *,
    trusted_cancel_authorized: bool,
    reason_code: str = "USER_CANCEL_REQUESTED",
) -> dict[str, Any]:
    """Durably establish cancel intent only if the unsafe boundary lost race."""
    _need(trusted_cancel_authorized is True,
          "CANCEL_AUTHORIZATION_UNAVAILABLE")
    _need(isinstance(reason_code, str) and 0 < len(reason_code) <= 128,
          "CANCEL_REASON_INVALID")
    with _locked(job.path / "transition.lock"):
        state = _read_json(job.path / "state.json")
        _need(state.get("capability_job_id") == job.job_id,
              "CAPABILITY_IDENTITY_MISMATCH")
        result = job.path / "result.json"
        _need(not result.is_symlink(), "TERMINAL_RESULT_UNTRUSTED")
        if result.exists():
            terminal = _read_json(result)
            return {
                "status": "ALREADY_TERMINAL",
                "outcome": terminal.get("outcome"),
                "cancel_won": False,
                "external_effect_retry_allowed": False,
            }
        boundary_path = job.path / "effect-boundary.json"
        _need(not boundary_path.is_symlink(),
              "EFFECT_BOUNDARY_PATH_UNTRUSTED")
        if boundary_path.exists():
            _append(job.path / "journal.jsonl", {
                "event": "CANCEL_AFTER_EFFECT_BOUNDARY",
                "timestamp": _utc(),
                "reason_code": reason_code,
            })
            return {
                "status": "CANCEL_AFTER_EFFECT_BOUNDARY",
                "terminal": False,
                "cancel_won": False,
                "effect_not_undone": True,
                "external_effect_retry_allowed": False,
            }
        path = job.path / "cancel.json"
        _need(not path.is_symlink(), "CANCEL_INTENT_PATH_UNTRUSTED")
        if not path.exists():
            _atomic_new(path, {
                "cancel_version": 1,
                "capability_job_id": job.job_id,
                "request_sha256": job.request_sha256,
                "cancel_requested_at": _utc(),
                "reason_code": reason_code,
                "cutoff": "BEFORE_EFFECT_BOUNDARY",
            })
        else:
            same = _read_json(path)
            _need(same.get("capability_job_id") == job.job_id
                  and same.get("request_sha256") == job.request_sha256,
                  "CANCEL_IDENTITY_CONFLICT")
        if state.get("lifecycle_state") not in {
            "CANCELLING", "CANCELLED", "RECONCILE_REQUIRED",
        }:
            _need(type(state.get("state_revision")) is int
                  and state["state_revision"] >= 0,
                  "STATE_STORE_CORRUPT")
            later = dict(state)
            later.update(
                lifecycle_state="CANCELLING",
                phase="CANCELLING",
                state_revision=state["state_revision"] + 1,
                phase_reason_code=reason_code,
                updated_at=_utc(),
                terminal=False,
            )
            _atomic_replace(job.path / "state.json", later)
        _append(job.path / "journal.jsonl", {
            "event": "CANCEL_REQUESTED",
            "timestamp": _utc(),
            "reason_code": reason_code,
            "cancel_preceded_effect_boundary": True,
        })
        return {
            "status": "CANCEL_REQUESTED",
            "cancel_won": True,
            "terminal": False,
            "backend_stop_confirmation_required": True,
            "external_effect_retry_allowed": False,
        }



# Only independently authenticated first-party control-plane provenance
# can authorize even a durable CANCEL INTENT; a CLI flag cannot.
_CANCEL_INGRESS_ACCEPTED = False
_CANCEL_RECEIPTS = "/opt/y700/runtime/trusted-cancellations"


def request_cancel_from_trusted_source(
    capability_job_id: str, *, reason_code: str,
) -> dict[str, Any]:
    """Exact protected one-job cancellation, never an app stop or UI action."""
    from pathlib import Path
    import re
    from automation.authoritative_state_reader import observe_authoritative_state
    from automation.capability_job_store import CapabilityStore

    if not _CANCEL_INGRESS_ACCEPTED:
        raise CapabilityStoreError("CANCEL_INGRESS_RELEASE_GATE_CLOSED")
    _need(isinstance(capability_job_id, str)
          and re.fullmatch(r"cap-[0-9a-f]{48}", capability_job_id) is not None,
          "CAPABILITY_JOB_ID_INVALID")
    _need(isinstance(reason_code, str)
          and 0 < len(reason_code) <= 128, "CANCEL_REASON_INVALID")
    store = CapabilityStore()
    active = store.jobs / "active" / capability_job_id
    _need(active.is_dir() and not active.is_symlink(),
          "CAPABILITY_CANCEL_SOURCE_UNAVAILABLE")
    immutable = _read_json(active / "identity.json")
    _need(immutable.get("capability_job_id") == capability_job_id,
          "CAPABILITY_CANCEL_IDENTITY_MISMATCH")
    receipt_root = Path(_CANCEL_RECEIPTS)
    _need(receipt_root.is_dir() and not receipt_root.is_symlink(),
          "CANCEL_INGRESS_UNAVAILABLE")
    receipt = _read_json(receipt_root / (capability_job_id + ".json"))
    state = observe_authoritative_state()
    age = receipt.get("observed_boottime_ms")
    actor = receipt.get("principal")
    _need(receipt.get("cancel_authorization_version") == 1
          and receipt.get("source") == "TRUSTED_FIRST_PARTY_CONTROLLER"
          and receipt.get("capability_job_id") == capability_job_id
          and receipt.get("request_sha256")
              == immutable.get("request_sha256")
          and receipt.get("reason_code") == reason_code
          and receipt.get("boot_id") == state.boot_id
          and receipt.get("state_epoch") == state.state_epoch
          and type(age) is int
          and 0 <= state.observed_boottime_ms - age <= 1000
          and isinstance(actor, dict)
          and actor.get("authenticated") is True
          and isinstance(actor.get("principal_id"), str)
          and bool(actor.get("principal_id")),
          "CANCEL_INGRESS_NOT_AUTHENTICATED")
    job = AdmittedJob(
        capability_job_id, active, immutable["request_sha256"],
        immutable["effective_policy_sha256"], False)
    intent = request_cancel(
        job, trusted_cancel_authorized=True, reason_code=reason_code)
    if intent.get("status") != "CANCEL_REQUESTED":
        return intent
    # A safe, exact pre-submit cancellation can complete synchronously.
    # Submission possible, a live UI Claim, or unavailable evidence must
    # remain non-terminal; never report CANCELLED from mere intent.
    try:
        return finalize_pre_submit_cancel_from_durable_proof(
            job, store=store)
    except CapabilityStoreError as exc:
        return {
            **intent,
            "status": "CANCELLING",
            "reason_code": exc.code,
            "terminal": False,
            "external_effect_retry_allowed": False,
            "explicit_reconcile_required": True,
        }


def finalize_pre_submit_cancel_from_durable_proof(
    job: AdmittedJob, *,
    store: "CapabilityStore | None" = None,
) -> dict[str, Any]:
    """Finalize CANCELLED only if exact Backend NEVER reached submission.

    This method never accepts caller-supplied proof booleans. The permanent
    cancel.json already won the effect-boundary linearization under the
    job's transition.lock. We independently re-read that identity, the
    original backend-execution.json, the canonical Android UI claim and
    all exact subordinate evidence. Any uncertainty remains CANCELLING /
    RECONCILE_REQUIRED; it cannot be converted to a safe terminal state.

    The store rechecks durable submission/effect witness under the SAME
    transition lock before writing result.json and moving to archive/.
    """
    from automation import resource_arbiter
    from automation.capability_job_store import CapabilityStore

    store = store or CapabilityStore()
    with _locked(job.path / "transition.lock", shared=True):
        state = _read_json(job.path / "state.json")
        request = _read_json(job.path / "request.json")
        identity = _read_json(job.path / "identity.json")
        _need(
            identity.get("capability_job_id") == job.job_id
            and identity.get("request_sha256") == job.request_sha256
            and state.get("capability_job_id") == job.job_id
            and state.get("request_sha256") == job.request_sha256,
            "CANCEL_DURABLE_IDENTITY_MISMATCH",
        )
        cancel = _read_json(job.path / "cancel.json")
        _need(
            cancel.get("capability_job_id") == job.job_id
            and cancel.get("request_sha256") == job.request_sha256
            and cancel.get("cutoff") == "BEFORE_EFFECT_BOUNDARY"
            and state.get("phase") == "CANCELLING",
            "CANCEL_INTENT_NOT_DURABLE",
        )
        _need(not (job.path / "effect-boundary.json").exists()
              and not (job.path / "result.json").exists()
              and state.get("backend_submitted") is False
              and state.get("effect_uncertain") is False
              and state.get("mutation_uncertain") is False,
              "CANCEL_RECONCILE_REQUIRED")

        backend_path = job.path / "backend.json"
        witness_path = job.path / "backend-execution.json"
        if backend_path.exists() or witness_path.exists():
            binding = _read_json(backend_path)
            execution = _read_json(witness_path)
            _need(
                binding.get("capability_job_id") == job.job_id
                and binding.get("request_sha256") == job.request_sha256
                and execution.get("backend_job_id")
                    == binding.get("backend_job_id")
                and execution.get("request_sha256") == job.request_sha256
                and execution.get("phase") == "NEVER_CREATED"
                and execution.get("submission_possible") is False
                and execution.get("attempt_serial") == 0,
                "CANCEL_BACKEND_NEVER_CREATED_UNPROVEN",
            )
        else:
            _need(
                state.get("phase") == "CANCELLING",
                "CANCEL_PRE_BIND_STATE_CONFLICT",
            )

        try:
            current_claim = resource_arbiter.read_claim()
        except resource_arbiter.ResourceError as exc:
            raise CapabilityStoreError(
                "CANCEL_RESOURCE_OWNERSHIP_UNAVAILABLE") from exc
        _need(
            current_claim is None
            or current_claim.get("capability_job_id") != job.job_id,
            "CANCEL_RESOURCE_STILL_OWNED",
        )
        # No exact UI subjob may survive as a dangling mutation holder.
        # Missing/unreadable provenance is not proof that an ever-started
        # backend is gone, hence this only applies to NEVER_CREATED.
        _need(request.get("submission_id") is not None,
              "CANCEL_REQUEST_IDENTITY_INVALID")

    terminal = store.finalize_terminal(
        job.job_id,
        outcome="CANCELLED",
        backend_never_created_proven=True,
        business_outcome_verified=False,
        reason_code="EXACT_PRE_SUBMIT_CANCEL_VERIFIED",
    )
    return {
        "status": "CANCELLED",
        "terminal": True,
        "capability_job_id": job.job_id,
        "outcome": terminal["outcome"],
        "backend_submitted": False,
        "external_effect_retry_allowed": False,
    }


def classify_cancel_completion(job: AdmittedJob) -> dict[str, Any]:
    """Read-only cancellation eligibility, with NO caller-supplied proof.

    A positive pre-submit result only describes durable evidence observed;
    only finalize_pre_submit_cancel_from_durable_proof writes result.json
    and independently rechecks the same facts under the job lock.
    """
    from automation import resource_arbiter
    with _locked(job.path / "transition.lock", shared=True):
        boundary_path = job.path / "effect-boundary.json"
        _need(not boundary_path.is_symlink(),
              "EFFECT_BOUNDARY_PATH_UNTRUSTED")
        if boundary_path.exists():
            return {
                "status": "RECONCILE_REQUIRED",
                "reason_code": "EFFECT_BOUNDARY_WON",
                "terminal": False,
                "external_effect_retry_allowed": False,
            }
        cancel_path = job.path / "cancel.json"
        _need(not cancel_path.is_symlink(),
              "CANCEL_INTENT_PATH_UNTRUSTED")
        if not cancel_path.exists():
            return {
                "status": "CANCEL_NOT_REQUESTED",
                "terminal": False,
                "external_effect_retry_allowed": False,
            }
        cancel = _read_json(job.path / "cancel.json")
        state = _read_json(job.path / "state.json")
        if (cancel.get("capability_job_id") != job.job_id
                or cancel.get("request_sha256") != job.request_sha256
                or state.get("phase") != "CANCELLING"
                or state.get("backend_submitted") is not False
                or state.get("effect_uncertain") is not False
                or state.get("mutation_uncertain") is not False):
            return {
                "status": "RECONCILE_REQUIRED",
                "reason_code": "CANCEL_DURABLE_STATE_UNCERTAIN",
                "terminal": False,
                "external_effect_retry_allowed": False,
            }
        backend = job.path / "backend.json"
        execution = job.path / "backend-execution.json"
        if backend.exists() or execution.exists():
            try:
                binding = _read_json(backend)
                witness = _read_json(execution)
            except CapabilityStoreError:
                return {
                    "status": "RECONCILE_REQUIRED",
                    "reason_code": "CANCEL_BACKEND_WITNESS_UNREADABLE",
                    "terminal": False,
                    "external_effect_retry_allowed": False,
                }
            if not (
                binding.get("capability_job_id") == job.job_id
                and binding.get("request_sha256") == job.request_sha256
                and witness.get("backend_job_id")
                    == binding.get("backend_job_id")
                and witness.get("phase") == "NEVER_CREATED"
                and witness.get("submission_possible") is False
                and witness.get("attempt_serial") == 0
            ):
                return {
                    "status": "CANCELLING",
                    "reason_code": "BACKEND_STOP_OR_EFFECT_RECONCILE_REQUIRED",
                    "terminal": False,
                    "external_effect_retry_allowed": False,
                }
        try:
            claim = resource_arbiter.read_claim()
        except resource_arbiter.ResourceError:
            return {
                "status": "CANCELLING",
                "reason_code": "RESOURCE_OWNERSHIP_UNAVAILABLE",
                "terminal": False,
                "external_effect_retry_allowed": False,
            }
        safe = claim is None or claim.get("capability_job_id") != job.job_id
        return {
            "status": ("CANCEL_TERMINALIZATION_CANDIDATE"
                       if safe else "CANCELLING"),
            "reason_code": ("EXACT_NEVER_CREATED_POSITIVE"
                            if safe else "RESOURCE_STILL_OWNED"),
            "terminal": False,
            "can_finalize_cancel": safe,
            "external_effect_retry_allowed": False,
        }
