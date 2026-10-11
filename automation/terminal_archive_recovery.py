"""Rev3.7 terminal-archive crash completion, never Backend recovery.

The durable result.json is terminal authority even if a crash occurs
after fsync but before active -> archive rename. This operator-only repair
checks immutable request/policy/result identities and performs only the
idempotent directory move under the SAME transition.lock.

It cannot create, submit, replay, verify, cancel or finalize a Backend.
The mutation gate remains CLOSED until whole-PRD acceptance.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any

from automation.capability_job_store import (
    CAP_JOBS, CapabilityStoreError, _fsync_directory, _locked,
    _read_json, _sha, _root_dir, _need,
)

_ARCHIVE = {
    "VERIFIED": "verified",
    "OUTCOME_NOT_ACHIEVED": "outcome_not_achieved",
    "FAILED": "failed",
    "CANCELLED": "cancelled",
    "EXPIRED": "expired",
}
_ID = re.compile(r"^cap-[0-9a-f]{48}$")
_ARCHIVE_RECOVERY_ACCEPTED = False


def inspect_terminal_archive_pending_readonly(
    job_id: str, *, jobs_root: Path = CAP_JOBS,
) -> dict[str, Any]:
    """Identity + terminal marker inspection, without repairing anything."""
    _need(isinstance(job_id, str) and _ID.fullmatch(job_id) is not None,
          "CAPABILITY_JOB_ID_INVALID")
    source = jobs_root / "active" / job_id
    _need(source.is_dir() and not source.is_symlink(),
          "CAPABILITY_ACTIVE_PATH_UNAVAILABLE")
    with _locked(source / "transition.lock", shared=True):
        identity = _read_json(source / "identity.json")
        request = _read_json(source / "request.json")
        policy = _read_json(source / "effective_policy.json")
        result = _read_json(source / "result.json")
        _need(
            identity.get("capability_job_id") == job_id
            and identity.get("request_sha256") == _sha(request)
            and identity.get("effective_policy_sha256") == _sha(policy)
            and result.get("result_version") == 1
            and result.get("capability_job_id") == job_id
            and result.get("request_sha256") == _sha(request)
            and result.get("outcome") in _ARCHIVE
            and result.get("terminal") is True
            and result.get("external_effect_retry_allowed") is False,
            "TERMINAL_ARCHIVE_PROOF_UNAVAILABLE",
        )
        archive = jobs_root / "archive" / _ARCHIVE[result["outcome"]]
        destination = archive / job_id
        _need(not destination.exists() and not destination.is_symlink(),
              "TERMINAL_ARCHIVE_CONFLICT")
        return {
            "status": "TERMINAL_ARCHIVE_PENDING_READ_ONLY",
            "capability_job_id": job_id,
            "outcome": result["outcome"],
            "archive_class": _ARCHIVE[result["outcome"]],
            "terminal_authority": "result.json",
            "external_effect_retry_allowed": False,
            "backend_replayed": False,
            "archive_mutated": False,
        }


def finish_terminal_archive_after_acceptance(
    job_id: str, *, jobs_root: Path = CAP_JOBS,
) -> dict[str, Any]:
    """One idempotent path move, protected by the existing job flock."""
    if not _ARCHIVE_RECOVERY_ACCEPTED:
        raise CapabilityStoreError("ARCHIVE_RECOVERY_RELEASE_GATE_CLOSED")
    _need(isinstance(job_id, str) and _ID.fullmatch(job_id) is not None,
          "CAPABILITY_JOB_ID_INVALID")
    active = jobs_root / "active" / job_id
    if not active.exists() and not active.is_symlink():
        # Already archived, or identity missing: read only, no fabrication.
        from automation.capability_job_store import CapabilityStore
        current = CapabilityStore(jobs=jobs_root).observe(job_id)
        _need(current.get("terminal") is True,
              "TERMINAL_ARCHIVE_NOT_FOUND")
        return {
            "status": "ALREADY_TERMINAL_ARCHIVED",
            "capability_job_id": job_id,
            "backend_replayed": False,
        }
    _need(active.is_dir() and not active.is_symlink(),
          "CAPABILITY_ACTIVE_PATH_UNTRUSTED")
    with _locked(active / "transition.lock"):
        identity = _read_json(active / "identity.json")
        request = _read_json(active / "request.json")
        policy = _read_json(active / "effective_policy.json")
        result = _read_json(active / "result.json")
        _need(
            identity.get("capability_job_id") == job_id
            and identity.get("request_sha256") == _sha(request)
            and identity.get("effective_policy_sha256") == _sha(policy)
            and result.get("result_version") == 1
            and result.get("capability_job_id") == job_id
            and result.get("request_sha256") == _sha(request)
            and result.get("outcome") in _ARCHIVE
            and result.get("terminal") is True
            and result.get("external_effect_retry_allowed") is False,
            "TERMINAL_ARCHIVE_PROOF_UNAVAILABLE",
        )
        folder = jobs_root / "archive" / _ARCHIVE[result["outcome"]]
        _root_dir(folder)
        destination = folder / job_id
        _need(not destination.exists() and not destination.is_symlink(),
              "TERMINAL_ARCHIVE_CONFLICT")
        os.replace(active, destination)
        _fsync_directory(active.parent)
        _fsync_directory(folder)
        return {
            "status": "TERMINAL_ARCHIVE_COMPLETED",
            "capability_job_id": job_id,
            "outcome": result["outcome"],
            "terminal_authority": "result.json",
            "backend_replayed": False,
            "external_effect_retry_allowed": False,
        }
