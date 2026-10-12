"""Read-only, fail-closed evidence inventory for interrupted UI jobs.

No reconciliation, replay, Claim release or Android action is performed here.
A positive terminal receipt is not itself proof of an external side effect.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

MAX_JOURNAL_BYTES = 8 * 1024 * 1024
MAX_JOURNAL_ROWS = 10000
TERMINAL_PHASES = {"MUTATION_COMMITTED", "MUTATION_AMBIGUOUS"}


class RecoveryEvidenceError(RuntimeError):
    pass


def _private_bytes(path: Path, limit: int) -> bytes | None:
    """Read a bounded owner-private regular file without following leaf links."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RecoveryEvidenceError("RECOVERY_EVIDENCE_UNAVAILABLE") from exc
    try:
        before = os.fstat(fd)
        named = os.stat(path, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600
                or (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino)
                or before.st_size > limit):
            raise RecoveryEvidenceError("RECOVERY_EVIDENCE_UNTRUSTED")
        chunks = []
        remaining = limit + 1
        while remaining:
            data = os.read(fd, min(remaining, 65536))
            if not data:
                break
            chunks.append(data)
            remaining -= len(data)
        raw = b"".join(chunks)
        after = os.fstat(fd)
        named_after = os.stat(path, follow_symlinks=False)
        if (len(raw) > limit or len(raw) != before.st_size
                or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                or (after.st_dev, after.st_ino) != (named_after.st_dev, named_after.st_ino)):
            raise RecoveryEvidenceError("RECOVERY_EVIDENCE_CHANGED")
        return raw
    except OSError as exc:
        raise RecoveryEvidenceError("RECOVERY_EVIDENCE_UNAVAILABLE") from exc
    finally:
        os.close(fd)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate evidence key")
        result[key] = value
    return result


def _json_object(path: Path) -> dict[str, Any] | None:
    raw = _private_bytes(path, 1024 * 1024)
    if raw is None:
        return None
    try:
        obj = json.loads(raw, object_pairs_hook=_unique_pairs)
    except (UnicodeError, ValueError) as exc:
        raise RecoveryEvidenceError("RECOVERY_JSON_INVALID") from exc
    if not isinstance(obj, dict):
        raise RecoveryEvidenceError("RECOVERY_JSON_INVALID")
    return obj


def _journal(path: Path) -> list[dict[str, Any]] | None:
    raw = _private_bytes(path, MAX_JOURNAL_BYTES)
    if raw is None:
        return None
    if raw and not raw.endswith(b"\n"):
        raise RecoveryEvidenceError("RECOVERY_JOURNAL_PARTIAL")
    lines = raw.splitlines()
    if len(lines) > MAX_JOURNAL_ROWS:
        raise RecoveryEvidenceError("RECOVERY_JOURNAL_OVERSIZE")
    result = []
    for line in lines:
        try:
            item = json.loads(line, object_pairs_hook=_unique_pairs)
        except (UnicodeError, ValueError) as exc:
            raise RecoveryEvidenceError("RECOVERY_JOURNAL_INVALID") from exc
        if not isinstance(item, dict) or not isinstance(item.get("phase"), str):
            raise RecoveryEvidenceError("RECOVERY_JOURNAL_INVALID")
        result.append(item)
    return result


