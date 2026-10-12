"""Rev3.7 read-only crash recovery evidence inspector.

No function in this module dispatches Android input, clears Claims, rewrites
checkpoints, or promotes an uncertain mutation into a successful receipt.
The scanner reports bounded evidence for human/accepted recovery workflows;
its result is NEVER a resume or replay authorization.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
from typing import Any

MAX_JOURNAL_BYTES = 8 * 1024 * 1024
MAX_JOURNAL_ROWS = 10000
MAX_JSON_BYTES = 1024 * 1024
MAX_ACTIONS = 2048
_JOB_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class RecoveryEvidenceUnavailable(RuntimeError):
    pass


def _private_file(path: Path, limit: int) -> bytes:
    """Read bounded private evidence; reject links, FIFO, and path replacement."""
    if not hasattr(os, "O_NOFOLLOW"):
        raise RecoveryEvidenceUnavailable("RECOVERY_NOFOLLOW_UNAVAILABLE")
    parent = os.lstat(path.parent)
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) != 0o700):
        raise RecoveryEvidenceUnavailable("RECOVERY_DIRECTORY_UNTRUSTED")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        named = os.lstat(path)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_size > limit
                or (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino)):
            raise RecoveryEvidenceUnavailable("RECOVERY_EVIDENCE_UNTRUSTED")
        data = os.read(fd, limit + 1)
        after = os.fstat(fd)
        current = os.lstat(path)
        if (len(data) > limit or len(data) != before.st_size
                or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                or (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino)):
            raise RecoveryEvidenceUnavailable("RECOVERY_EVIDENCE_CHANGED")
        return data
    finally:
        os.close(fd)


def _json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(_private_file(path, MAX_JSON_BYTES))
    except (UnicodeError, ValueError) as exc:
        raise RecoveryEvidenceUnavailable("RECOVERY_JSON_INVALID") from exc
    if not isinstance(obj, dict):
        raise RecoveryEvidenceUnavailable("RECOVERY_JSON_INVALID")
    return obj


def _journal(path: Path) -> list[dict[str, Any]]:
    try:
        data = _private_file(path, MAX_JOURNAL_BYTES)
        if not data or not data.endswith(b"\n"):
            raise RecoveryEvidenceUnavailable("RECOVERY_JOURNAL_TRUNCATED")
        lines = data.splitlines()
        if len(lines) > MAX_JOURNAL_ROWS:
            raise RecoveryEvidenceUnavailable("RECOVERY_JOURNAL_OVERSIZE")
        rows = [json.loads(line) for line in lines]
    except (UnicodeError, ValueError) as exc:
        raise RecoveryEvidenceUnavailable("RECOVERY_JOURNAL_INVALID") from exc
    if any(not isinstance(row, dict) or not isinstance(row.get("phase"), str)
           for row in rows):
        raise RecoveryEvidenceUnavailable("RECOVERY_JOURNAL_INVALID")
    return rows


def inspect_ui_job(ui_dir: Path, *, expected_job_id: str | None = None) -> dict[str, Any]:
    """Conservative evidence summary; never return safe_to_resume=True."""
    job_id = expected_job_id or ui_dir.name
    if not _JOB_ID.fullmatch(job_id) or ui_dir.name != job_id:
        raise RecoveryEvidenceUnavailable("RECOVERY_JOB_ID_INVALID")
    workflow = _json(ui_dir / "workflow.json")
    if workflow.get("job_id") != job_id or not isinstance(workflow.get("session_id"), str):
        raise RecoveryEvidenceUnavailable("RECOVERY_WORKFLOW_IDENTITY_MISMATCH")
    actions = workflow.get("actions")
    if not isinstance(actions, list) or len(actions) > MAX_ACTIONS:
        raise RecoveryEvidenceUnavailable("RECOVERY_ACTIONS_INVALID")
    checkpoint = _json(ui_dir / "checkpoint.json")
    if (checkpoint.get("job_id") != job_id
            or checkpoint.get("session_id") != workflow["session_id"]):
        raise RecoveryEvidenceUnavailable("RECOVERY_CHECKPOINT_IDENTITY_MISMATCH")
    completed = checkpoint.get("last_completed_action_index")
    if type(completed) is not int or completed < -1 or completed >= len(actions):
        raise RecoveryEvidenceUnavailable("RECOVERY_CHECKPOINT_INDEX_INVALID")
    if completed >= 0 and checkpoint.get("last_completed_action_id") != actions[completed].get("action_id"):
        raise RecoveryEvidenceUnavailable("RECOVERY_CHECKPOINT_ACTION_MISMATCH")
    rows = _journal(ui_dir / "journal.jsonl")
    prepared: dict[int, dict[str, Any]] = {}
    committed: set[int] = set()
    ambiguous: set[int] = set()
    for row in rows:
        phase = row["phase"]
        if phase not in {"MUTATION_PREPARED", "MUTATION_COMMITTED", "MUTATION_AMBIGUOUS"}:
            continue
        index = row.get("action_index")
        if type(index) is not int or not 0 <= index < len(actions):
            raise RecoveryEvidenceUnavailable("RECOVERY_MUTATION_INDEX_INVALID")
        if row.get("action_id") != actions[index].get("action_id"):
            raise RecoveryEvidenceUnavailable("RECOVERY_MUTATION_IDENTITY_MISMATCH")
        if phase == "MUTATION_PREPARED":
            if index in prepared:
                raise RecoveryEvidenceUnavailable("RECOVERY_DUPLICATE_PREPARE")
            if (row.get("job_id") != job_id or row.get("session_id") != workflow["session_id"]):
                raise RecoveryEvidenceUnavailable("RECOVERY_PREPARE_IDENTITY_MISMATCH")
            prepared[index] = row
        elif phase == "MUTATION_COMMITTED":
            if index not in prepared or index in committed:
                raise RecoveryEvidenceUnavailable("RECOVERY_COMMIT_ORDER_INVALID")
            if (row.get("job_id") != job_id or row.get("session_id") != workflow["session_id"]
                    or row.get("revision_before") != prepared[index].get("revision_before")
                    or row.get("revision_after") != prepared[index].get("revision_before", -2) + 1
                    or row.get("state_epoch") != prepared[index].get("state_epoch")):
                raise RecoveryEvidenceUnavailable("RECOVERY_COMMIT_AUTHORITY_MISMATCH")
            committed.add(index)
        else:
            ambiguous.add(index)
    unresolved = sorted((set(prepared) - committed) | ambiguous)
    result_path = ui_dir / "result.json"
    try:
        result = _json(result_path)
    except FileNotFoundError:
        result = None
    if result is not None and (result.get("job_id") != job_id
                               or result.get("session_id") != workflow["session_id"]):
        raise RecoveryEvidenceUnavailable("RECOVERY_RESULT_IDENTITY_MISMATCH")
    terminal = result.get("status") if result else None
    # A committed journal row alone is not a checkpoint/driver proof. The
    # inspector does not infer permission to resume even for PASS receipts.
    reasons = []
    if unresolved:
        reasons.append("PREPARED_MUTATION_UNRESOLVED")
    if result is None:
        reasons.append("RESULT_MISSING")
    elif terminal == "RECONCILE_REQUIRED":
        reasons.append("RESULT_REQUIRES_RECONCILIATION")
    elif terminal != "PASS":
        reasons.append("RESULT_NOT_SUCCESSFUL")
    if prepared and (checkpoint.get("safe_to_resume") is not True
                     or completed < max(prepared)):
        reasons.append("CHECKPOINT_BEHIND_MUTATION")
    return {
        "status": "READ_ONLY_RECOVERY_INSPECTION",
        "job_id": job_id,
        "session_id": workflow["session_id"],
        "result_status": terminal,
        "prepared_action_indices": sorted(prepared),
        "committed_action_indices": sorted(committed),
        "unresolved_action_indices": unresolved,
        "checkpoint_completed_index": completed,
        "reason_codes": reasons,
        "safe_to_resume": False,
        "replay_allowed": False,
        "claim_release_allowed": False,
        "android_actions_dispatched": 0,
    }
