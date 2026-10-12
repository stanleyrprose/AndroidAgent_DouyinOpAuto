"""Rev3.7 TikTok Gateway adapter around the EXISTING Publisher.

No second publishing engine is created. Publisher's existing
before_irreversible callback is the future integration point:
Capability EFFECT_BOUNDARY_CROSSED must be durable before Publisher
COMMITTING and one Publish click. Currently no production code calls
commit_public through this adapter.

A bound publisher may never turn an uncertain COMMIT into another COMMIT;
Profile verification and DRY_RUN stay owned by the existing Publisher.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any, Mapping

from automation.capability_job_store import (
    AdmittedJob, CapabilityStoreError, _read_json, _need,
)
from automation.effect_boundary import read_effect_boundary

# Source-level migration is dormant until full Gateway+Publisher acceptance.
_TIKTOK_BUSINESS_MIGRATION_ENABLED = False


@dataclass(frozen=True)
class TikTokPublisherBinding:
    capability_job_id: str
    top_backend_job_id: str
    request_sha256: str
    effective_policy_sha256: str
    existing_publisher_job_id: str
    expected_visibility: str
    content_sha256: str


def inspect_exact_publisher_binding(
    job: AdmittedJob,
    *,
    publisher_job_id: str,
    trusted_manifest: Mapping[str, Any],
) -> TikTokPublisherBinding:
    """Existing Publisher job is the top-level backend; no duplicate job."""
    _need(isinstance(publisher_job_id, str)
          and publisher_job_id and len(publisher_job_id) < 160
          and "/" not in publisher_job_id and ".." not in publisher_job_id,
          "PUBLISHER_JOB_ID_INVALID")
    backend = _read_json(job.path / "backend.json")
    _need(backend.get("backend_type") == "publisher"
          and backend.get("capability_job_id") == job.job_id
          and backend.get("request_sha256") == job.request_sha256,
          "TOP_BACKEND_BINDING_INVALID")
    _need(
        isinstance(trusted_manifest, Mapping)
        and trusted_manifest.get("job_id") == publisher_job_id
        and trusted_manifest.get("publish_mode") in {"DRY_RUN", "COMMIT"}
        and trusted_manifest.get("visibility") == "PUBLIC",
        "PUBLISHER_MANIFEST_MISMATCH")
    content_sha = trusted_manifest.get("content_sha256")
    _need(isinstance(content_sha, str) and len(content_sha) == 64
          and all(ch in "0123456789abcdef" for ch in content_sha),
          "PUBLISHER_CONTENT_IDENTITY_UNAVAILABLE")
    # Never allocate a new top-level backend ID on a transport retry.
    _need(backend.get("backend_job_id") in {
        publisher_job_id,
        f"{job.job_id}--publisher-01",
    }, "PUBLISHER_BACKEND_IDENTITY_MISMATCH")
    return TikTokPublisherBinding(
        capability_job_id=job.job_id,
        top_backend_job_id=backend["backend_job_id"],
        request_sha256=job.request_sha256,
        effective_policy_sha256=job.effective_policy_sha256,
        existing_publisher_job_id=publisher_job_id,
        expected_visibility="PUBLIC",
        content_sha256=content_sha,
    )


def before_publisher_committing_readonly(
    job: AdmittedJob,
    binding: TikTokPublisherBinding,
    *,
    current_claim: Mapping[str, Any],
    trusted_claim_observation: Mapping[str, Any],
    publisher_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Pre-COMMIT gate; checks durable boundary and resource identity.

    This can only BLOCK; it cannot trigger the Publisher's callback, wake
    the screen, or issue a COMMIT action.
    """
    base = {
        "status": "BLOCKED",
        "phase": "BEFORE_PUBLISHER_COMMITTING",
        "production_dispatch_authorized": False,
        "publish_click_attempts": 0,
        "business_activation_enabled": False,
        "dg3_status": "OPEN",
    }
    if not _TIKTOK_BUSINESS_MIGRATION_ENABLED:
        return {**base, "reason_code": "BUSINESS_GATE_CLOSED"}
    try:
        _need(binding.capability_job_id == job.job_id
              and binding.request_sha256 == job.request_sha256
              and binding.effective_policy_sha256
                  == job.effective_policy_sha256,
              "CAPABILITY_IDENTITY_MISMATCH")
        boundary = _read_json(job.path / "effect-boundary.json")
        _need(boundary.get("phase") == "EFFECT_BOUNDARY_CROSSED",
              "EFFECT_BOUNDARY_NOT_CROSSED")
        _need(boundary.get("backend_job_id")
              == binding.top_backend_job_id
              and boundary.get("request_sha256") == binding.request_sha256
              and boundary.get("effective_policy_sha256")
                  == binding.effective_policy_sha256
              and boundary.get("content_sha256") == binding.content_sha256
              and boundary.get("visibility") == "PUBLIC",
              "EFFECT_IDENTITY_MISMATCH")
        guard = boundary.get("resource_guard")
        _need(isinstance(guard, dict)
              and isinstance(current_claim, Mapping)
              and isinstance(trusted_claim_observation, Mapping)
              and guard.get("claim_id") == current_claim.get("claim_id")
                  == trusted_claim_observation.get("claim_id")
              and guard.get("owner_id") == current_claim.get("owner_id")
                  == trusted_claim_observation.get("owner_id"),
              "STALE_RESOURCE_OWNERSHIP")
        _need(publisher_state.get("status") == "READY_TO_COMMIT"
              and publisher_state.get("job_id")
                  == binding.existing_publisher_job_id,
              "PUBLISHER_PRECOMMIT_STATE_INVALID")
        # The native Android Driver JIT remains independently closed;
        # even a matched boundary does not grant Publisher COMMIT.
        return {**base, "reason_code": "DRIVER_JIT_NOT_ACCEPTED",
                "effect_boundary_verified_readonly": True}
    except CapabilityStoreError as exc:
        return {**base, "reason_code": exc.code}




