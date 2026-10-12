"""Rev3.7 exact irreversible TikTok effect authority adapter.

This is the sole bridge from authenticated Publisher callback to the
Capability effect-boundary SOT. The callback is internally constructed from
the exact admitted Job and existing canonical UI claim; it cannot be chosen
by a user request or generated workflow.

Before the durable boundary it requires: exact accepted native production
Driver dispatch-time witness, app contract, immutable content, one-url
single-use approval, current boot/epoch/revision and ownership. A file or
caller "jit_verified=true" cannot open the independent native gate.

Whole PRD developer source only; native observer, signing and D-G3 acceptance
are currently FALSE and this module never dispatches a TikTok UI input.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Callable
import re

from automation import resource_arbiter
from automation.capability_job_store import (
    AdmittedJob, CapabilityStoreError, _read_json, _need, _sha,
)
from automation.authoritative_state_reader import (
    observe_authoritative_state,
)
from automation.effect_boundary import cross_effect_boundary
from automation.runtime_authority import LocalRootRuntimeAuthority
from automation.publisher_boundary_guard import _strict_json
from automation.trusted_ingress_approval import (
    inspect_trusted_one_url_authorization,
)

_NATIVE_EFFECT_PRODUCER_ACCEPTED = False
_TIKTOK_FINAL_EFFECT_DISPATCH_ACCEPTED = False
_NATIVE_RECEIPT_ROOT = Path("/opt/y700/runtime/native-effect-receipts")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def build_exact_effect_callback(
    admitted: AdmittedJob, *,
    backend_job_id: str,
    exact_guard: Mapping[str, Any],
) -> Callable[[], dict[str, Any]]:
    """Construct from protected durable identity; no injected proof values."""
    _need(isinstance(exact_guard, Mapping),
          "RESOURCE_GUARD_INVALID")
    frozen_guard = {
        "resource": exact_guard.get("resource"),
        "claim_id": exact_guard.get("claim_id"),
        "owner_id": exact_guard.get("owner_id"),
    }
    def callback() -> dict[str, Any]:
        _need(_NATIVE_EFFECT_PRODUCER_ACCEPTED
              and _TIKTOK_FINAL_EFFECT_DISPATCH_ACCEPTED,
              "NATIVE_EFFECT_AUTHORITY_NOT_ACCEPTED")
        current_claim = resource_arbiter.assert_guard(frozen_guard)
        _need(current_claim.get("owner_kind") == "CAPABILITY"
              and current_claim.get("capability_job_id") == admitted.job_id
              and current_claim.get("backend_job_id") == backend_job_id
              and current_claim.get("request_sha256")
                  == admitted.request_sha256,
              "RESOURCE_CLAIM_IDENTITY_MISMATCH")
        policy = _read_json(admitted.path / "effective_policy.json")
        request = _read_json(admitted.path / "request.json")
        _need(_sha(request) == admitted.request_sha256
              and _sha(policy) == admitted.effective_policy_sha256,
              "EFFECT_IMMUTABLE_IDENTITY_MISMATCH")
        payload = request.get("payload")
        _need(isinstance(payload, dict)
              and request.get("capability") == "tiktok.publish"
              and payload.get("publish_mode") == "COMMIT"
              and payload.get("visibility") == "PUBLIC"
              and backend_job_id == f"{admitted.job_id}--publisher-01",
              "EFFECT_PUBLISH_MODE_INVALID")
        current = observe_authoritative_state()
        from automation.runtime_evidence_producer import (
            publish_post_admission_readonly,
        )
        # Pre-submit/prepare-stage facts are never replay permission.
        # Re-sample privileged identity and SOT at this exact precommit
        # boundary, immediately before consuming the single-use approval.
        publish_post_admission_readonly(
            capability_job_id=admitted.job_id,
            backend_job_id=backend_job_id,
        )
        authority = LocalRootRuntimeAuthority().observe_fresh(
            admitted.job_id, backend_job_id)
        _need(authority.get("boot_id") == current.boot_id
              and authority.get("state_epoch") == current.state_epoch
              and authority.get("revision") == current.revision
              and authority.get("identity_facts", {}).get("clock_health")
                  == "HEALTHY",
              "EFFECT_AUTHORITY_STALE")
        approval = inspect_trusted_one_url_authorization(
            admitted, current_clock_health="HEALTHY")
        durable_approval = _read_json(admitted.path / "approval.json")
        _need(durable_approval.get("approval_id")
              == approval.get("approval_id")
              and durable_approval.get("approval_nonce")
                  == approval.get("approval_nonce")
              and durable_approval.get("request_sha256")
                  == admitted.request_sha256
              and durable_approval.get("effective_policy_sha256")
                  == admitted.effective_policy_sha256
              and durable_approval.get("content_sha256")
                  == payload.get("content_sha256")
              and durable_approval.get("caption_sha256")
                  == payload.get("caption_sha256")
              and durable_approval.get("visibility") == "PUBLIC",
              "EFFECT_APPROVAL_MISMATCH")
        # Driver-issued receipts remain separately accepted at the
        # action-time native boundary. Root-owned JSON alone cannot
        # authorize input; check required provenance contract below.
        witness = _strict_json(
            _NATIVE_RECEIPT_ROOT / (admitted.job_id + ".json"))
        _need(witness.get("native_effect_receipt_version") == 1
              and witness.get("issuer") == "Y700_NATIVE_DRIVER_DISPATCH"
              and witness.get("capability_job_id") == admitted.job_id
              and witness.get("backend_job_id") == backend_job_id
              and witness.get("request_sha256") == admitted.request_sha256
              and witness.get("state_epoch") == current.state_epoch
              and witness.get("observed_boot_id") == current.boot_id
              and witness.get("revision") == current.revision
              and witness.get("claim_id") == frozen_guard["claim_id"]
              and witness.get("owner_id") == frozen_guard["owner_id"]
              and witness.get("route_class") == "SEMANTIC_UI"
              and witness.get("native_driver_proof_validated") is True
              and witness.get("app_ui_contract_accepted") is True
              and type(witness.get("observed_boottime_ms")) is int
              and 0 <= (
                  current.observed_boottime_ms
                  - witness["observed_boottime_ms"]) <= 250,
              "NATIVE_EFFECT_WITNESS_UNAVAILABLE")
        _need(witness.get("app_ui_contract_version")
              == payload.get("app_ui_contract_version")
              and witness.get("content_sha256")
                  == payload.get("content_sha256")
              and witness.get("caption_sha256")
                  == payload.get("caption_sha256")
              and isinstance(witness.get("state_hash"), str)
              and _SHA.fullmatch(witness["state_hash"]) is not None,
              "NATIVE_EFFECT_CONTENT_OR_STATE_DRIFT")
        effect = {
            "content_sha256": payload["content_sha256"],
            "visibility": "PUBLIC",
            "approval_id": approval["approval_id"],
            "observed_boot_id": current.boot_id,
            "state_epoch": current.state_epoch,
            "revision": current.revision,
            "fingerprint_version": "semantic-v1",
            "fingerprint_profile_id": "tiktok.publish-control.v1",
            "state_hash": witness["state_hash"],
            "app_ui_contract_version": witness["app_ui_contract_version"],
            "app_version_code": witness.get("app_version_code"),
            "app_signing_cert_sha256":
                witness.get("app_signing_cert_sha256"),
        }
        return cross_effect_boundary(
            admitted, trusted_effect=effect,
            approval_authority_verified=True,
            state_jit_verified=True,
            current_resource_guard=frozen_guard,
        )
    return callback
