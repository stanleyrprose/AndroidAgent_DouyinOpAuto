"""Rev3.7 local exact Publisher backend adapter (source-dormant).

Adapter is a thin, synchronous wrapper of the EXISTING Publisher; it never
creates a second publishing engine. The top-level ForegroundCoordinator
owns policy, resource claim, TTL, status and outcome. No daemon, async
task, or fallback to a different backend ID.

All execution functions are statically disabled in the development batch.
Read-only exact lookup resolves ONLY the current deterministic backend.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping
import re

from automation.capability_job_store import (
    AdmittedJob, CapabilityStore, CapabilityStoreError,
    _locked, _need, _read_json, _sha,
)
from automation.tiktok_gateway_adapter import (
    persist_exact_gateway_publisher_binding,
)
from publisher.gateway_execution import execute_gateway_bound
from publisher.job_contract import load_manifest

_BACKEND_ID = re.compile(r"^(cap-[0-9a-f]{48})--publisher-01$")
_PUBLISHER_PATH = Path("/opt/y700/media/ready")
_LOCAL_PUBLISHER_SUBMISSION_ACCEPTED = False


def _identity(backend_id: str) -> str:
    if not isinstance(backend_id, str):
        raise CapabilityStoreError("BACKEND_IDENTITY_INVALID")
    match = _BACKEND_ID.fullmatch(backend_id)
    if match is None:
        raise CapabilityStoreError("BACKEND_IDENTITY_INVALID")
    return match.group(1)


class LocalPublisherBackend:
    """Exact-ID adapter; the only effect-producing code is Existing Publisher."""

    def __init__(self, *,
                 store: CapabilityStore | None = None,
                 trusted_effect_callback: Callable[
                     [], Mapping[str, Any]] | None = None,
                 trusted_binding_authority: Callable[
                     [str, str, Mapping[str, Any]], bool] | None = None):
        self.store = store or CapabilityStore()
        # This callback is injected by a trusted in-process Gateway wiring,
        # never from job JSON, CLI flags or a model-generated request.
        self.trusted_effect_callback = trusted_effect_callback
        self.trusted_binding_authority = trusted_binding_authority

    def _load_admitted(self, backend_id: str) -> AdmittedJob:
        job_id = _identity(backend_id)
        path = self.store.jobs / "active" / job_id
        _need(path.is_dir() and not path.is_symlink(),
              "CAPABILITY_JOB_UNAVAILABLE")
        ident = _read_json(path / "identity.json")
        backend = _read_json(path / "backend.json")
        _need(ident.get("capability_job_id") == job_id
              and backend.get("capability_job_id") == job_id
              and backend.get("backend_job_id") == backend_id
              and backend.get("backend_type") == "publisher"
              and backend.get("request_sha256")
                  == ident.get("request_sha256"),
              "BACKEND_IDENTITY_MISMATCH")
        return AdmittedJob(
            job_id, path, ident["request_sha256"],
            ident["effective_policy_sha256"], False,
        )

    def lookup_exact(
        self, backend_type: str, backend_id: str,
    ) -> dict[str, Any]:
        """Never mark unknown or crashed submission as never-created."""
        if backend_type != "publisher":
            raise CapabilityStoreError("BACKEND_TYPE_MISMATCH")
        admitted = self._load_admitted(backend_id)
        with _locked(admitted.path / "transition.lock", shared=True):
            witness = _read_json(admitted.path / "backend-execution.json")
            state = _read_json(admitted.path / "state.json")
            _need(witness.get("backend_job_id") == backend_id
                  and witness.get("request_sha256")
                      == admitted.request_sha256,
                  "BACKEND_WITNESS_MISMATCH")
            untouched = (
                witness.get("phase") == "NEVER_CREATED"
                and witness.get("submission_possible") is False
                and witness.get("attempt_serial") == 0
                and state.get("backend_submitted") is False
                and state.get("mutation_uncertain") is False
                and not (admitted.path / "effect-boundary.json").exists()
                and not (admitted.path / "result.json").exists()
            )
            return {
                "lookup_complete": True,
                "exists": not untouched,
                "durable_never_created_proof": bool(untouched),
                "backend_job_id": backend_id,
                "request_sha256": admitted.request_sha256,
                "state": "NEVER_CREATED" if untouched else "UNKNOWN",
                "backend_submission_possible":
                    witness.get("submission_possible") is True,
                "execution_performed_by_lookup": False,
                "external_effect_retry_allowed": False,
            }

    def _binding_authority(self, admitted: AdmittedJob,
                           backend_id: str,
                           intent: Mapping[str, Any]) -> bool:
        """Protected same-job identity/Claim and approval; no caller flag."""
        from automation import resource_arbiter
        guard = intent.get("resource_guard")
        _need(isinstance(guard, Mapping), "RESOURCE_GUARD_REQUIRED")
        try:
            claim = resource_arbiter.assert_guard(dict(guard))
        except resource_arbiter.ResourceError as exc:
            raise CapabilityStoreError("STALE_RESOURCE_OWNERSHIP") from exc
        _need(claim.get("owner_kind") == "CAPABILITY"
              and claim.get("capability_job_id") == admitted.job_id
              and claim.get("backend_job_id") == backend_id
              and claim.get("request_sha256") == admitted.request_sha256,
              "RESOURCE_CLAIM_IDENTITY_MISMATCH")
        request = _read_json(admitted.path / "request.json")
        policy = _read_json(admitted.path / "effective_policy.json")
        _need(_sha(request) == admitted.request_sha256
              and _sha(policy) == admitted.effective_policy_sha256,
              "PUBLISHER_IMMUTABLE_IDENTITY_MISMATCH")
        payload = request.get("payload")
        _need(isinstance(payload, dict), "PUBLISHER_PAYLOAD_INVALID")
        if payload.get("publish_mode") == "COMMIT":
            from automation.trusted_ingress_approval import (
                inspect_trusted_one_url_authorization,
            )
            from automation.runtime_authority import LocalRootRuntimeAuthority
            from automation.runtime_evidence_producer import (
                publish_post_admission_readonly,
            )
            # No stale pre-wait readiness receipt can authorize a binding.
            publish_post_admission_readonly(
                capability_job_id=admitted.job_id,
                backend_job_id=backend_id,
            )
            facts = LocalRootRuntimeAuthority(
                jobs_root=self.store.jobs).observe_fresh(
                    admitted.job_id, backend_id)
            _need(facts.get("identity_facts", {}).get("clock_health")
                  == "HEALTHY", "TRUSTED_CLOCK_UNAVAILABLE")
            expected = inspect_trusted_one_url_authorization(
                admitted, current_clock_health="HEALTHY")
            written = _read_json(admitted.path / "approval.json")
            _need(all(written.get(key) == expected.get(key)
                      for key in (
                          "approval_id", "job_id", "request_sha256",
                          "effective_policy_sha256", "content_sha256",
                          "caption_sha256", "visibility", "approval_nonce",
                          "single_use")),
                  "PUBLISHER_APPROVAL_NOT_DURABLE")
        else:
            _need(payload.get("publish_mode") == "DRY_RUN"
                  and not (admitted.path / "effect-boundary.json").exists(),
                  "PUBLISHER_MODE_UNTRUSTED")
        return True

    def prepare_exact(
        self, backend_type: str, backend_id: str,
        intent: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Persist exact Publisher identity before backend submission."""
        if backend_type != "publisher":
            raise CapabilityStoreError("BACKEND_TYPE_MISMATCH")
        admitted = self._load_admitted(backend_id)
        _need(isinstance(intent, Mapping)
              and intent.get("backend_job_id") == backend_id
              and intent.get("request_sha256") == admitted.request_sha256
              and intent.get("effective_policy_sha256")
                  == admitted.effective_policy_sha256,
              "BACKEND_INTENT_IDENTITY_MISMATCH")
        adapter = intent.get("adapter_intent")
        _need(isinstance(adapter, Mapping)
              and adapter.get("capability") == "tiktok.publish"
              and adapter.get("backend_type") == "publisher"
              and adapter.get("request_sha256") == admitted.request_sha256
              and adapter.get("backend_job_id") == backend_id,
              "BACKEND_ADAPTER_CONTRACT_INVALID")
        payload = adapter.get("payload")
        _need(isinstance(payload, Mapping),
              "BACKEND_PAYLOAD_UNAVAILABLE")
        publisher_id = payload.get("existing_publisher_job_id")
        _need(isinstance(publisher_id, str)
              and bool(re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", publisher_id)),
              "PUBLISHER_JOB_ID_INVALID")
        publisher_job = _PUBLISHER_PATH / publisher_id
        _need(publisher_job.parent == _PUBLISHER_PATH,
              "PUBLISHER_READY_PATH_UNTRUSTED")
        manifest = load_manifest(publisher_job / "manifest.json")
        media_name = manifest["video_file"]
        _need(manifest["job_id"] == publisher_id
              and manifest["publish_mode"] == payload.get("publish_mode")
              and manifest.get("visibility", "PUBLIC") == "PUBLIC"
              and manifest["sha256"][media_name].lower()
                  == payload.get("content_sha256")
              and manifest["sha256"][manifest["caption_file"]].lower()
                  == payload.get("caption_sha256"),
              "PUBLISHER_CONTENT_IDENTITY_MISMATCH")
        claim = intent.get("resource_guard")
        _need(isinstance(claim, Mapping), "RESOURCE_OWNERSHIP_REQUIRED")
        # Authenticate against durable source-owned job/approval/claim, not
        # an injected positive boolean. External callbacks may RESTRICT
        # this check but cannot substitute for it.
        authority_ok = self._binding_authority(
            admitted, backend_id, intent)
        if self.trusted_binding_authority is not None:
            try:
                additional = self.trusted_binding_authority(
                    admitted.job_id, backend_id, intent)
            except Exception as exc:
                raise CapabilityStoreError(
                    "TRUSTED_BINDING_AUTHORITY_UNAVAILABLE") from exc
            _need(additional is True, "TRUSTED_BINDING_AUTHORITY_DENIED")
        _need(authority_ok is True, "TRUSTED_BINDING_AUTHORITY_DENIED")
        persisted = persist_exact_gateway_publisher_binding(
            admitted,
            publisher_job_path=publisher_job,
            expected_publisher_job_id=publisher_id,
            current_claim=claim,
            trusted_authorization_verified=authority_ok,
        )
        return {
            "prepared": True,
            "backend_job_id": backend_id,
            "request_sha256": admitted.request_sha256,
            "publisher_job_id": publisher_id,
            "binding_content_sha256": persisted["content_sha256"],
            "external_effect_attempts": 0,
        }

    def submit_exact(
        self, backend_type: str, backend_id: str,
        intent: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Potentially executes the EXISTING Publisher, but currently CLOSED."""
        if not _LOCAL_PUBLISHER_SUBMISSION_ACCEPTED:
            raise CapabilityStoreError("PUBLISHER_BACKEND_RELEASE_GATE_CLOSED")
        if backend_type != "publisher":
            raise CapabilityStoreError("BACKEND_TYPE_MISMATCH")
        admitted = self._load_admitted(backend_id)
        _need(isinstance(intent, Mapping)
              and intent.get("backend_job_id") == backend_id
              and intent.get("capability_job_id") == admitted.job_id
              and intent.get("request_sha256") == admitted.request_sha256
              and intent.get("effective_policy_sha256")
                  == admitted.effective_policy_sha256,
              "BACKEND_INTENT_IDENTITY_MISMATCH")
        adapter = intent.get("adapter_intent")
        _need(isinstance(adapter, Mapping)
              and adapter.get("backend_type") == "publisher"
              and adapter.get("capability") == "tiktok.publish"
              and adapter.get("backend_job_id") == backend_id
              and adapter.get("request_sha256") == admitted.request_sha256,
              "BACKEND_ADAPTER_CONTRACT_INVALID")
        witness = _read_json(admitted.path / "backend-execution.json")
        _need(witness.get("phase") == "SUBMISSION_POSSIBLE"
              and witness.get("attempt_serial") == 1
              and witness.get("submission_possible") is True
              and witness.get("backend_job_id") == backend_id
              and witness.get("capability_job_id") == admitted.job_id
              and witness.get("request_sha256") == admitted.request_sha256
              and not (admitted.path / "effect-boundary.json").exists()
              and not (admitted.path / "result.json").exists(),
              "BACKEND_SUBMISSION_WITNESS_MISSING")
        prepared = _read_json(admitted.path / "request.json")
        payload = prepared.get("payload")
        _need(isinstance(payload, dict)
              and payload.get("existing_publisher_job_id"),
              "PUBLISHER_JOB_ID_INVALID")
        publisher_id = payload["existing_publisher_job_id"]
        from automation.gateway_adapters import (
            prepare_adapter_intent_readonly,
        )
        expected_adapter = prepare_adapter_intent_readonly(
            capability="tiktok.publish",
            immutable_payload=payload,
            exact_backend_id=backend_id,
            exact_request_sha256=admitted.request_sha256,
        )
        _need(isinstance(publisher_id, str)
              and re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", publisher_id)
              is not None
              and dict(adapter) == expected_adapter,
              "PUBLISHER_SUBMISSION_PAYLOAD_DRIFT")
        path = _PUBLISHER_PATH / publisher_id
        _need(path.parent == _PUBLISHER_PATH and path.is_dir()
              and not path.is_symlink(),
              "PUBLISHER_JOB_UNAVAILABLE")
        manifest = load_manifest(path / "manifest.json")
        from automation.publisher_boundary_guard import read_gateway_binding
        bound = read_gateway_binding(path, manifest)
        _need(isinstance(bound, dict)
              and bound.get("backend_job_id") == backend_id
              and bound.get("request_sha256") == admitted.request_sha256,
              "GATEWAY_BINDING_IDENTITY_MISMATCH")
        # The in-process Publisher is now positively entered under its
        # exact deterministic Backend ID. Persist accepted submission
        # before any TikTok UI preparation can cross an external boundary.
        # A previous SUBMISSION_POSSIBLE crash remains reconcile-only.
        self.store.record_backend_submission(
            admitted,
            exact_backend_job_id=backend_id,
            backend_identity_confirmed=True,
        )
        # The publisher-scoped executor re-checks exact durable Claim.
        # An uncertain exception is propagated to coordinator's reconcile
        # path, never retried under another Backend ID.
        effect_callback = None
        if manifest.get("publish_mode") == "COMMIT":
            from automation.publisher_effect_authority import (
                build_exact_effect_callback,
            )
            exact_guard = intent.get("resource_guard")
            _need(isinstance(exact_guard, Mapping),
                  "RESOURCE_GUARD_REQUIRED")
            effect_callback = build_exact_effect_callback(
                admitted,
                backend_job_id=backend_id,
                exact_guard=exact_guard,
            )
        # External injected callbacks cannot replace the canonical
        # immutable effect authority; only the source-built callback can
        # cross the durable boundary for a BUSINESS COMMIT.
        outcome = execute_gateway_bound(
            publisher_job=path,
            manifest=manifest,
            binding=bound,
            trusted_runtime_context=bound,
            trusted_effect_callback=effect_callback,
        )
        # No detached backend is spawned: existing controller's UI Core
        # sub-jobs run synchronously. Still require a current exact claim
        # with no active subordinate binding before declaring quiescence.
        from automation import resource_arbiter
        from automation.native_stop_receipt_producer import (
            NativeStopReceiptUnavailable,
            publish_generation_bound_stop_receipt,
        )
        exact_guard = intent.get("resource_guard")
        stopped = False
        if isinstance(exact_guard, Mapping) and isinstance(outcome, Mapping):
            # The acceptance-gated foreground producer independently
            # samples the native Driver, Bridge and all Core subjobs for
            # the latest durable UI execution generation. Producer refusal
            # NEVER becomes an implicit positive stop receipt.
            try:
                publish_generation_bound_stop_receipt(
                    exact_claim=exact_guard, backend_job_id=backend_id)
            except (NativeStopReceiptUnavailable,
                    resource_arbiter.ResourceError,
                    CapabilityStoreError):
                pass
            try:
                current = resource_arbiter.assert_guard(dict(exact_guard))
                from automation.resource_stop_observer import (
                    positive_synchronous_ui_quiescence,
                )
                # A synchronously returned Publisher function and empty
                # "active_*" fields do NOT independently prove all native
                # and UI Core descendants have stopped. A fresh accepted
                # exact-Claim native receipt is mandatory before release.
                stopped = (
                    current.get("active_ui_job_id") is None
                    and current.get("active_session_id") is None
                    and not current.get("reconcile_required")
                    and outcome.get("status") in {
                        "DRY_RUN_READY_ONLY", "PROFILE_VERIFIED",
                    }
                    and (
                        outcome.get("status") != "PROFILE_VERIFIED"
                        or (
                            isinstance(outcome.get("verification"), Mapping)
                            and outcome["verification"].get("verified") is True
                        )
                    )
                    and positive_synchronous_ui_quiescence(
                        exact_guard, backend_job_id=backend_id)
                )
            except resource_arbiter.ResourceError:
                stopped = False
        if manifest.get("publish_mode") == "DRY_RUN":
            # DRY_RUN is a separately proven local preview, NEVER a public
            # post. It must reach POST_CONFIG, emit evidence, and positively
            # clean up the foreground before durable verification exists.
            preview = outcome.get("result") if isinstance(outcome, Mapping) else None
            _need(isinstance(preview, Mapping)
                  and outcome.get("status") == "DRY_RUN_READY_ONLY"
                  and outcome.get("ui_cleanup_complete") is True
                  and outcome.get("external_effect_attempts") == 0
                  and isinstance(preview.get("ui_state"), Mapping)
                  and preview["ui_state"].get("state") == "POST_CONFIG"
                  and preview.get("caption_verified") is True
                  and preview.get("visibility") == "PUBLIC"
                  and isinstance(preview.get("workflow_job_id"), str)
                  and bool(preview["workflow_job_id"])
                  and stopped is True
                  and not (admitted.path / "effect-boundary.json").exists(),
                  "PUBLISHER_DRY_RUN_COMPLETION_UNVERIFIED")
            from automation.capability_job_store import _atomic_new, _locked
            with _locked(admitted.path / "transition.lock"):
                _need(not (admitted.path / "result.json").exists()
                      and not (admitted.path / "effect-boundary.json").exists(),
                      "PUBLISHER_DRY_RUN_TERMINAL_CONFLICT")
                _atomic_new(
                    admitted.path / "publisher-dryrun-result.json",
                    {
                        "publisher_dryrun_result_version": 1,
                        "capability_job_id": admitted.job_id,
                        "backend_job_id": backend_id,
                        "publisher_job_id": publisher_id,
                        "request_sha256": admitted.request_sha256,
                        "content_sha256": bound["content_sha256"],
                        "caption_sha256": bound["caption_sha256"],
                        "preview_state": "POST_CONFIG",
                        "caption_verified": True,
                        "visibility": "PUBLIC",
                        "workflow_job_id": preview["workflow_job_id"],
                        "ui_cleanup_complete": True,
                        "external_effect_attempts": 0,
                        "external_effect_retry_allowed": False,
                    },
                )
        return {
            "accepted": True,
            "backend_job_id": backend_id,
            "request_sha256": admitted.request_sha256,
            "publisher_outcome": outcome,
            "ui_mutators_quiesced_positive": stopped,
            "external_effect_retry_allowed": False,
        }