def persist_exact_gateway_publisher_binding(
    job: AdmittedJob,
    *,
    publisher_job_path: Path,
    expected_publisher_job_id: str,
    current_claim: Mapping[str, Any],
    trusted_authorization_verified: bool,
) -> dict[str, Any]:
    """Write-once binding to existing Publisher READY job, before submit.

    Caller has already authenticated the immutable Capability request and
    owns the exact canonical android_ui claim. This is infrastructure
    only: it neither submits nor starts a Publisher process. Binding
    existence MUST NOT be interpreted as effect approval.
    """
    from automation import resource_arbiter
    from automation.capability_job_store import _atomic_new, _locked
    from publisher.job_contract import load_manifest
    from automation.publisher_boundary_guard import _hash_file

    _need(trusted_authorization_verified is True,
          "GATEWAY_BIND_AUTHORITY_UNVERIFIED")
    _need(isinstance(publisher_job_path, Path)
          and publisher_job_path.parent == Path("/opt/y700/media/ready")
          and publisher_job_path.name == expected_publisher_job_id
          and not publisher_job_path.is_symlink()
          and publisher_job_path.is_dir(),
          "PUBLISHER_READY_PATH_UNTRUSTED")
    _need(isinstance(expected_publisher_job_id, str)
          and bool(re.fullmatch(r"[A-Za-z0-9_.-]{1,96}",
                                expected_publisher_job_id)),
          "PUBLISHER_JOB_ID_INVALID")
    _need(isinstance(current_claim, Mapping),
          "RESOURCE_GUARD_INVALID")
    from publisher.job_contract import load_manifest
    manifest = load_manifest(publisher_job_path / "manifest.json")
    manifest_sha = _hash_file(publisher_job_path / "manifest.json")
    _need(manifest["job_id"] == expected_publisher_job_id
          and manifest["publish_mode"] in {"DRY_RUN", "COMMIT"}
          and manifest.get("visibility", "PUBLIC") == "PUBLIC",
          "PUBLISHER_MANIFEST_MISMATCH")
    media_name = manifest["video_file"]
    media_hash = manifest["sha256"].get(media_name)
    caption_hash = manifest["sha256"].get(manifest["caption_file"])
    _need(isinstance(media_hash, str)
          and re.fullmatch(r"[0-9a-fA-F]{64}", media_hash) is not None
          and isinstance(caption_hash, str)
          and re.fullmatch(r"[0-9a-fA-F]{64}", caption_hash) is not None,
          "PUBLISHER_CONTENT_IDENTITY_UNAVAILABLE")
    request = _read_json(job.path / "request.json")
    payload = request.get("payload")
    _need(isinstance(payload, dict)
          and payload.get("existing_publisher_job_id")
              == expected_publisher_job_id
          and payload.get("content_sha256") == media_hash.lower()
          and payload.get("caption_sha256") == caption_hash.lower()
          and payload.get("publish_mode") == manifest["publish_mode"]
          and payload.get("visibility") == "PUBLIC",
          "IMMUTABLE_PUBLISHER_PAYLOAD_MISMATCH")

    with _locked(job.path / "transition.lock"):
        state = _read_json(job.path / "state.json")
        backend = _read_json(job.path / "backend.json")
        _need(not state.get("terminal")
              and state.get("effect_uncertain") is False
              and state.get("mutation_uncertain") is False
              and not (job.path / "effect-boundary.json").exists()
              and not (job.path / "cancel.json").exists(),
              "JOB_STATE_NOT_BINDABLE")
        _need(backend.get("backend_type") == "publisher"
              and backend.get("capability_job_id") == job.job_id
              and backend.get("request_sha256") == job.request_sha256,
              "BACKEND_BINDING_MISMATCH")
        try:
            owned = resource_arbiter.assert_guard(dict(current_claim))
        except resource_arbiter.ResourceError as exc:
            raise CapabilityStoreError("STALE_RESOURCE_OWNERSHIP") from exc
        _need(owned.get("owner_kind") == "CAPABILITY"
              and owned.get("capability_job_id") == job.job_id
              and owned.get("backend_job_id") == backend["backend_job_id"]
              and owned.get("request_sha256") == job.request_sha256,
              "CAPABILITY_RESOURCE_IDENTITY_MISMATCH")
        persisted = {
            "binding_version": 1,
            "capability_job_id": job.job_id,
            "backend_job_id": backend["backend_job_id"],
            "publisher_job_id": expected_publisher_job_id,
            "request_sha256": job.request_sha256,
            "effective_policy_sha256": job.effective_policy_sha256,
            "content_sha256": media_hash.lower(),
            "caption_sha256": caption_hash.lower(),
            "manifest_sha256": manifest_sha,
            "publish_mode": manifest["publish_mode"],
            "visibility": "PUBLIC",
            "claim_id": owned["claim_id"],
            "owner_id": owned["owner_id"],
        }
        path = publisher_job_path / "gateway-binding.json"
        if path.exists() or path.is_symlink():
            original = _read_json(path)
            _need(original == persisted, "GATEWAY_BINDING_IMMUTABLE")
            return original
        _atomic_new(path, persisted)
        return persisted


def classify_publisher_outcome_readonly(
    job: AdmittedJob, publisher_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Neither old Publisher nor Gateway can retry uncertain COMMIT."""
    recorded = read_effect_boundary(job)
    status = publisher_state.get("status")
    if status in {"COMMITTING", "AMBIGUOUS_COMMIT_NEEDS_RECONCILE"} or (
        recorded.get("requires_reconcile") is True
    ):
        result = "RECONCILE_REQUIRED"
    elif status == "PUBLISHED" and recorded.get("phase") == "EFFECT_OUTCOME_VERIFIED":
        result = "SUCCEEDED"
    elif status == "READY_TO_COMMIT":
        result = "DRY_RUN_READY_ONLY"
    else:
        result = "OUTCOME_UNKNOWN"
    return {
        "status": result,
        "production_dispatch_authorized": False,
        "publisher_restart_allowed": False,
        "commit_retry_allowed": False,
        "requires_profile_verification": result != "DRY_RUN_READY_ONLY",
        "publish_click_attempts": 0,
    }
