"""Rev3.7 one-owner android_ui resource adapter for ForegroundCoordinator.

Exactly ONE resource_arbiter.acquire_android_ui context per foreground
capability invocation, preserved through every subordinate UI job.
Delegated TikTok Controller uses claim inheritance, not nested acquisition.

A potentially active/uncertain backend retains the durable claim when the
foreground scope exits; only positive quiescence can release it. This
implementation does not guess process liveness from transport timeout.
No daemon or auto-reset. The Gateway release gate is still CLOSED.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from automation import resource_arbiter
from automation.capability_job_store import (
    CapabilityStore, CapabilityStoreError, _read_json, _need,
)


@dataclass(frozen=True)
class _HeldClaim:
    capability_job_id: str
    backend_job_id: str
    request_sha256: str


class CanonicalUIResource:
    """Foreground single owner; never create a second independent flock."""

    def __init__(self, store: CapabilityStore | None = None):
        self.store = store or CapabilityStore()
        self._manager: Any = None
        self._guard: resource_arbiter.ResourceGuard | None = None
        self._held: _HeldClaim | None = None

    def acquire_exact(self, capability_job_id: str,
                      backend_job_id: str) -> dict[str, Any]:
        _need(self._manager is None and self._guard is None
              and self._held is None, "NESTED_UI_RESOURCE_LEASE_DENIED")
        source = self.store.jobs / "active" / capability_job_id
        _need(source.is_dir() and not source.is_symlink(),
              "CAPABILITY_JOB_UNAVAILABLE")
        identity = _read_json(source / "identity.json")
        bound = _read_json(source / "backend.json")
        _need(identity.get("capability_job_id") == capability_job_id
              and bound.get("capability_job_id") == capability_job_id
              and bound.get("backend_job_id") == backend_job_id,
              "RESOURCE_BACKEND_IDENTITY_MISMATCH")
        request_sha = identity.get("request_sha256")
        _need(isinstance(request_sha, str) and len(request_sha) == 64
              and request_sha == bound.get("request_sha256"),
              "RESOURCE_REQUEST_IDENTITY_MISMATCH")
        backend_type = bound.get("backend_type")
        _need(backend_type in {"publisher", "ui_workflow"},
              "RESOURCE_BACKEND_TYPE_INVALID")
        manager = resource_arbiter.acquire_android_ui(
            owner_kind="CAPABILITY",
            owner_id=f"cap:{capability_job_id}",
            backend_type=backend_type,
            backend_job_id=backend_job_id,
            request_sha256=request_sha,
            capability_job_id=capability_job_id,
            timeout_sec=120.0,
        )
        try:
            guard = manager.__enter__()
        except resource_arbiter.ResourceError as exc:
            raise CapabilityStoreError("RESOURCE_ACQUIRE_DENIED") from exc
        # A job may be cancelled/archived WHILE waiting for android_ui.
        # After actually acquiring the canonical Claim, re-read its
        # immutable state under transition.lock. If cancellation won,
        # release ONLY this newly acquired Claim before any backend call.
        # The Gateway's later begin_backend_submission also rechecks the
        # cancel/result boundary under the same job lock.
        try:
            from automation.capability_job_store import _locked
            with _locked(source / "transition.lock", shared=True):
                current_identity = _read_json(source / "identity.json")
                current_binding = _read_json(source / "backend.json")
                state = _read_json(source / "state.json")
                _need(
                    source.is_dir() and not source.is_symlink()
                    and not (source / "cancel.json").exists()
                    and not (source / "cancel.json").is_symlink()
                    and not (source / "result.json").exists()
                    and not (source / "result.json").is_symlink()
                    and not (source / "effect-boundary.json").exists()
                    and current_identity.get("capability_job_id")
                        == capability_job_id
                    and current_identity.get("request_sha256") == request_sha
                    and current_binding.get("backend_job_id") == backend_job_id
                    and current_binding.get("request_sha256") == request_sha
                    and state.get("phase") in {
                        "BACKEND_BOUND", "WAITING_RESOURCE",
                    }
                    and state.get("backend_submitted") is False
                    and state.get("effect_uncertain") is False
                    and state.get("mutation_uncertain") is False,
                    "RESOURCE_ACQUIRE_JOB_CHANGED_OR_CANCELLED",
                )
                _need(
                    resource_arbiter.assert_guard(guard.as_dict()).get(
                        "backend_job_id") == backend_job_id,
                    "RESOURCE_IDENTITY_DRIFT",
                )
        except Exception:
            # No external Backend has been invoked by this adapter.
            # Preserve the original exception; the arbiter's own finally
            # removes only the exact fresh claim it owns.
            manager.__exit__(None, None, None)
            raise
        self._manager = manager
        self._guard = guard
        self._held = _HeldClaim(capability_job_id, backend_job_id,
                                request_sha)
        return guard.as_dict()

    def verify_exact(self, claim: Mapping[str, Any]) -> bool:
        if not isinstance(claim, Mapping) or self._held is None:
            return False
        if self._guard is None or dict(claim) != self._guard.as_dict():
            return False
        try:
            current = resource_arbiter.assert_guard(self._guard.as_dict())
        except resource_arbiter.ResourceError:
            return False
        return bool(
            current.get("owner_kind") == "CAPABILITY"
            and current.get("capability_job_id")
                == self._held.capability_job_id
            and current.get("backend_job_id") == self._held.backend_job_id
            and current.get("request_sha256") == self._held.request_sha256
            and current.get("claim_id") == claim.get("claim_id")
            and current.get("owner_id") == claim.get("owner_id")
        )

    def finish_exact(self, claim: Mapping[str, Any], *,
                     safe_to_release_positive_proof: bool,
                     reason_code: str) -> None:
        """Always close flock; retain durable claim unless positively safe.

        An exception during reconcile marking MUST NOT accidentally release
        the claim in resource_arbiter's finally block.
        """
        _need(self._manager is not None and self._guard is not None
              and self._held is not None, "RESOURCE_LEASE_NOT_OWNED")
        guard = self._guard
        manager = self._manager
        # A synchronous Python return/ACK is NOT native quiescence.
        # Independently re-observe the exact last UI mutator/subjob
        # terminal evidence before releasing this live owner's Claim.
        from automation.resource_stop_observer import (
            positive_synchronous_ui_quiescence,
        )
        never_submitted = False
        if self._held is not None:
            source = self.store.jobs / "active" / self._held.capability_job_id
            try:
                witness = _read_json(source / "backend-execution.json")
                state = _read_json(source / "state.json")
                durable = resource_arbiter.assert_guard(dict(claim))
                never_submitted = (
                    witness.get("phase") == "NEVER_CREATED"
                    and witness.get("submission_possible") is False
                    and witness.get("attempt_serial") == 0
                    and state.get("backend_submitted") is False
                    and state.get("effect_uncertain") is False
                    and state.get("mutation_uncertain") is False
                    and durable.get("active_ui_job_id") is None
                    and durable.get("active_session_id") is None
                    and not (source / "effect-boundary.json").exists()
                )
            except (OSError, CapabilityStoreError,
                    resource_arbiter.ResourceError):
                never_submitted = False
        # Before any possible backend execution, exact NEVER_CREATED proof
        # suffices; afterward independent native child quiescence is required.
        safe = (
            safe_to_release_positive_proof is True
            and self.verify_exact(claim)
            and self._held is not None
            and (
                never_submitted
                or positive_synchronous_ui_quiescence(
                    claim, backend_job_id=self._held.backend_job_id)
            )
        )
        self._manager = None
        self._guard = None
        self._held = None
        try:
            if not safe:
                guard.retained_for_reconcile = True
                # Best effort audit of reconcile. Even if the audit path
                # fails, the durable claim must remain for operator repair.
                try:
                    resource_arbiter.mark_reconcile_required(
                        guard.as_dict(),
                        reason=reason_code[:160] or "BACKEND_LIVENESS_UNKNOWN",
                    )
                except resource_arbiter.ResourceError:
                    pass
        finally:
            manager.__exit__(None, None, None)

    def release_exact(self, claim: Mapping[str, Any]) -> None:
        """Legacy Protocol compatibility: release only by positive proof.

        An unqualified release is not legal; coordinator must use finish_exact
        with its independently collected safe-quiescence evidence.
        """
        raise CapabilityStoreError("RESOURCE_RELEASE_PROOF_REQUIRED")
