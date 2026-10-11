"""Rev3.7 source-gated exact Capability reconciler (NO effect retry).

Normal foreground recovery reads the original bound Backend ID and
durable per-capability verifiers. It never resubmits, chooses another ID,
unlocks the device, invokes UI Publisher, or synthesizes positive proof.
Business outcome reconciliation is independent of resource-only release.

Effect/Backend uncertainty without a positively recorded terminal
verifier ALWAYS remains RECONCILE_REQUIRED.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from automation.capability_job_store import (
    CAP_JOBS, CapabilityStore, CapabilityStoreError,
    _read_json, _sha, inspect_public_commit_authority_readonly,
)
from automation.recovery_inventory import inspect_active_exact_readonly

_RECONCILE_MUTATION_ACCEPTED = False
_JOB_ID = re.compile(r"^cap-[0-9a-f]{48}$")
_PUBLISHER_ID = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
_PUBLISHED = Path("/opt/y700/media/published")
_READY = Path("/opt/y700/media/ready")


def inspect_exact_outcome_readonly(
    capability_job_id: str, *,
    store: CapabilityStore | None = None,
) -> dict[str, Any]:
    """Positive Profile verification is an archived durable source fact."""
    if not isinstance(capability_job_id, str) or not _JOB_ID.fullmatch(
            capability_job_id):
        raise CapabilityStoreError("CAPABILITY_JOB_ID_INVALID")
    store = store or CapabilityStore()
    snapshot = store.observe(capability_job_id)
    if snapshot.get("terminal") is True:
        active_marker = (
            store.jobs / "active" / capability_job_id / "result.json")
        if active_marker.exists() or active_marker.is_symlink():
            from automation.terminal_archive_recovery import (
                inspect_terminal_archive_pending_readonly,
            )
            pending = inspect_terminal_archive_pending_readonly(
                capability_job_id, jobs_root=store.jobs)
            return {
                **pending,
                "effect_retry_allowed": False,
                "state_mutated": False,
            }
        return {
            "status": "ALREADY_TERMINAL",
            "capability_job_id": capability_job_id,
            "effect_retry_allowed": False,
            "state_mutated": False,
        }
    active = store.jobs / "active" / capability_job_id
    if not active.is_dir() or active.is_symlink():
        raise CapabilityStoreError("RECONCILE_SOURCE_UNAVAILABLE")
    if not (active / "backend.json").exists():
        stage = inspect_active_exact_readonly(
            capability_job_id, root=store.jobs)
        return {
            "status": "PRE_SUBMIT_EXPLICIT_CONTINUATION_ONLY"
                      if stage.get("status") == "PRE_SUBMIT_NEVER_BOUND"
                      else "RECONCILE_REQUIRED",
            "reason_code": stage.get("reason_code"),
            "capability_job_id": capability_job_id,
            "effect_retry_allowed": False,
            "new_backend_allocated": False,
            "state_mutated": False,
        }
    identity = _read_json(active / "identity.json")
    backend = _read_json(active / "backend.json")
    request = _read_json(active / "request.json")
    policy = _read_json(active / "effective_policy.json")
    state = _read_json(active / "state.json")
    if (identity.get("capability_job_id") != capability_job_id
            or identity.get("request_sha256") != _sha(request)
            or identity.get("effective_policy_sha256") != _sha(policy)
            or backend.get("capability_job_id") != capability_job_id
            or backend.get("request_sha256")
                != identity.get("request_sha256")):
        raise CapabilityStoreError("RECONCILE_IMMUTABLE_IDENTITY_MISMATCH")
    backend_id = backend.get("backend_job_id")
    possible = inspect_active_exact_readonly(
        capability_job_id, root=store.jobs)
    if (possible.get("status") == "PRE_SUBMIT_BOUND_READ_ONLY"
            or possible.get("status") == "PRE_SUBMIT_NEVER_BOUND"):
        return {
            "status": "PRE_SUBMIT_EXPLICIT_CONTINUATION_ONLY",
            "capability_job_id": capability_job_id,
            "backend_job_id": backend_id,
            "effect_retry_allowed": False,
            "new_backend_allocated": False,
            "state_mutated": False,
        }
    if backend.get("backend_type") in {
        "ui_workflow", "observation", "root_exec",
    }:
        backend_type = backend["backend_type"]
        filename = {
            "ui_workflow": "settings-restore-result.json",
            "observation": "observation-result.json",
            "root_exec": "root-result.json",
        }[backend_type]
        receipt_path = active / filename
        if not receipt_path.exists() or receipt_path.is_symlink():
            return {
                "status": "RECONCILE_REQUIRED",
                "reason_code": "POSITIVE_BACKEND_VERIFIER_ABSENT",
                "capability_job_id": capability_job_id,
                "backend_job_id": backend_id,
                "effect_retry_allowed": False,
                "state_mutated": False,
            }
        receipt = _read_json(receipt_path)
        exact = (
            receipt.get("capability_job_id") == capability_job_id
            and receipt.get("backend_job_id") == backend_id
        )
        if backend_type == "ui_workflow":
            positive = (
                exact
                and receipt.get("settings_restore_result_version") == 1
                and receipt.get("request_sha256")
                    == identity["request_sha256"]
                and receipt.get("restored_verified") is True
                and receipt.get("initial_mode") in {"LIGHT", "DARK"}
                and receipt.get("initial_mode")
                    == receipt.get("restored_mode")
            )
        elif backend_type == "observation":
            positive = (
                exact
                and receipt.get("request_sha256")
                    == identity["request_sha256"]
                and receipt.get("authoritative_state_observed") is True
                and receipt.get("read_only") is True
            )
        else:
            positive = (
                exact
                and receipt.get("request_sha256")
                    == identity["request_sha256"]
                and receipt.get("root_epoch_advanced") is True
                and receipt.get("command_exited_zero") is True
                and receipt.get("fixed_maintenance_contract_id")
                    == "read-only-system-info.v1"
            )
        if not positive:
            return {
                "status": "RECONCILE_REQUIRED",
                "reason_code": "POSITIVE_BACKEND_VERIFIER_INVALID",
                "capability_job_id": capability_job_id,
                "backend_job_id": backend_id,
                "effect_retry_allowed": False,
                "state_mutated": False,
            }
        return {
            "status": "POSITIVE_BACKEND_VERIFIER_OBSERVED",
            "capability_job_id": capability_job_id,
            "backend_job_id": backend_id,
            "request_sha256": identity["request_sha256"],
            "backend_type": backend_type,
            "terminal_outcome_candidate": "VERIFIED",
            "effect_retry_allowed": False,
            "state_mutated": False,
        }
    # All non-Publisher backends were handled by the single typed
    # verifier above. No duplicated, divergent receipt checks.
    if backend.get("backend_type") != "publisher":
        raise CapabilityStoreError("RECONCILE_BACKEND_TYPE_UNSUPPORTED")
    payload = request.get("payload")
    if not isinstance(payload, dict):
        raise CapabilityStoreError("RECONCILE_PUBLISHER_PAYLOAD_INVALID")
    publisher_id = payload.get("existing_publisher_job_id")
    if not isinstance(publisher_id, str) or not _PUBLISHER_ID.fullmatch(
            publisher_id):
        raise CapabilityStoreError("RECONCILE_PUBLISHER_ID_INVALID")
    if payload.get("publish_mode") == "DRY_RUN":
        # A preview is a terminal LOCAL verification candidate, NEVER a
        # published TikTok post. It uses its own immutable Capability
        # receipt, not Profile/published metadata or COMMIT approval.
        preview_path = active / "publisher-dryrun-result.json"
        if not preview_path.is_file() or preview_path.is_symlink():
            return {
                "status": "RECONCILE_REQUIRED",
                "reason_code": "DRY_RUN_POSITIVE_RECEIPT_ABSENT",
                "capability_job_id": capability_job_id,
                "backend_job_id": backend_id,
                "effect_retry_allowed": False,
                "state_mutated": False,
            }
        preview = _read_json(preview_path)
        positive = (
            preview.get("publisher_dryrun_result_version") == 1
            and preview.get("capability_job_id") == capability_job_id
            and preview.get("backend_job_id") == backend_id
            and preview.get("publisher_job_id") == publisher_id
            and preview.get("request_sha256") == identity["request_sha256"]
            and preview.get("content_sha256")
                == payload.get("content_sha256")
            and preview.get("caption_sha256")
                == payload.get("caption_sha256")
            and preview.get("preview_state") == "POST_CONFIG"
            and preview.get("caption_verified") is True
            and preview.get("visibility") == "PUBLIC"
            and preview.get("ui_cleanup_complete") is True
            and preview.get("external_effect_attempts") == 0
            and preview.get("external_effect_retry_allowed") is False
            and not (active / "effect-boundary.json").exists()
        )
        if positive:
            from automation.resource_stop_observer import (
                positive_synchronous_ui_quiescence,
                inspect_exact_stop_readonly,
            )
            backend_witness = _read_json(active / "backend-execution.json")
            guard = backend_witness.get("resource_guard")
            if isinstance(guard, dict):
                stopped_live = positive_synchronous_ui_quiescence(
                    guard, backend_job_id=backend_id)
                stopped_dead = (
                    {} if stopped_live
                    else inspect_exact_stop_readonly(
                        guard.get("claim_id", "")))
                positive = (
                    stopped_live
                    or stopped_dead.get("fully_quiescent_positive") is True
                )
            else:
                positive = False
        if not positive:
            return {
                "status": "RECONCILE_REQUIRED",
                "reason_code": "DRY_RUN_QUIESCENCE_OR_RECEIPT_UNVERIFIED",
                "capability_job_id": capability_job_id,
                "backend_job_id": backend_id,
                "effect_retry_allowed": False,
                "state_mutated": False,
            }
        # CapabilityStore.finalize_terminal independently repeats all
        # checks under transition.lock before result.json/archive rename.
        return {
            "status": "POSITIVE_BACKEND_VERIFIER_OBSERVED",
            "capability_job_id": capability_job_id,
            "backend_job_id": backend_id,
            "request_sha256": identity["request_sha256"],
            "backend_type": "publisher",
            "terminal_outcome_candidate": "VERIFIED",
            "external_effect_attempts": 0,
            "effect_retry_allowed": False,
            "state_mutated": False,
        }
    if payload.get("publish_mode") != "COMMIT":
        raise CapabilityStoreError("RECONCILE_PUBLISH_MODE_INVALID")
    if not inspect_public_commit_authority_readonly(
            active,
            capability_job_id=capability_job_id,
            backend_job_id=backend_id,
            request_sha256=identity["request_sha256"],
            effective_policy_sha256=identity["effective_policy_sha256"],
            content_sha256=payload.get("content_sha256"),
            caption_sha256=payload.get("caption_sha256")):
        return {
            "status": "RECONCILE_REQUIRED",
            "reason_code": "PUBLIC_COMMIT_AUTHORITY_UNVERIFIED",
            "capability_job_id": capability_job_id,
            "backend_job_id": backend_id,
            "effect_retry_allowed": False,
            "state_mutated": False,
        }
    published = _PUBLISHED / publisher_id / "publish-result.json"
    if not published.exists() or published.is_symlink():
        # A crash may occur between the durable Profile result write and
        # atomic ready/ -> published/ namespace move. Never retry TikTok;
        # retain the original positive receipt for archive-only repair.
        prepared = _READY / publisher_id / "publish-result.json"
        if prepared.is_file() and not prepared.is_symlink():
            positive = _read_json(prepared)
            if (positive.get("status") == "PUBLISHED"
                    and positive.get("job_id") == publisher_id
                    and positive.get("capability_job_id")
                        == capability_job_id
                    and positive.get("backend_job_id") == backend_id
                    and positive.get("request_sha256")
                        == identity["request_sha256"]
                    and positive.get("content_sha256")
                        == payload.get("content_sha256")
                    and positive.get("caption_sha256")
                        == payload.get("caption_sha256")
                    and positive.get("visibility") == "PUBLIC"
                    and isinstance(positive.get("verification"), dict)
                    and positive["verification"].get("verified") is True):
                return {
                    "status": "PUBLISHER_ARCHIVE_PENDING",
                    "reason_code": "POSITIVE_PROFILE_RECEIPT_BEFORE_RENAME",
                    "capability_job_id": capability_job_id,
                    "backend_job_id": backend_id,
                    "effect_retry_allowed": False,
                    "archive_only_reconciliation": True,
                    "state_mutated": False,
                }
        return {
            "status": "RECONCILE_REQUIRED",
            "reason_code": "POSITIVE_PROFILE_VERIFIER_ABSENT",
            "capability_job_id": capability_job_id,
            "backend_job_id": backend_id,
            "effect_retry_allowed": False,
            "state_mutated": False,
        }
    receipt = _read_json(published)
    _positive = (
        receipt.get("status") == "PUBLISHED"
        and receipt.get("job_id") == publisher_id
        and receipt.get("capability_job_id") == capability_job_id
        and receipt.get("backend_job_id") == backend_id
        and receipt.get("request_sha256") == identity["request_sha256"]
        and receipt.get("content_sha256") == payload.get("content_sha256")
        and receipt.get("caption_sha256") == payload.get("caption_sha256")
        and receipt.get("visibility") == "PUBLIC"
        and isinstance(receipt.get("verification"), dict)
        and receipt["verification"].get("verified") is True
    )
    if not _positive:
        return {
            "status": "RECONCILE_REQUIRED",
            "reason_code": "PROFILE_RECEIPT_UNVERIFIED",
            "capability_job_id": capability_job_id,
            "backend_job_id": backend_id,
            "effect_retry_allowed": False,
            "state_mutated": False,
        }
    return {
        "status": "POSITIVE_PROFILE_VERIFIER_OBSERVED",
        "capability_job_id": capability_job_id,
        "backend_job_id": backend_id,
        "request_sha256": identity["request_sha256"],
        "terminal_outcome_candidate": "VERIFIED",
        "effect_retry_allowed": False,
        "state_mutated": False,
    }


def reconcile_exact_after_acceptance(
    capability_job_id: str,
) -> dict[str, Any]:
    """At most one final result; no input, no Publisher rerun."""
    if not _RECONCILE_MUTATION_ACCEPTED:
        raise CapabilityStoreError("EXACT_RECONCILE_RELEASE_GATE_CLOSED")
    store = CapabilityStore()
    candidate = inspect_exact_outcome_readonly(
        capability_job_id, store=store)
    if candidate.get("status") == "TERMINAL_ARCHIVE_PENDING_READ_ONLY":
        from automation.terminal_archive_recovery import (
            finish_terminal_archive_after_acceptance,
        )
        return finish_terminal_archive_after_acceptance(
            capability_job_id, jobs_root=store.jobs)
    if candidate.get("status") == "PUBLISHER_ARCHIVE_PENDING":
        # Recover ONLY the positive Publisher namespace rename. The
        # archive-only adapter independently verifies exact content and
        # accepted native UI quiescence; it never launches TikTok/Core.
        from automation.publisher_archive_recovery import (
            archive_verified_publisher_after_acceptance,
        )
        archive_verified_publisher_after_acceptance(capability_job_id)
        candidate = inspect_exact_outcome_readonly(
            capability_job_id, store=store)
    if candidate.get("status") not in {
        "POSITIVE_PROFILE_VERIFIER_OBSERVED",
        "POSITIVE_BACKEND_VERIFIER_OBSERVED",
    }:
        return candidate
    # Store independently revalidates the same exact archived Profile
    # verifier under transition.lock before durable result+archive.
    terminal = store.finalize_terminal(
        capability_job_id,
        outcome="VERIFIED",
        backend_never_created_proven=False,
        business_outcome_verified=True,
        exact_backend_id=candidate["backend_job_id"],
        reason_code="EXACT_DURABLE_VERIFIER_POSITIVE_RECONCILED",
    )
    return {
        "status": "VERIFIED",
        "capability_job_id": capability_job_id,
        "outcome": terminal["outcome"],
        "effect_retry_allowed": False,
        "backend_reallocated": False,
    }