def inspect_job(job_dir: Path, *, expected_job_id: str | None = None) -> dict[str, Any]:
    """Classify evidence only; all uncertainty is a replay prohibition."""
    directory = os.lstat(job_dir)
    if (not stat.S_ISDIR(directory.st_mode)
            or directory.st_uid != os.geteuid()
            or stat.S_IMODE(directory.st_mode) != 0o700):
        raise RecoveryEvidenceError("RECOVERY_DIRECTORY_UNTRUSTED")
    request = _json_object(job_dir / "workflow.json")
    if request is None or not isinstance(request.get("job_id"), str):
        raise RecoveryEvidenceError("RECOVERY_REQUEST_UNAVAILABLE")
    job_id = request["job_id"]
    if job_id != job_dir.name or (expected_job_id is not None and job_id != expected_job_id):
        raise RecoveryEvidenceError("RECOVERY_JOB_ID_MISMATCH")
    checkpoint = _json_object(job_dir / "checkpoint.json")
    state = _json_object(job_dir / "state.json")
    result = _json_object(job_dir / "result.json")
    journal = _journal(job_dir / "journal.jsonl")
    if journal is None:
        raise RecoveryEvidenceError("RECOVERY_JOURNAL_UNAVAILABLE")
    session = request.get("session_id")
    if not isinstance(session, str) or not session:
        raise RecoveryEvidenceError("RECOVERY_SESSION_UNAVAILABLE")
    for row in journal:
        if row.get("phase") in {"SESSION_START", "MUTATION_PREPARED", "MUTATION_COMMITTED"}:
            if row.get("job_id") not in (None, job_id):
                raise RecoveryEvidenceError("RECOVERY_JOURNAL_IDENTITY_MISMATCH")
            if row.get("session_id") not in (None, session):
                raise RecoveryEvidenceError("RECOVERY_JOURNAL_IDENTITY_MISMATCH")
    prepared = [row for row in journal if row["phase"] == "MUTATION_PREPARED"]
    committed = [row for row in journal if row["phase"] == "MUTATION_COMMITTED"]
    ambiguous = [row for row in journal if row["phase"] == "MUTATION_AMBIGUOUS"]
    terminal = result is not None and result.get("status") in {"PASS", "FAILED", "CANCELLED", "BLOCKED"}
    if result is not None and (result.get("job_id") != job_id
                               or result.get("session_id") != session):
        raise RecoveryEvidenceError("RECOVERY_RESULT_IDENTITY_MISMATCH")
    # Validate mutation ordering in the actual append sequence. Grouping all
    # PREPARED before all COMMITTED would accept a COMMITTED row written first.
    actions = request.get("actions")
    if not isinstance(actions, list) or len(actions) > 2048:
        raise RecoveryEvidenceError("RECOVERY_ACTIONS_INVALID")
    outstanding: dict[int, dict[str, Any]] = {}
    seen_prepared: set[int] = set()
    for row in journal:
        phase = row.get("phase")
        if phase not in {"MUTATION_PREPARED", "MUTATION_COMMITTED", "MUTATION_AMBIGUOUS"}:
            continue
        if row.get("job_id") != job_id or row.get("session_id") != session:
            raise RecoveryEvidenceError("RECOVERY_MUTATION_IDENTITY_MISMATCH")
        index = row.get("action_index")
        if type(index) is not int or not 0 <= index < len(actions):
            raise RecoveryEvidenceError("RECOVERY_MUTATION_INDEX_INVALID")
        action = actions[index]
        if not isinstance(action, dict) or row.get("action_id") != action.get("action_id"):
            raise RecoveryEvidenceError("RECOVERY_MUTATION_ACTION_MISMATCH")
        if phase == "MUTATION_PREPARED":
            if index in seen_prepared:
                raise RecoveryEvidenceError("RECOVERY_PREPARED_SEQUENCE_INVALID")
            seen_prepared.add(index)
            outstanding[index] = row
        elif phase == "MUTATION_COMMITTED":
            prior = outstanding.pop(index, None)
            if prior is None:
                raise RecoveryEvidenceError("RECOVERY_COMMIT_WITHOUT_PREPARE")
            if (row.get("state_epoch") != prior.get("state_epoch")
                    or type(row.get("revision_before")) is not int
                    or row.get("revision_before") != prior.get("revision_before")
                    or type(row.get("revision_after")) is not int
                    or row["revision_after"] != row["revision_before"] + 1):
                raise RecoveryEvidenceError("RECOVERY_COMMIT_AUTHORITY_MISMATCH")
    # Checkpoint cannot independently certify an uncertain mutation.
    if checkpoint is not None:
        if (checkpoint.get("job_id") != job_id
                or checkpoint.get("session_id") != session):
            raise RecoveryEvidenceError("RECOVERY_CHECKPOINT_IDENTITY_MISMATCH")
        completed = checkpoint.get("last_completed_action_index")
        if type(completed) is not int or completed < -1 or completed >= len(actions):
            raise RecoveryEvidenceError("RECOVERY_CHECKPOINT_INDEX_INVALID")
        if completed >= 0 and checkpoint.get("last_completed_action_id") != actions[completed].get("action_id"):
            raise RecoveryEvidenceError("RECOVERY_CHECKPOINT_ACTION_MISMATCH")
    reasons = []
    if outstanding:
        reasons.append("PREPARED_OUTCOME_UNRESOLVED")
    if ambiguous:
        reasons.append("MUTATION_AMBIGUOUS")
    if not terminal:
        reasons.append("TERMINAL_RESULT_UNVERIFIED")
    if checkpoint is None or state is None:
        reasons.append("CHECKPOINT_OR_STATE_MISSING")
    if result is not None and result.get("status") == "RECONCILE_REQUIRED":
        reasons.append("RECONCILIATION_REQUIRED")
    # This inspector does not authorize replay even when evidence is complete.
    return {
        "job_id": job_id,
        "session_id": session,
        "classification": "RECONCILE_REQUIRED" if reasons else "TERMINAL_EVIDENCE_PRESENT",
        "reason_codes": reasons,
        "prepared_count": len(prepared),
        "committed_count": len(committed),
        "ambiguous_count": len(ambiguous),
        "unresolved_action_indices": sorted(outstanding),
        "automatic_replay_allowed": False,
        "claim_release_authorized": False,
        "mutation_dispatch_allowed": False,
    }
