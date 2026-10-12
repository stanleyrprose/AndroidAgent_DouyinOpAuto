"""Rev3.7 read-only crash/startup inventory: NO replay, cleanup or mutation.

Crash after SUBMISSION_POSSIBLE cannot become NEVER_CREATED. Uncertain jobs
remain RECONCILE_REQUIRED and a missing index is not silently repaired.
No scheduler, background worker, or secondary Backend ID.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import re
from typing import Any

from automation.capability_job_store import (
    CAP_JOBS, SUBMISSIONS, CapabilityStoreError, _read_json,
    _locked, _sha, _job_id,
)

_JOB = re.compile(r"^cap-[0-9a-f]{48}$")


def _blocked(job: str, code: str) -> dict[str, Any]:
    return {
        "capability_job_id": job, "status": "RECONCILE_REQUIRED",
        "reason_code": code, "backend_retry_allowed": False,
        "claim_released": False, "external_effect_attempts": 0,
    }


def inspect_active_exact_readonly(
    job_id: str, *, root: Path = CAP_JOBS,
) -> dict[str, Any]:
    if not isinstance(job_id, str) or _JOB.fullmatch(job_id) is None:
        return _blocked(str(job_id)[:128], "CAPABILITY_JOB_ID_INVALID")
    path = root / "active" / job_id
    if not path.is_dir() or path.is_symlink():
        return _blocked(job_id, "CAPABILITY_ACTIVE_PATH_UNAVAILABLE")
    try:
        with _locked(path / "transition.lock", shared=True):
            identity = _read_json(path / "identity.json")
            request = _read_json(path / "request.json")
            policy = _read_json(path / "effective_policy.json")
            state = _read_json(path / "state.json")
            if not (
                identity.get("capability_job_id") == job_id
                and identity.get("request_sha256") == _sha(request)
                and identity.get("effective_policy_sha256") == _sha(policy)
                and state.get("capability_job_id") == job_id
                and state.get("request_sha256") == identity["request_sha256"]
                and state.get("effective_policy_sha256")
                    == identity["effective_policy_sha256"]
                and state.get("lifecycle_state") == state.get("phase")
                and type(state.get("state_revision")) is int
            ):
                return _blocked(job_id, "CAPABILITY_DURABLE_IDENTITY_CORRUPT")
            if (path / "result.json").exists():
                return _blocked(job_id, "TERMINAL_ARCHIVE_PENDING")
            binding_file = path / "backend.json"
            witness_file = path / "backend-execution.json"
            if (binding_file.is_symlink() or witness_file.is_symlink()
                    or (path / "effect-boundary.json").is_symlink()
                    or (path / "result.json").is_symlink()):
                return _blocked(job_id, "DURABLE_RECOVERY_PATH_UNTRUSTED")
            if not binding_file.exists() and not witness_file.exists():
                if (state.get("phase") == "ADMITTED"
                        and not state.get("mutation_uncertain")
                        and not (path / "effect-boundary.json").exists()):
                    return {
                        "status": "PRE_SUBMIT_NEVER_BOUND",
                        "capability_job_id": job_id,
                        "continue_only_by_explicit_reconcile": True,
                        "external_effect_attempts": 0,
                    }
                return _blocked(job_id, "DURABLE_BACKEND_BINDING_MISSING")
            if not binding_file.exists() or not witness_file.exists():
                return _blocked(job_id, "BACKEND_DURABLE_WITNESS_MISSING")
            binding = _read_json(binding_file)
            witness = _read_json(witness_file)
            exact = binding.get("backend_job_id")
            if not (
                isinstance(exact, str)
                and exact.startswith(job_id + "--")
                and binding.get("capability_job_id") == job_id
                and binding.get("request_sha256") == identity["request_sha256"]
                and witness.get("backend_job_id") == exact
                and witness.get("request_sha256")
                    == identity["request_sha256"]
            ):
                return _blocked(job_id, "BACKEND_DURABLE_IDENTITY_MISMATCH")
            possible = (
                witness.get("submission_possible") is True
                or witness.get("phase") != "NEVER_CREATED"
                or witness.get("attempt_serial") != 0
                or state.get("backend_submitted") is True
            )
            if (possible or (path / "effect-boundary.json").exists()
                    or state.get("effect_uncertain") is True
                    or state.get("mutation_uncertain") is True):
                return {
                    **_blocked(job_id, "EXACT_BACKEND_AND_EFFECT_RECONCILE"),
                    "backend_job_id": exact,
                    "submission_may_have_occurred": bool(possible),
                }
            if (witness.get("phase") == "NEVER_CREATED"
                    and witness.get("submission_possible") is False
                    and witness.get("attempt_serial") == 0):
                return {
                    "status": "PRE_SUBMIT_BOUND_READ_ONLY",
                    "capability_job_id": job_id, "backend_job_id": exact,
                    "continue_only_by_explicit_reconcile": True,
                    "backend_retry_allowed": False,
                }
            return _blocked(job_id, "BACKEND_STATE_UNCLASSIFIED")
    except (OSError, ValueError, CapabilityStoreError):
        return _blocked(job_id, "DURABLE_RECOVERY_UNAVAILABLE")


def inspect_staged_bound_readonly(
    job_id: str, *, root: Path = CAP_JOBS,
    submissions: Path = SUBMISSIONS,
) -> dict[str, Any]:
    """Precisely classify a binding-first activation crash window.

    The durable submission binding is authoritative, but existence alone
    never licenses activation. This observes the stage and its original
    index under the SAME admission flock as normal admission/release;
    it never repairs a partially written stage or executes a Backend.
    """
    if not isinstance(job_id, str) or _JOB.fullmatch(job_id) is None:
        return _blocked(str(job_id)[:128], "CAPABILITY_JOB_ID_INVALID")
    stage = root / ".staging" / job_id
    active = root / "active" / job_id
    if not stage.is_dir() or stage.is_symlink():
        return _blocked(job_id, "ADMISSION_STAGING_PATH_UNTRUSTED")
    try:
        with _locked(submissions / ".admission.lock", shared=True), \
                _locked(stage / "transition.lock", shared=True):
            request = _read_json(stage / "request.json")
            policy = _read_json(stage / "effective_policy.json")
            identity = _read_json(stage / "identity.json")
            state = _read_json(stage / "state.json")
            submission_id = request.get("submission_id")
            if (not isinstance(submission_id, str)
                    or _job_id(submission_id) != job_id):
                return _blocked(job_id, "STAGED_REQUEST_IDENTITY_MISMATCH")
            bind = submissions / (
                hashlib.sha256(submission_id.encode()).hexdigest()
                + ".json")
            if not bind.exists() or bind.is_symlink():
                return _blocked(job_id,
                                "STAGED_SUBMISSION_BINDING_NOT_DURABLE")
            stored = _read_json(bind)
            request_hash = _sha(request)
            policy_hash = _sha(policy)
            if not (
                stored.get("submission_registry_version") == 1
                and stored.get("capability_job_id") == job_id
                and stored.get("request_sha256") == request_hash
                and stored.get("effective_policy_sha256") == policy_hash
                and identity.get("capability_job_id") == job_id
                and identity.get("request_sha256") == request_hash
                and identity.get("effective_policy_sha256") == policy_hash
                and state.get("capability_job_id") == job_id
                and state.get("request_sha256") == request_hash
                and state.get("effective_policy_sha256") == policy_hash
                and state.get("phase") == "ADMITTED"
                and state.get("state_revision") == 0
                and state.get("backend_submitted") is False
                and state.get("effect_uncertain") is False
                and state.get("mutation_uncertain") is False
                and not active.exists()
                and not active.is_symlink()
                and not (stage / "backend.json").exists()
                and not (stage / "cancel.json").exists()
                and not (stage / "effect-boundary.json").exists()
                and not (stage / "result.json").exists()
                and (stage / "journal.jsonl").is_file()
                and not (stage / "journal.jsonl").is_symlink()
            ):
                return _blocked(
                    job_id, "STAGED_DURABLE_IDENTITY_INCOMPLETE")
            # TTL is separately checked again during SAME-submission
            # activation and before backend submission; it is not
            # reissued or silently extended by inspecting a stage.
            return {
                "status": "BOUND_STAGE_AWAITING_ACTIVATION_READ_ONLY",
                "capability_job_id": job_id,
                "submission_binding_durable": True,
                "backend_submitted": False,
                "eligible_for_same_submission_replay_check": True,
                "activation_authorized": False,
                "release_fence_must_be_rechecked": True,
                "external_effect_retry_allowed": False,
                "mutation_attempts": 0,
            }
    except (OSError, ValueError, CapabilityStoreError):
        return _blocked(job_id, "STAGED_RECOVERY_UNAVAILABLE")


def _inventory_snapshot(directory: Path) -> dict[str, tuple[int, int]]:
    """Stable name/inode inventory; never treat a disappearing entry as empty."""
    return {
        entry.name: (entry.lstat().st_dev, entry.lstat().st_ino)
        for entry in directory.iterdir()
    }


def inspect_startup_inventory_readonly(
    *, root: Path = CAP_JOBS, maximum_jobs: int = 500,
) -> dict[str, Any]:
    try:
        active_root, staging_root = root / "active", root / ".staging"
        if (not active_root.is_dir() or active_root.is_symlink()
                or not staging_root.is_dir() or staging_root.is_symlink()):
            raise CapabilityStoreError("CAPABILITY_LIFECYCLE_PATH_UNAVAILABLE")
        active_before = _inventory_snapshot(active_root)
        staged_before = _inventory_snapshot(staging_root)
        active = sorted(active_root.iterdir())
        staged = sorted(staging_root.iterdir())
        if (len(active) != len(active_before)
                or len(staged) != len(staged_before)):
            raise CapabilityStoreError("CAPABILITY_INVENTORY_CHANGED_DURING_SCAN")
        if len(active) + len(staged) > maximum_jobs:
            raise CapabilityStoreError("CAPABILITY_INVENTORY_TOO_LARGE")
        if any(item.is_symlink() or not item.is_dir()
               or _JOB.fullmatch(item.name) is None
               for item in active + staged):
            raise CapabilityStoreError("CAPABILITY_INVENTORY_UNTRUSTED")
        active_rows = [inspect_active_exact_readonly(x.name, root=root)
                       for x in active]
        staged_rows = [inspect_staged_bound_readonly(x.name, root=root)
                       for x in staged]
        if (active_before != _inventory_snapshot(active_root)
                or staged_before != _inventory_snapshot(staging_root)):
            raise CapabilityStoreError("CAPABILITY_INVENTORY_CHANGED_DURING_SCAN")
        return {
            "status": "READ_ONLY_STARTUP_INVENTORY",
            "active_jobs": active_rows,
            "staging_jobs": staged_rows,
            "active_count": len(active),
            "staging_count": len(staged),
            "automatic_recovery_enabled": False,
            "backend_submitted": False,
            "claim_released": False,
        }
    except (OSError, ValueError, CapabilityStoreError) as exc:
        return {
            "status": "BLOCKED",
            "reason_code": getattr(
                exc, "code", "CAPABILITY_INVENTORY_UNAVAILABLE"),
            "automatic_recovery_enabled": False,
            "backend_submitted": False,
        }
