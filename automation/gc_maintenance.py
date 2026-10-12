"""Rev3.7 foreground-only maintenance garbage collection.

Default is read-only dry-run. Only proven terminal archive records may be
considered; unresolved active jobs, effect evidence, resource claims and
uncertain staging are never eligible. No background worker or daemon.

Apply is statically CLOSED pending full PRD acceptance and reviewed release.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
import re
from typing import Any

from automation.capability_job_store import (
    CAP_JOBS, SUBMISSIONS, CapabilityStoreError, _read_json, _need,
)

_ARCHIVE = ("verified", "outcome_not_achieved", "failed",
            "cancelled", "expired")
_JOB_ID = re.compile(r"^cap-[0-9a-f]{48}$")
_GC_APPLY_ACCEPTED = False


@dataclass(frozen=True)
class RetentionCandidate:
    kind: str
    object_id: str
    created_at: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "object_id": self.object_id,
            "created_at": self.created_at, "reason": self.reason,
        }


def _past_retention(iso: str, older_than_sec: int,
                    now: datetime) -> bool:
    try:
        parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    return (parsed.tzinfo is not None and parsed <= now
            and (now - parsed).total_seconds() > older_than_sec)


def gc_preview(
    *,
    jobs_root: Path = CAP_JOBS,
    older_than_sec: int,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Read terminal result authority; never walk symlinked workspaces."""
    if type(older_than_sec) is not int or older_than_sec < 86400:
        raise CapabilityStoreError("GC_RETENTION_TOO_SHORT")
    now = now_utc or datetime.now(timezone.utc)
    _need(now.tzinfo is not None, "GC_CLOCK_UNAVAILABLE")
    candidates: list[RetentionCandidate] = []
    unsafe_or_unknown = 0
    for label in _ARCHIVE:
        directory = jobs_root / "archive" / label
        if not directory.exists():
            continue
        _need(directory.is_dir() and not directory.is_symlink(),
              "GC_ARCHIVE_PATH_UNTRUSTED")
        for entry in directory.iterdir():
            if (entry.is_symlink() or not entry.is_dir()
                    or not _JOB_ID.fullmatch(entry.name)):
                unsafe_or_unknown += 1
                continue
            result = entry / "result.json"
            # Do not treat an archive path alone as terminal proof.
            try:
                raw = _read_json(result)
            except CapabilityStoreError:
                unsafe_or_unknown += 1
                continue
            if not (raw.get("result_version") == 1
                    and raw.get("terminal") is True
                    and raw.get("capability_job_id") == entry.name
                    and raw.get("external_effect_retry_allowed") is False
                    and raw.get("outcome") == label.upper()
                    and _past_retention(
                        raw.get("completed_at", ""),
                        older_than_sec, now)):
                unsafe_or_unknown += 1
                continue
            if (jobs_root / "active" / entry.name).exists():
                unsafe_or_unknown += 1
                continue
            candidates.append(RetentionCandidate(
                "terminal_archive", entry.name,
                raw["completed_at"], "PROVEN_TERMINAL_ARCHIVE",
            ))
    # Staging orphan cleanup and expired submission binding deletion are
    # deliberately NOT inferred from age alone: crash/replay safety needs
    # an exact identity/absence/reconcile proof first.
    return {
        "status": "READ_ONLY_GC_PREVIEW",
        "candidate_count": len(candidates),
        "candidates": [x.as_dict() for x in candidates],
        "unsafe_or_unclassified_count": unsafe_or_unknown,
        "staging_cleanup_authorized": False,
        "submission_index_cleanup_authorized": False,
        "active_job_cleanup_authorized": False,
        "apply_authorized": False,
        "effect_replayed": False,
        "mutation_attempts": 0,
    }


def gc_apply(*, older_than_sec: int) -> dict[str, Any]:
    """Prune ONLY aged terminal auxiliary data; preserve recovery SOT.

    Immutable result.json, identity/request/policy, backend execution
    witness, claim history, effect boundary, journal, and the submission
    registry MUST outlive any evidence pruning. Archive-directory and
    submission-binding deletion need a separate durable tombstone protocol,
    so they are conservatively excluded from this safe first pass.
    """
    if not _GC_APPLY_ACCEPTED:
        raise CapabilityStoreError("GC_APPLY_RELEASE_GATE_CLOSED")
    import fcntl
    from automation import resource_arbiter
    from automation.capability_job_store import _fsync_directory, _locked
    _need(type(older_than_sec) is int and older_than_sec >= 86400,
          "GC_RETENTION_TOO_SHORT")
    maintenance = CAP_JOBS / ".gc-maintenance.lock"
    with _locked(maintenance):
        before = gc_preview(older_than_sec=older_than_sec)
        claim = resource_arbiter.read_claim()
        pruned = 0
        skipped = 0
        for item in before["candidates"]:
            job_id = item["object_id"]
            _need(bool(_JOB_ID.fullmatch(job_id)), "GC_JOB_ID_INVALID")
            # The exact root result is revalidated on each candidate.
            archive_category = None
            for label in _ARCHIVE:
                candidate_path = CAP_JOBS / "archive" / label / job_id
                if candidate_path.is_dir() and not candidate_path.is_symlink():
                    _need(archive_category is None,
                          "GC_DUPLICATE_ARCHIVE_IDENTITY")
                    archive_category = label
            if archive_category is None:
                skipped += 1
                continue
            path = CAP_JOBS / "archive" / archive_category / job_id
            if (CAP_JOBS / "active" / job_id).exists() or (
                    claim is not None
                    and claim.get("capability_job_id") == job_id):
                skipped += 1
                continue
            with _locked(path / "transition.lock"):
                result = _read_json(path / "result.json")
                if (result.get("terminal") is not True
                        or result.get("capability_job_id") != job_id
                        or result.get("outcome") != archive_category.upper()
                        or not _past_retention(
                            result.get("completed_at", ""),
                            older_than_sec, datetime.now(timezone.utc))):
                    skipped += 1
                    continue
                # Only a purpose-made non-authoritative temp directory is
                # eligible. No generic symlink recursion, no archive unlink.
                transient = path / ".terminal-tmp"
                if not transient.exists():
                    continue
                _need(not transient.is_symlink() and transient.is_dir(),
                      "GC_TRANSIENT_PATH_UNTRUSTED")
                for child in transient.iterdir():
                    _need(child.is_file() and not child.is_symlink(),
                          "GC_TRANSIENT_TREE_NOT_FLAT")
                    _need(child.stat().st_size <= 32 * 1024 * 1024,
                          "GC_TRANSIENT_FILE_OVERSIZE")
                    child.unlink()
                    pruned += 1
                _fsync_directory(transient)
                transient.rmdir()
                _fsync_directory(path)
        return {
            "status": "GC_SAFE_TERMINAL_AUX_PRUNED",
            "terminal_candidates": before["candidate_count"],
            "transient_files_pruned": pruned,
            "candidates_skipped": skipped,
            "authoritative_archives_deleted": 0,
            "submission_registry_deleted": 0,
            "active_jobs_deleted": 0,
            "claim_released": False,
            "external_effect_retried": False,
        }
