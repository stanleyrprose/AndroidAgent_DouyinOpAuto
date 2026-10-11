"""Rev3.7 foreground synchronous capability coordinator — opt-in dormant.

Execution order is immutable request -> trusted policy -> durable backend ID
-> exact resource claim -> TTL/approval recheck -> exact backend submission
-> status/verifier/reconcile. Never creates a second top-level backend on
ambiguity. Does not spawn background tasks, threads, daemons or timers.

Production activation is NOT granted by request flags: the release gate
is a static code constant kept False until final acceptance and merge.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Protocol

from automation import capability_axes
from automation.gateway_adapters import (
    AdapterContractError, prepare_adapter_intent_readonly,
)
from automation.trusted_ingress_approval import (
    IngressAuthorizationUnavailable, inspect_before_admission,
)
from automation.capability_catalog import CatalogUnavailable, load_catalog
from automation.effective_policy import (
    PolicyUnavailable, check_request_contract, resolve_effective_policy,
)
from automation.capability_job_store import (
    AdmittedJob, CapabilityStore, CapabilityStoreError,
    _atomic_replace, _read_json, _locked, _need, _utc,
)
from automation.authoritative_state_reader import (
    AuthorityUnavailable, observe_authoritative_state,
)
from automation.runtime_authority import (
    LocalRootRuntimeAuthority, RuntimeEvidenceUnavailable,
)
from automation.pre_admission_authority import read_trusted_pre_admission
from automation.runtime_evidence_producer import publish_post_admission_readonly
from automation.ttl_clock_guard import (
    ClockGuardUnavailable, accept_ttl, classify_pre_submit_ttl,
)

# No runtime/caller override; can only change through reviewed release.
_PRODUCTION_GATEWAY_ENABLED = False
_BUSINESS_EFFECTS_ENABLED = False
_EXTERNAL_TIKTOK_COMMIT_ACCEPTED = False


class Backend(Protocol):
    def prepare_exact(self, backend_type: str, backend_id: str,
                      intent: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def lookup_exact(self, backend_type: str,
                     backend_id: str) -> Mapping[str, Any]: ...
    def submit_exact(self, backend_type: str, backend_id: str,
                     intent: Mapping[str, Any]) -> Mapping[str, Any]: ...


class Resource(Protocol):
    def acquire_exact(self, capability_job_id: str,
                      backend_job_id: str) -> Mapping[str, Any]: ...
    def verify_exact(self, claim: Mapping[str, Any]) -> bool: ...
    def finish_exact(self, claim: Mapping[str, Any], *,
                     safe_to_release_positive_proof: bool,
                     reason_code: str) -> None: ...


class RuntimeAuthority(Protocol):
    """Privileged local observer, NOT an invocation/workflow-provided flag."""
    def observe_fresh(self, capability_job_id: str,
                      backend_job_id: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class TrustedInvocation:
    """Constructed by a local authenticated policy + adapter layer."""
    request: Mapping[str, Any]
    contract: Mapping[str, Any]
    policy: Mapping[str, Any]
    runtime_facts: Mapping[str, Any]
    identity_facts: Mapping[str, Any]
    backend_type: str
    ui_resource_required: bool
    dry_run: bool


_FAILURE_STAGES = {
    "ADMISSION": "CONTROL_PLANE",
    "PERMISSION": "PERMISSION",
    "BACKEND_BOUND": "PERSISTENCE",
    "PRE_SUBMIT_POLICY": "PERMISSION",
    "PRE_SUBMIT_TTL": "PERMISSION",
    "RESOURCE_OWNERSHIP": "RESOURCE_OWNERSHIP",
    "BACKEND_DISPATCH": "ACTION_DISPATCH",
    "BACKEND_RECONCILE": "BUSINESS_VERIFICATION",
    "STATUS": "PERSISTENCE",
}
_PRE_SUBMIT_FAILURES = frozenset({
    "ADMISSION", "PERMISSION", "BACKEND_BOUND",
    "PRE_SUBMIT_POLICY", "PRE_SUBMIT_TTL", "RESOURCE_OWNERSHIP",
})


def _blocked(code: str, job_id: str | None = None,
             *, phase: str = "ADMISSION") -> dict[str, Any]:
    """Stage-typed refusal; never fabricate zero attempts after submit.

    An unknown transport outcome is UNKNOWN, not a confirmed zero click.
    Retrying an ambiguous external effect requires explicit reconciliation.
    """
    pre_submit = phase in _PRE_SUBMIT_FAILURES
    unsafe_unknown = (
        phase == "BACKEND_RECONCILE" or code in {
            "RECONCILE_REQUIRED", "BACKEND_ACK_UNVERIFIED",
            "BACKEND_SUBMISSION_UNKNOWN", "EXACT_BACKEND_ALREADY_EXISTS",
        }
    )
    if unsafe_unknown:
        retry_class = "RECONCILE_ONLY"
    elif code in {
        "FRAME_STALE", "FRAME_REVISION_STALE",
        "FRAME_FOREGROUND_DRIFT", "PRE_SUBMIT_AUTHORITY_STALE",
        "TRUSTED_AUTHORITY_OBSERVER_UNAVAILABLE",
    }:
        retry_class = "REOBSERVE_ONLY"
    else:
        retry_class = "NO_AUTOMATIC_RETRY"
    return {
        "status": "BLOCKED",
        "reason_code": code,
        "failure_stage": _FAILURE_STAGES.get(phase, "PERSISTENCE"),
        "source_phase": phase,
        "last_success_stage": (
            "RESOURCE_OWNERSHIP" if phase == "BACKEND_DISPATCH"
            else "PERMISSION" if phase == "RESOURCE_OWNERSHIP"
            else None
        ),
        "retry_class": retry_class,
        "capability_job_id": job_id,
        "action_attempts": 0 if pre_submit else None,
        "backend_submitted": False if pre_submit else None,
        "external_effect_attempts": 0 if pre_submit else None,
        "external_effect_retry_allowed": False,
        "gateway_activation_enabled": False,
    }


def _preflight(invocation: TrustedInvocation, *, fresh_runtime_witness: bool = False) -> dict[str, Any]:
    """Resolve exact static Catalog/policy before any job or backend write."""
    name = invocation.request.get("capability")
    _need(isinstance(name, str), "CAPABILITY_REQUEST_INVALID")
    catalog = load_catalog()
    entry = catalog.get(name)
    _need(entry is not None, "CAPABILITY_CATALOG_ENTRY_MISSING")
    if name == "tiktok.publish":
        payload = invocation.request.get("payload")
        _need(isinstance(payload, Mapping)
              and payload.get("publish_mode") in {"DRY_RUN", "COMMIT"}
              and (payload["publish_mode"] == "DRY_RUN")
                  is invocation.dry_run,
              "EXECUTION_MODE_MISMATCH")
    minimum = resolve_effective_policy(entry)
    _need(dict(invocation.policy) == minimum.as_dict(),
          "EFFECTIVE_POLICY_IDENTITY_MISMATCH")
    if fresh_runtime_witness:
        trusted_facts = dict(invocation.identity_facts)
        measured_runtime = dict(invocation.runtime_facts)
    else:
        observed_facts = read_trusted_pre_admission(
            immutable_request=invocation.request,
            effective_policy=invocation.policy,
        )
        trusted_facts = dict(observed_facts["identity_facts"])
        measured_runtime = dict(observed_facts["runtime_facts"])
    if name == "tiktok.publish" and not invocation.dry_run:
        approved = inspect_before_admission(
            request=invocation.request,
            effective_policy=invocation.policy,
            current_clock_health=trusted_facts.get(
                "clock_health", "UNKNOWN"))
        _need(approved["authenticated_control_plane_fact"] is True,
              "INGRESS_AUTH_UNAVAILABLE")
        trusted_facts["identity_authenticated"] = True
        trusted_facts["current_approval_valid"] = True
    check_request_contract(
        request=invocation.request,
        capability=entry,
        effective=minimum,
        trusted_authenticated_identity=(
            trusted_facts.get("identity_authenticated") is True
        ),
    )
    view = capability_axes.inspect_capability_readonly(
        name,
        runtime_facts=measured_runtime,
        trusted_policy_facts=trusted_facts,
        catalog_advertised=entry["enabled"],
    )
    admission = capability_axes.readonly_admission_explanation(view)
    if admission["reason_code"] != "GATEWAY_NOT_ACTIVATED":
        return admission
    return {"status": "PRECHECKED_READ_ONLY", "reason_code": None,
            "trusted_clock_health": trusted_facts.get("clock_health", "UNKNOWN")}


def preview_invocation(invocation: TrustedInvocation) -> dict[str, Any]:
    """A safe discovery/admission preview; no durable job or backend."""
    try:
        result = _preflight(invocation)
    except (CapabilityStoreError, CatalogUnavailable, PolicyUnavailable,
            IngressAuthorizationUnavailable, RuntimeEvidenceUnavailable,
            AttributeError, TypeError) as exc:
        return _blocked(getattr(exc, "code", "CAPABILITY_REQUEST_INVALID"))
    return {
        **result,
        "capability": invocation.request.get("capability"),
        "backend_submitted": False,
        "external_effect_attempts": 0,
        "execution_authorized": False,
        "gateway_activation_enabled": False,
    }


class ForegroundCoordinator:
    """Single foreground caller owns execution; no detached recovery worker."""

    def __init__(self, *,
                 store: CapabilityStore | None = None,
                 backend: Backend | None = None,
                 resource: Resource | None = None,
                 authority: RuntimeAuthority | None = None):
        self.store = store or CapabilityStore()
        self.backend = backend
        self.resource = resource
        # Runtime facts are never caller/workflow-provided in the active
        # coordinator. Only the fixed root-owned source may observe them.
        # The injectable Protocol stays documented but cannot replace
        # this observer via request/CLI during development.
        self.authority = LocalRootRuntimeAuthority(jobs_root=self.store.jobs)

    def invoke(self, invocation: TrustedInvocation) -> dict[str, Any]:
        if not _PRODUCTION_GATEWAY_ENABLED:
            return _blocked("GATEWAY_RELEASE_GATE_CLOSED")
        if invocation.request.get("capability") == "tiktok.publish":
            if not _BUSINESS_EFFECTS_ENABLED:
                return _blocked("BUSINESS_RELEASE_GATE_CLOSED")
            if not invocation.dry_run and not _EXTERNAL_TIKTOK_COMMIT_ACCEPTED:
                return _blocked("TIKTOK_COMMIT_RELEASE_GATE_CLOSED")
        try:
            preflight = _preflight(invocation)
            if preflight["status"] != "PRECHECKED_READ_ONLY":
                return _blocked(preflight["reason_code"], phase="PERMISSION")
            observed = observe_authoritative_state()
            # The initial TTL witness is minted at most once by a durable
            # admission. A replay never overwrites its original deadline.
            witness = None
            expires = invocation.request.get("expires_at")
            if expires is not None and (
                preflight.get("trusted_clock_health") == "HEALTHY"
            ):
                try:
                    witness = accept_ttl(
                        expires_at=expires,
                        boot_id=observed.boot_id,
                        contract_max_ttl_sec=invocation.policy["max_ttl_sec"],
                    ).durable()
                except (ClockGuardUnavailable, KeyError, TypeError):
                    witness = None
            admitted = self.store.admit(
                invocation.request,
                trusted_contract=invocation.contract,
                trusted_effective_policy=invocation.policy,
                ttl_clock_evidence=witness,
            )
            current = self.store.observe(admitted.job_id)
            if admitted.replayed:
                # Frozen §13 exceptional same-submission availability
                # recovery: only the original durable, explicitly
                # retriable prerequisite block, with exact NEVER_CREATED
                # witness and zero mutation/effect uncertainty. All other
                # transport replays are strictly read-only.
                eligible = False
                old_binding = None
                if (not current.get("terminal")
                        and not current.get("reconcile_required")
                        and current.get("phase") == "WAITING_RESOURCE"
                        and current.get("backend_submitted") is False
                        and current.get("effect_uncertain") is False
                        and current.get("mutation_uncertain") is False
                        and admitted.path
                            == self.store.jobs / "active" / admitted.job_id
                        and not admitted.path.is_symlink()):
                    old_state = _read_json(admitted.path / "state.json")
                    old_binding = _read_json(
                        admitted.path / "backend.json")
                    witness = _read_json(
                        admitted.path / "backend-execution.json")
                    eligible = (
                        old_state.get("phase_reason_code") in {
                            "CLOCK_SUSPECT_PRE_SUBMIT",
                            "RESOURCE_BUSY_PRE_SUBMIT",
                        }
                        and old_binding.get("backend_type")
                            == invocation.backend_type
                        and old_binding.get("capability_job_id")
                            == admitted.job_id
                        and old_binding.get("request_sha256")
                            == admitted.request_sha256
                        and witness.get("backend_job_id")
                            == old_binding.get("backend_job_id")
                        and witness.get("request_sha256")
                            == admitted.request_sha256
                        and witness.get("phase") == "NEVER_CREATED"
                        and witness.get("submission_possible") is False
                        and witness.get("attempt_serial") == 0
                        and not (admitted.path / "effect-boundary.json").exists()
                        and not (admitted.path / "cancel.json").exists()
                        and not (admitted.path / "result.json").exists()
                    )
                if eligible and old_binding is not None:
                    # This exact-ID path STILL checks independent Backend
                    # existence, live policy/TTL, canonical Claim, and the
                    # admission fence before the first possible effect.
                    return self._continue_exact_backend(
                        invocation, admitted, old_binding)
                return {
                    **current,
                    "status": "REPLAY_RESOLVED_READ_ONLY",
                    "replayed_submission": True,
                    "backend_resubmitted": False,
                    "external_effect_retry_allowed": False,
                    "execution_authorized": False,
                }
            if current["terminal"]:
                return {**current, "status": "ALREADY_TERMINAL"}
            if current["reconcile_required"] or (
                current["backend_submitted"]
                or current["effect_uncertain"]
                or current["mutation_uncertain"]
            ):
                return _blocked(
                    "RECONCILE_REQUIRED", admitted.job_id,
                    phase="BACKEND_RECONCILE")
            binding = self.store.bind_backend(
                admitted, backend_type=invocation.backend_type)
            # This branch is unreachable during local development because
            # _PRODUCTION_GATEWAY_ENABLED stays source-level False.
            return self._continue_exact_backend(
                invocation, admitted, binding)
        except (CapabilityStoreError, AuthorityUnavailable,
                CatalogUnavailable, PolicyUnavailable,
                AdapterContractError, IngressAuthorizationUnavailable,
                RuntimeEvidenceUnavailable) as exc:
            return _blocked(
                getattr(exc, "code", "AUTHORITY_UNAVAILABLE"))
        except Exception:
            return _blocked("COORDINATOR_UNAVAILABLE")

    def _continue_exact_backend(
        self, invocation: TrustedInvocation, admitted: AdmittedJob,
        binding: Mapping[str, Any],
    ) -> dict[str, Any]:
        """No secondary backend identity, no effect replay on uncertainty.

        Enabled only after a separately reviewed source-level release gate.
        Adapter implementers must persist their exact submission identity.
        """
        job_id = admitted.job_id
        backend_id = binding.get("backend_job_id")
        if self.backend is None:
            return _blocked("BACKEND_ADAPTER_UNAVAILABLE", job_id,
                            phase="BACKEND_BOUND")
        if not isinstance(backend_id, str) or not backend_id:
            return _blocked("BACKEND_BINDING_INVALID", job_id,
                            phase="BACKEND_BOUND")
        # First inspect the deterministic ID. NEVER try '-02' on timeout.
        try:
            existing = self.backend.lookup_exact(
                invocation.backend_type, backend_id)
        except Exception:
            return _blocked("BACKEND_LOOKUP_UNAVAILABLE", job_id,
                            phase="BACKEND_RECONCILE")
        if not isinstance(existing, Mapping):
            return _blocked("BACKEND_LOOKUP_UNAVAILABLE", job_id,
                            phase="BACKEND_RECONCILE")
        if existing.get("exists") is True:
            if (existing.get("backend_job_id") != backend_id
                    or existing.get("request_sha256")
                    != admitted.request_sha256):
                return _blocked("JOB_CONTRACT_VIOLATION", job_id,
                                phase="BACKEND_RECONCILE")
            # Attachment to existing backend is allowed; no duplicate submit.
            return {
                **_blocked("EXACT_BACKEND_ALREADY_EXISTS", job_id,
                           phase="BACKEND_RECONCILE"),
                "backend_job_id": backend_id,
                "repeated_backend_submission": False,
            }
        if not (existing.get("exists") is False
                and existing.get("durable_never_created_proof") is True):
            return _blocked("BACKEND_NEVER_CREATED_UNPROVEN", job_id,
                            phase="BACKEND_RECONCILE")

        claim = None
        admission_read_hold = None
        admission_lock_held = False
        resource_safe_to_release = True  # no external submission possible yet
        try:
            if invocation.ui_resource_required:
                if self.resource is None:
                    return _blocked("RESOURCE_ARBITER_UNAVAILABLE", job_id,
                                    phase="RESOURCE_OWNERSHIP")
                claim = self.resource.acquire_exact(job_id, backend_id)
                if (not isinstance(claim, Mapping)
                        or claim.get("resource") != "android_ui"
                        or not isinstance(claim.get("claim_id"), str)
                        or not self.resource.verify_exact(claim)):
                    return _blocked("STALE_RESOURCE_OWNERSHIP", job_id,
                                    phase="RESOURCE_OWNERSHIP")
            # After resource wait, a newly observed privileged runtime/policy
            # snapshot is mandatory. Never reuse pre-wait identity/readiness.
            if self.authority is None:
                return _blocked("TRUSTED_AUTHORITY_OBSERVER_UNAVAILABLE",
                                job_id, phase="PRE_SUBMIT_POLICY")
            try:
                # A privileged in-process foreground sensor produces a NEW
                # exact authority sample after the canonical resource wait.
                # It never accepts transport-provided identity/readiness.
                publish_post_admission_readonly(
                    capability_job_id=job_id, backend_job_id=backend_id,
                )
                fresh = self.authority.observe_fresh(job_id, backend_id)
            except Exception:
                return _blocked("TRUSTED_AUTHORITY_OBSERVER_UNAVAILABLE",
                                job_id, phase="PRE_SUBMIT_POLICY")
            observed = observe_authoritative_state()
            if not isinstance(fresh, Mapping):
                return _blocked("AUTHORITY_FACTS_UNAVAILABLE", job_id,
                                phase="PRE_SUBMIT_POLICY")
            sampled_at = fresh.get("observed_boottime_ms")
            if (fresh.get("boot_id") != observed.boot_id
                    or fresh.get("state_epoch") != observed.state_epoch
                    or fresh.get("revision") != observed.revision
                    or fresh.get("capability_job_id") != job_id
                    or fresh.get("backend_job_id") != backend_id
                    or type(sampled_at) is not int
                    or sampled_at > observed.observed_boottime_ms
                    or observed.observed_boottime_ms - sampled_at > 1000
                    or fresh.get("effective_policy_sha256")
                        != admitted.effective_policy_sha256
                    or not isinstance(fresh.get("identity_facts"), Mapping)
                    or not isinstance(fresh.get("runtime_facts"), Mapping)):
                return _blocked("PRE_SUBMIT_AUTHORITY_STALE", job_id,
                                phase="PRE_SUBMIT_POLICY")
            current_invocation = replace(
                invocation,
                identity_facts=dict(fresh["identity_facts"]),
                runtime_facts=dict(fresh["runtime_facts"]),
            )
            # TTL is rechecked AFTER waiting for resource, BEFORE submit.
            # Without healthy wall/boot proof, a new backend cannot start.
            if invocation.request.get("expires_at") is not None:
                # The persisted original witness, never fresh transport
                # metadata, controls the same-boot monotonic deadline.
                witness = _read_json(admitted.path / "ttl-clock.json")
                try:
                    ttl_state = classify_pre_submit_ttl(
                        evidence=witness,
                        current_boot_id=observed.boot_id,
                        backend_submitted=False,
                        current_clock_health=current_invocation.identity_facts.get(
                            "clock_health", "UNKNOWN"),
                        backend_never_created_positive_proof=True,
                    )
                except ClockGuardUnavailable as exc:
                    if exc.code == "CLOCK_SUSPECT_PRE_SUBMIT":
                        self.store.record_pre_submit_prerequisite_block(
                            admitted, reason_code="CLOCK_SUSPECT_PRE_SUBMIT")
                    return _blocked(exc.code, job_id, phase="PRE_SUBMIT_TTL")
                if ttl_state["status"] == "EXPIRED":
                    self.store.advance_no_effect(
                        job_id, phase="EXPIRED",
                        reason_code="REQUEST_EXPIRED_BEFORE_BACKEND_SUBMIT",
                        backend_never_created_positive_proof=True)
                    return _blocked("REQUEST_EXPIRED", job_id,
                                    phase="PRE_SUBMIT_TTL")
                if ttl_state["status"] != "PRE_SUBMIT_TTL_VALID":
                    refusal = ttl_state.get(
                        "reason_code", "CLOCK_SUSPECT_PRE_SUBMIT")
                    if refusal == "CLOCK_SUSPECT_PRE_SUBMIT":
                        self.store.record_pre_submit_prerequisite_block(
                            admitted, reason_code=refusal)
                    return _blocked(
                        refusal, job_id, phase="PRE_SUBMIT_TTL")
            # Repeat preflight using the independently reobserved identity,
            # permission, and readiness, not the original request snapshot.
            status = _preflight(current_invocation,
                               fresh_runtime_witness=True)
            if status["status"] != "PRECHECKED_READ_ONLY":
                return _blocked(
                    status["reason_code"], job_id,
                    phase="PRE_SUBMIT_POLICY")

            # Final exact resource-session recheck immediately before the
            # backend's first possible side effect. A changed claim cannot
            # be resurrected from a previous successful check.
            if claim is not None and (
                self.resource is None
                or self.resource.verify_exact(claim) is not True
            ):
                return _blocked("STALE_RESOURCE_OWNERSHIP", job_id,
                                phase="RESOURCE_OWNERSHIP")
            # Hold the same canonical admission lock SHARED from the last
            # eligibility decision THROUGH synchronous Backend return. The
            # release operator must acquire it EXCLUSIVE to install a fence.
            # Without this hold, a Job admitted before the fence could
            # submit a new UI mutation after the operator observed quiet.
            from automation.admission_fence import (
                assert_admission_unfenced_readonly,
                AdmissionFenceUnavailable,
            )
            admission_read_hold = _locked(
                self.store.submissions / ".admission.lock", shared=True)
            admission_read_hold.__enter__()
            admission_lock_held = True
            try:
                assert_admission_unfenced_readonly(
                    submissions_root=self.store.submissions)
            except AdmissionFenceUnavailable as exc:
                raise CapabilityStoreError(exc.code) from exc
            # Static adapter contract translates exact immutable payload;
            # no request-selected resource, fallback, backend or policy.
            prepared = prepare_adapter_intent_readonly(
                capability=invocation.request["capability"],
                immutable_payload=invocation.request["payload"],
                exact_backend_id=backend_id,
                exact_request_sha256=admitted.request_sha256,
            )
            if (prepared["backend_type"] != invocation.backend_type
                    or prepared["needs_android_ui"] is not
                    invocation.ui_resource_required):
                return _blocked("BACKEND_ADAPTER_CONTRACT_MISMATCH", job_id,
                                phase="BACKEND_DISPATCH")
            exact_intent = {
                "adapter_intent": prepared,
                "capability_job_id": job_id,
                "backend_job_id": backend_id,
                "request_sha256": admitted.request_sha256,
                "effective_policy_sha256": admitted.effective_policy_sha256,
                "resource_guard": dict(claim) if claim else None,
                "execution_mode": "DRY_RUN"
                    if invocation.dry_run else "EXECUTE",
            }
            # A BUSINESS COMMIT approval is a separate immutable fact,
            # rooted in the pre-existing authenticated one-URL ingress.
            # Record under the SAME capability transition lock before the
            # adapter binds an existing Publisher; a second invocation
            # cannot invent a new approval or change the request hash.
            if (invocation.request.get("capability") == "tiktok.publish"
                    and invocation.dry_run is False):
                from automation.effect_boundary import record_approval
                from automation.trusted_ingress_approval import (
                    prepare_approval_for_recording,
                )
                approval = prepare_approval_for_recording(
                    admitted,
                    current_clock_health=current_invocation.identity_facts.get(
                        "clock_health", "UNKNOWN"),
                )
                record_approval(
                    admitted, trusted_approval=approval,
                    trusted_clock_health=current_invocation.identity_facts.get(
                        "clock_health", "UNKNOWN"),
                )
            # The adapter binds to its EXISTING backend/artifact and
            # persists exact provenance before the submit-possible marker.
            # This must neither launch, wake, unlock nor mutate Android.
            if self.backend is None:
                return _blocked("BACKEND_ADAPTER_UNAVAILABLE", job_id,
                                phase="BACKEND_DISPATCH")
            prepared_receipt = self.backend.prepare_exact(
                invocation.backend_type, backend_id, exact_intent)
            if not (isinstance(prepared_receipt, Mapping)
                    and prepared_receipt.get("prepared") is True
                    and prepared_receipt.get("backend_job_id") == backend_id
                    and prepared_receipt.get("request_sha256")
                        == admitted.request_sha256):
                return _blocked("BACKEND_PREPARATION_UNVERIFIED", job_id,
                                phase="BACKEND_DISPATCH")

            # The exact Backend ID is bound before resource claim.
            # Under the same job transition lock, close the NEVER_CREATED
            # window with a durable SUBMISSION_POSSIBLE witness BEFORE
            # entering any external backend submission code.
            self.store.begin_backend_submission(
                admitted,
                exact_backend_job_id=backend_id,
                exact_resource_claim=dict(claim) if claim is not None else None,
            )
            # From this durable instant, the backend may have executed;
            # release is forbidden without independently positive quiescence.
            resource_safe_to_release = False
            # Even a crash between the witness fsync and the call below is
            # RECONCILE_REQUIRED, NEVER proof of safe retry.
            try:
                acknowledgement = self.backend.submit_exact(
                    invocation.backend_type, backend_id, exact_intent)
            except Exception:
                self.store.mark_backend_uncertain(
                    admitted, reason_code="BACKEND_SUBMISSION_UNKNOWN",
                    effect_may_have_occurred=not invocation.dry_run,
                )
                return _blocked("RECONCILE_REQUIRED", job_id,
                                phase="BACKEND_RECONCILE")
            if (not isinstance(acknowledgement, Mapping)
                    or acknowledgement.get("backend_job_id") != backend_id
                    or acknowledgement.get("request_sha256")
                    != admitted.request_sha256
                    or acknowledgement.get("accepted") is not True):
                self.store.mark_backend_uncertain(
                    admitted, reason_code="BACKEND_ACK_UNVERIFIED",
                    effect_may_have_occurred=not invocation.dry_run,
                )
                return _blocked("RECONCILE_REQUIRED", job_id,
                                phase="BACKEND_RECONCILE")
            self.store.record_backend_submission(
                admitted, exact_backend_job_id=backend_id,
                backend_identity_confirmed=True)
            # An EXACT trusted synchronous adapter may positively prove
            # that its UI backend/subordinates all completed. An ACK alone
            # or a transport timeout is insufficient to release ownership.
            if (acknowledgement.get("ui_mutators_quiesced_positive") is True
                    and self.resource is not None
                    and claim is not None
                    and self.resource.verify_exact(claim)):
                from automation.resource_stop_observer import (
                    positive_synchronous_ui_quiescence,
                )
                # An ACK or empty active subjob slots never grants lock
                # release without independently accepted native evidence.
                resource_safe_to_release = (
                    positive_synchronous_ui_quiescence(
                        claim, backend_job_id=backend_id))
            # An ACK is execution evidence, NOT business outcome. Only
            # deterministic synchronous adapters with their own durable
            # accepted verifier receipt may enter result.json/archive.
            adapter_type = invocation.backend_type
            positive_verifier = False
            if adapter_type in {"observation", "root_exec"}:
                # The adapter's ACK is transport evidence, not a terminal
                # verifier. Reopen the immutable, exact-job result persisted
                # by the fixed backend before declaring VERIFIED.
                result_name = ("observation-result.json"
                               if adapter_type == "observation"
                               else "root-result.json")
                try:
                    durable_result = _read_json(admitted.path / result_name)
                except (OSError, ValueError, CapabilityStoreError):
                    durable_result = {}
                identity_ok = (
                    durable_result.get("capability_job_id") == job_id
                    and durable_result.get("backend_job_id") == backend_id
                    and durable_result.get("request_sha256")
                        == admitted.request_sha256
                )
                if adapter_type == "observation":
                    positive_verifier = (
                        identity_ok
                        and durable_result.get("observation_result_version") == 1
                        and durable_result.get("authoritative_state_observed")
                            is True
                        and durable_result.get("read_only") is True
                        and acknowledgement.get("backend_synchronous_complete")
                            is True
                        and isinstance(acknowledgement.get("read_only_authority"),
                                       Mapping)
                        and acknowledgement["read_only_authority"].get("status")
                            == "READ_ONLY_SOT_OBSERVED"
                    )
                else:
                    positive_verifier = (
                        identity_ok
                        and durable_result.get("root_result_version") == 1
                        and durable_result.get("fixed_maintenance_contract_id")
                            == "read-only-system-info.v1"
                        and durable_result.get("root_epoch_advanced") is True
                        and durable_result.get("command_exited_zero") is True
                        and acknowledgement.get("root_epoch_advanced") is True
                        and acknowledgement.get("ui_mutators_quiesced_positive")
                            is True
                    )
            elif adapter_type == "ui_workflow":
                proof = acknowledgement.get("settings_golden")
                try:
                    durable_restore = _read_json(
                        admitted.path / "settings-restore-result.json")
                except (OSError, ValueError, CapabilityStoreError):
                    durable_restore = {}
                positive_verifier = (
                    resource_safe_to_release
                    and durable_restore.get("settings_restore_result_version") == 1
                    and durable_restore.get("capability_job_id") == job_id
                    and durable_restore.get("backend_job_id") == backend_id
                    and durable_restore.get("request_sha256")
                        == admitted.request_sha256
                    and durable_restore.get("restored_verified") is True
                    and durable_restore.get("initial_mode") in {"LIGHT", "DARK"}
                    and durable_restore.get("initial_mode")
                        == durable_restore.get("restored_mode")
                    and isinstance(proof, Mapping)
                    and proof.get("status") == "VERIFIED"
                    and proof.get("initial_mode")
                        == durable_restore.get("initial_mode")
                    and proof.get("restored_mode")
                        == durable_restore.get("restored_mode")
                )
            elif adapter_type == "publisher":
                business = acknowledgement.get("publisher_outcome")
                if (isinstance(business, Mapping)
                        and invocation.dry_run is True):
                    # A DRY_RUN is NOT public publication. To end this
                    # local-only preview, require successful reversible
                    # cleanup plus independently verified native/UI Core
                    # subordinate quiescence under the SAME exact Claim.
                    from automation.resource_stop_observer import (
                        positive_synchronous_ui_quiescence,
                    )
                    positive_verifier = (
                        business.get("status") == "DRY_RUN_READY_ONLY"
                        and business.get("ui_cleanup_complete") is True
                        and business.get("external_effect_attempts") == 0
                        and resource_safe_to_release
                        and claim is not None
                        and positive_synchronous_ui_quiescence(
                            claim, backend_job_id=backend_id)
                    )
                elif isinstance(business, Mapping):
                    # A positive Profile fact establishes BUSINESS outcome
                    # independently of resource-only stop/reconcile status.
                    positive_verifier = (
                        business.get("status") == "PROFILE_VERIFIED"
                        and isinstance(business.get("verification"), Mapping)
                        and business["verification"].get("verified") is True
                    )
            if positive_verifier:
                terminal = self.store.finalize_terminal(
                    job_id,
                    outcome="VERIFIED",
                    backend_never_created_proven=False,
                    business_outcome_verified=True,
                    exact_backend_id=backend_id,
                    reason_code="POSITIVE_BACKEND_VERIFIER_RECEIPT",
                )
                return {
                    "status": "VERIFIED",
                    "capability_job_id": job_id,
                    "backend_job_id": backend_id,
                    "outcome": terminal["outcome"],
                    "terminal": True,
                    "external_effect_retry_allowed": False,
                }
            return {
                "status": "BACKEND_SUBMITTED",
                "capability_job_id": job_id,
                "backend_job_id": backend_id,
                "backend_submitted": True,
                "repeated_backend_submission": False,
                "external_effect_verified": False,
                "terminal": False,
                "next_action": "OBSERVE_EXACT_BACKEND",
            }
        except Exception as exc:
            # A failure after durable SUBMISSION_POSSIBLE is not a normal
            # prerequisite block even when no ACK reached this process.
            # It may have crossed an external effect; keep the ORIGINAL
            # Backend ID and force exact reconciliation, never resubmit.
            if not resource_safe_to_release:
                try:
                    source = self.store.jobs / "active" / job_id
                    if (source.is_dir() and not source.is_symlink()
                            and not (source / "result.json").exists()):
                        self.store.mark_backend_uncertain(
                            admitted,
                            reason_code="POST_SUBMISSION_PATH_UNAVAILABLE",
                            effect_may_have_occurred=not invocation.dry_run,
                        )
                except Exception:
                    # A partial write or archive-crash window must not be
                    # 'repaired' from this exception path. The durable
                    # witness and retained Claim stay authoritative.
                    pass
                return _blocked(
                    "RECONCILE_REQUIRED", job_id,
                    phase="BACKEND_RECONCILE",
                )
            if isinstance(exc, (
                CapabilityStoreError, AuthorityUnavailable,
                CatalogUnavailable, PolicyUnavailable,
                AdapterContractError, IngressAuthorizationUnavailable,
                RuntimeEvidenceUnavailable,
            )):
                return _blocked(
                    getattr(exc, "code", "AUTHORITY_UNAVAILABLE"),
                    job_id, phase="BACKEND_DISPATCH",
                )
            return _blocked("BACKEND_PRE_SUBMIT_UNAVAILABLE",
                            job_id, phase="BACKEND_DISPATCH")
        finally:
            # Finish exact resource ownership BEFORE giving the release
            # operator the exclusive admission flock. A fence installer
            # cannot observe a half-decided Claim between backend completion
            # and release/retain. Always unlock even if cleanup raises.
            try:
                if claim is not None and self.resource is not None:
                    self.resource.finish_exact(
                        claim,
                        safe_to_release_positive_proof=resource_safe_to_release,
                        reason_code=("SAFE_PRE_SUBMIT_STOP" if
                                     resource_safe_to_release
                                     else "BACKEND_OR_UI_LIVENESS_UNKNOWN"),
                    )
            finally:
                # Ambiguous/detached execution still blocks upgrade by its
                # durable Job and retained Claim even after this flock exits.
                if admission_lock_held:
                    admission_read_hold.__exit__(None, None, None)

    def status(self, job_id: str) -> dict[str, Any]:
        """Read-only; cannot implicitly repair old uncertain jobs."""
        try:
            return self.store.observe(job_id)
        except CapabilityStoreError as exc:
            return _blocked(exc.code, job_id, phase="STATUS")

    def reconcile(self, job_id: str) -> dict[str, Any]:
        """Inspect exact durable outcome; never replay, release or archive.

        A positive receipt is a proposal for separately authorized final
        reconciliation, not permission for this foreground API to mutate.
        """
        from automation.capability_reconcile_runtime import (
            inspect_exact_outcome_readonly,
        )
        try:
            current = self.store.observe(job_id)
            evidence = inspect_exact_outcome_readonly(
                job_id, store=self.store)
        except (CapabilityStoreError, OSError, ValueError) as exc:
            return {
                **_blocked(getattr(exc, "code", "RECONCILE_EVIDENCE_UNAVAILABLE"),
                           job_id, phase="BACKEND_RECONCILE"),
                "backend_replayed": False,
                "capability_state_mutated": False,
            }
        return {
            "status": "RECONCILE_INSPECTED_READ_ONLY",
            "capability_job_id": job_id,
            "capability_terminal": current.get("terminal") is True,
            "durable_outcome_status": evidence.get("status", "UNKNOWN"),
            "reason_code": evidence.get("reason_code"),
            "backend_job_id": evidence.get("backend_job_id"),
            "next_action": (
                "SEPARATELY_AUTHORIZED_EXACT_FINALIZATION"
                if evidence.get("status") in {
                    "POSITIVE_PROFILE_VERIFIER_OBSERVED",
                    "POSITIVE_BACKEND_VERIFIER_OBSERVED",
                    "TERMINAL_ARCHIVE_PENDING_READ_ONLY",
                    "PUBLISHER_ARCHIVE_PENDING",
                } else "EXACT_BACKEND_AND_EFFECT_OBSERVATION"
            ),
            "backend_replayed": False,
            "external_effect_retry_allowed": False,
            "capability_state_mutated": False,
            "execution_authorized": False,
        }
