"""Rev3.7 archive-only Publisher recovery after positive Profile receipt.

After a crash between durable publish-result.json and ready/ -> published/
rename, recover the original archive namespace WITHOUT executing TikTok,
creating a new Backend, or resubmitting the external effect.

Source-gated until the native mutator-stop observer and versioned Publisher
recovery invariants are finally accepted. This performs no work on import.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any

from automation.capability_job_store import (
    CAP_JOBS, _locked, _read_json, _need,
)
from automation.publisher_boundary_guard import (
    _hash_file, _strict_json, PublisherBoundaryError,
)
from automation.authoritative_state_reader import observe_authoritative_state
from automation import resource_stop_observer, resource_arbiter
from publisher.job_contract import validate_manifest, ContractError

_READY = Path("/opt/y700/media/ready")
_PUBLISHED = Path("/opt/y700/media/published")
_JOB_ID = re.compile(r"^cap-[0-9a-f]{48}$")
_PUBLISH_ID = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
_ARCHIVE_REPAIR_ACCEPTED = False


def archive_verified_publisher_after_acceptance(
    capability_job_id: str,
) -> dict[str, Any]:
    """Repair ONLY namespace, never launch a new publishing attempt."""
    _need(_ARCHIVE_REPAIR_ACCEPTED
          and resource_stop_observer._NATIVE_MUTATOR_ABSENCE_ACCEPTED,
          "PUBLISHER_ARCHIVE_REPAIR_RELEASE_GATE_CLOSED")
    _need(isinstance(capability_job_id, str)
          and _JOB_ID.fullmatch(capability_job_id) is not None,
          "CAPABILITY_JOB_ID_INVALID")
    active = CAP_JOBS / "active" / capability_job_id
    _need(active.is_dir() and not active.is_symlink(),
          "ARCHIVE_REPAIR_CAPABILITY_JOB_UNAVAILABLE")
    with _locked(active / "transition.lock"):
        identity = _read_json(active / "identity.json")
        request = _read_json(active / "request.json")
        backend = _read_json(active / "backend.json")
        state = _read_json(active / "state.json")
        payload = request.get("payload")
        _need(isinstance(payload, dict)
              and payload.get("publish_mode") == "COMMIT"
              and payload.get("visibility") == "PUBLIC"
              and identity.get("capability_job_id") == capability_job_id
              and backend.get("capability_job_id") == capability_job_id
              and backend.get("backend_type") == "publisher"
              and backend.get("request_sha256")
                  == identity.get("request_sha256")
              and state.get("capability_job_id") == capability_job_id
              and state.get("backend_submitted") is True,
              "ARCHIVE_REPAIR_IMMUTABLE_IDENTITY_MISMATCH")
        publisher_id = payload.get("existing_publisher_job_id")
        _need(isinstance(publisher_id, str)
              and _PUBLISH_ID.fullmatch(publisher_id) is not None,
              "ARCHIVE_REPAIR_PUBLISHER_ID_INVALID")
        source = _READY / publisher_id
        target = _PUBLISHED / publisher_id
        _need(source.parent == _READY and source.is_dir()
              and not source.is_symlink()
              and target.parent == _PUBLISHED
              and not target.exists() and not target.is_symlink()
              and _PUBLISHED.is_dir() and not _PUBLISHED.is_symlink(),
              "ARCHIVE_REPAIR_DIRECTORY_CONFLICT")

        manifest = _strict_json(source / "manifest.json")
        validate_manifest(manifest)
        _need(manifest.get("job_id") == publisher_id
              and manifest.get("publish_mode") == "COMMIT"
              and manifest.get("visibility", "PUBLIC") == "PUBLIC",
              "ARCHIVE_REPAIR_MANIFEST_MISMATCH")
        video_name = manifest.get("video_file")
        caption_name = manifest.get("caption_file")
        _need(isinstance(video_name, str)
              and isinstance(caption_name, str),
              "ARCHIVE_REPAIR_MEDIA_INVALID")
        sha = manifest.get("sha256")
        _need(isinstance(sha, dict), "ARCHIVE_REPAIR_MANIFEST_MISMATCH")
        _need(_hash_file(source / video_name)
                  == payload.get("content_sha256")
                  == str(sha.get(video_name, "")).lower()
              and _hash_file(source / caption_name)
                  == payload.get("caption_sha256")
                  == str(sha.get(caption_name, "")).lower(),
              "ARCHIVE_REPAIR_CONTENT_DRIFT")

        binding = _strict_json(source / "gateway-binding.json")
        receipt = _strict_json(source / "publish-result.json")
        backend_id = backend["backend_job_id"]
        _need(binding.get("binding_version") == 1
              and binding.get("capability_job_id") == capability_job_id
              and binding.get("backend_job_id") == backend_id
              and binding.get("publisher_job_id") == publisher_id
              and binding.get("request_sha256")
                  == identity["request_sha256"]
              and binding.get("content_sha256")
                  == payload["content_sha256"]
              and binding.get("caption_sha256")
                  == payload["caption_sha256"]
              and binding.get("publish_mode") == "COMMIT"
              and binding.get("manifest_sha256")
                  == _hash_file(source / "manifest.json"),
              "ARCHIVE_REPAIR_GATEWAY_BINDING_MISMATCH")
        _need(receipt.get("status") == "PUBLISHED"
              and receipt.get("job_id") == publisher_id
              and receipt.get("capability_job_id") == capability_job_id
              and receipt.get("backend_job_id") == backend_id
              and receipt.get("request_sha256")
                  == identity["request_sha256"]
              and receipt.get("content_sha256")
                  == payload["content_sha256"]
              and receipt.get("caption_sha256")
                  == payload["caption_sha256"]
              and receipt.get("visibility") == "PUBLIC"
              and isinstance(receipt.get("verification"), dict)
              and receipt["verification"].get("verified") is True,
              "ARCHIVE_REPAIR_PROFILE_NOT_VERIFIED")

        # The original Publisher and every subordinate UI mutator must be
        # proven terminated; a healthy receipt alone does NOT authorize
        # moving a directory while a writer may still be alive.
        now = observe_authoritative_state()
        claim_id = binding.get("claim_id")
        _need(isinstance(claim_id, str)
              and re.fullmatch(r"ui-claim-[0-9a-f]{32}", claim_id) is not None,
              "ARCHIVE_REPAIR_CLAIM_INVALID")
        native = _strict_json(
            resource_stop_observer._NATIVE_STOP_ROOT
            / (claim_id + ".json"))
        at = native.get("observed_boottime_ms")
        _need(native.get("native_stop_receipt_version") == 1
              and native.get("source") == "Y700_NATIVE_DRIVER_AND_BRIDGE"
              and native.get("claim_id") == claim_id
              and native.get("owner_id") == binding.get("owner_id")
              and native.get("backend_job_id") == backend_id
              and native.get("boot_id") == now.boot_id
              and native.get("state_epoch") == now.state_epoch
              and native.get("native_ui_subjobs_absent") is True
              and native.get("linux_child_mutators_absent") is True
              and native.get("all_subordinates_terminal_positive") is True
              and type(at) is int
              and 0 <= now.observed_boottime_ms - at <= 1000,
              "ARCHIVE_REPAIR_MUTATOR_STOP_UNPROVEN")
        existing_claim = resource_arbiter.read_claim()
        _need(existing_claim is None
              or existing_claim.get("claim_id") != claim_id
              or existing_claim.get("reconcile_required") is True,
              "ARCHIVE_REPAIR_ORIGINAL_CLAIM_STILL_ACTIVE")

        os.replace(source, target)
        for folder in (_READY, _PUBLISHED):
            handle = os.open(
                folder, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(handle)
            finally:
                os.close(handle)
        return {
            "status": "PUBLISHER_ARCHIVE_RECOVERED",
            "capability_job_id": capability_job_id,
            "backend_job_id": backend_id,
            "publisher_job_id": publisher_id,
            "external_effect_attempts": 0,
            "backend_resubmitted": False,
            "capability_terminalized": False,
        }
