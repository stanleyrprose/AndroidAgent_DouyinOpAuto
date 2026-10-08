#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

RUNTIME = Path(os.environ.get("Y700_RUNTIME", "/opt/y700/runtime"))
LOCK_PATH = RUNTIME / "android-ui.lock"
CLAIM_PATH = RUNTIME / "android-ui.claim.json"
AUDIT_PATH = RUNTIME / "android-ui.claim-journal.jsonl"


class ResourceError(RuntimeError):
    pass


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _ensure_runtime() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(RUNTIME, 0o700)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _ensure_runtime()
    tmp = path.with_name(path.name + ".tmp-" + secrets.token_hex(4))
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with open(tmp, "wb") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    _fsync_dir(path.parent)


def _append_audit(row: dict[str, Any]) -> None:
    _ensure_runtime()
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat()


def _boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ResourceError("RESOURCE_STATE_INTEGRITY_FAILURE: boot_id unavailable") from exc


def _proc_start_ticks(pid: int) -> int:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        # comm may contain spaces and parentheses. Field 22 is the 20th token
        # after the closing ') ' prefix.
        tail = raw.rsplit(") ", 1)[1].split()
        return int(tail[19])
    except (OSError, ValueError, IndexError) as exc:
        raise ResourceError("RESOURCE_STATE_INTEGRITY_FAILURE: proc identity unavailable") from exc


def read_claim() -> dict[str, Any] | None:
    try:
        value = json.loads(CLAIM_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceError("RESOURCE_STATE_INTEGRITY_FAILURE: invalid durable claim") from exc
    if not isinstance(value, dict):
        raise ResourceError("RESOURCE_STATE_INTEGRITY_FAILURE: invalid durable claim")
    return value


def _lineage(owner_id: str) -> tuple[int, str | None]:
    generation = 0
    prior: str | None = None
    try:
        rows = AUDIT_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return 1, None
    except OSError as exc:
        raise ResourceError("RESOURCE_STATE_INTEGRITY_FAILURE: claim audit unreadable") from exc
    for line in rows:
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ResourceError("RESOURCE_STATE_INTEGRITY_FAILURE: claim audit corrupt") from exc
        if row.get("owner_id") == owner_id and row.get("phase") in {"RESOURCE_ACQUIRED", "RESOURCE_REACQUIRED"}:
            generation = max(generation, int(row.get("claim_generation", 0)))
            cid = row.get("claim_id")
            if isinstance(cid, str) and cid:
                prior = cid
    return generation + 1, prior


def request_identity(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass
class ResourceGuard:
    resource: str
    claim_id: str
    owner_id: str
    retained_for_reconcile: bool = False

    def as_dict(self) -> dict[str, str]:
        return {
            "resource": self.resource,
            "claim_id": self.claim_id,
            "owner_id": self.owner_id,
        }

    def bind_active_execution(self, *, ui_job_id: str, session_id: str) -> None:
        bind_active_execution(
            self.as_dict(),
            ui_job_id=ui_job_id,
            session_id=session_id,
        )

    def clear_active_execution(self, *, ui_job_id: str) -> None:
        clear_active_execution(self.as_dict(), ui_job_id=ui_job_id)

    def retain_for_reconcile(self, reason: str = "LIVENESS_UNKNOWN") -> None:
        mark_reconcile_required(self.as_dict(), reason=reason)
        self.retained_for_reconcile = True


def assert_guard(guard: Any) -> dict[str, Any]:
    if not isinstance(guard, dict):
        raise ResourceError("RESOURCE_OWNERSHIP_REQUIRED")
    if not guard.get("claim_id") or not guard.get("owner_id"):
        raise ResourceError("RESOURCE_OWNERSHIP_REQUIRED")
    if guard.get("resource") != "android_ui":
        raise ResourceError("RESOURCE_OWNERSHIP_MISMATCH")
    current = read_claim()
    if current is None:
        raise ResourceError("RESOURCE_OWNERSHIP_REQUIRED")
    if (
        current.get("resource") != "android_ui"
        or current.get("claim_id") != guard.get("claim_id")
        or current.get("owner_id") != guard.get("owner_id")
    ):
        raise ResourceError("RESOURCE_OWNERSHIP_MISMATCH")
    return current


def bind_active_execution(
    guard: dict[str, Any],
    *,
    ui_job_id: str,
    session_id: str,
) -> dict[str, Any]:
    if not isinstance(ui_job_id, str) or not ui_job_id:
        raise ResourceError("RESOURCE_BACKEND_BINDING_INVALID: ui_job_id")
    if not isinstance(session_id, str) or not session_id:
        raise ResourceError("RESOURCE_BACKEND_BINDING_INVALID: session_id")
    current = assert_guard(guard)
    updated = dict(current)
    updated["active_ui_job_id"] = ui_job_id
    updated["active_session_id"] = session_id
    updated["active_backend_type"] = "ui_job"
    updated["active_bound_at"] = _now_iso()
    _atomic_json(CLAIM_PATH, updated)
    _append_audit({
        "timestamp": _now_iso(),
        "phase": "RESOURCE_BACKEND_BOUND",
        "claim_id": updated["claim_id"],
        "claim_generation": updated.get("claim_generation"),
        "owner_id": updated.get("owner_id"),
        "ui_job_id": ui_job_id,
        "session_id": session_id,
    })
    return updated


def clear_active_execution(
    guard: dict[str, Any],
    *,
    ui_job_id: str,
) -> dict[str, Any]:
    current = assert_guard(guard)
    active = current.get("active_ui_job_id")
    if active not in {None, ui_job_id}:
        raise ResourceError("RESOURCE_BACKEND_BINDING_MISMATCH")
    updated = dict(current)
    for key in (
        "active_ui_job_id",
        "active_session_id",
        "active_backend_type",
        "active_bound_at",
    ):
        updated.pop(key, None)
    _atomic_json(CLAIM_PATH, updated)
    _append_audit({
        "timestamp": _now_iso(),
        "phase": "RESOURCE_BACKEND_CLEARED",
        "claim_id": updated["claim_id"],
        "claim_generation": updated.get("claim_generation"),
        "owner_id": updated.get("owner_id"),
        "ui_job_id": ui_job_id,
    })
    return updated


def mark_reconcile_required(
    guard: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    current = assert_guard(guard)
    updated = dict(current)
    updated["reconcile_required"] = True
    updated["reconcile_reason"] = str(reason)[:256]
    updated["reconcile_marked_at"] = _now_iso()
    _atomic_json(CLAIM_PATH, updated)
    _append_audit({
        "timestamp": _now_iso(),
        "phase": "RESOURCE_RECONCILE_REQUIRED",
        "claim_id": updated["claim_id"],
        "claim_generation": updated.get("claim_generation"),
        "owner_id": updated.get("owner_id"),
        "active_ui_job_id": updated.get("active_ui_job_id"),
        "active_session_id": updated.get("active_session_id"),
        "reason": updated["reconcile_reason"],
    })
    return updated


def _acquire_flock(fd: int, timeout_sec: float) -> None:
    deadline = time.monotonic() + max(0.0, timeout_sec)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError as exc:
            if time.monotonic() >= deadline:
                raise ResourceError("DEVICE_BUSY") from exc
            time.sleep(0.05)


@contextmanager
def acquire_android_ui(
    *,
    owner_kind: str,
    owner_id: str,
    backend_type: str,
    backend_job_id: str,
    request_sha256: str,
    capability_job_id: str | None = None,
    timeout_sec: float = 0.0,
) -> Iterator[ResourceGuard]:
    if owner_kind not in {"LEGACY", "CAPABILITY", "ADMIN"}:
        raise ResourceError("RESOURCE_OWNER_KIND_INVALID")
    if owner_kind == "CAPABILITY" and not capability_job_id:
        raise ResourceError("CAPABILITY_JOB_ID_REQUIRED")
    for name, value in {
        "owner_id": owner_id,
        "backend_type": backend_type,
        "backend_job_id": backend_job_id,
        "request_sha256": request_sha256,
    }.items():
        if not isinstance(value, str) or not value:
            raise ResourceError(f"RESOURCE_CLAIM_INVALID: {name}")

    _ensure_runtime()
    fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    os.chmod(LOCK_PATH, 0o600)
    claim_id: str | None = None
    guard: ResourceGuard | None = None
    try:
        _acquire_flock(fd, timeout_sec)
        current = read_claim()
        if current is not None:
            raise ResourceError("RESOURCE_RECONCILE_REQUIRED")

        generation, prior = _lineage(owner_id)
        claim_id = "ui-claim-" + secrets.token_hex(16)
        phase = "RESOURCE_REACQUIRED" if prior is not None else "RESOURCE_ACQUIRED"
        claim = {
            "claim_version": 1,
            "claim_id": claim_id,
            "claim_generation": generation,
            "prior_claim_id": prior,
            "resource": "android_ui",
            "owner_kind": owner_kind,
            "owner_id": owner_id,
            "capability_job_id": capability_job_id,
            "backend_type": backend_type,
            "backend_job_id": backend_job_id,
            "request_sha256": request_sha256,
            "owner": {
                "boot_id": _boot_id(),
                "pid": os.getpid(),
                "proc_start_ticks": _proc_start_ticks(os.getpid()),
            },
            "acquired_at": _now_iso(),
        }
        _atomic_json(CLAIM_PATH, claim)
        _append_audit({
            "timestamp": _now_iso(),
            "phase": phase,
            "claim_id": claim_id,
            "claim_generation": generation,
            "prior_claim_id": prior,
            "owner_kind": owner_kind,
            "owner_id": owner_id,
            "backend_type": backend_type,
            "backend_job_id": backend_job_id,
            "capability_job_id": capability_job_id,
            "request_sha256": request_sha256,
        })
        guard = ResourceGuard("android_ui", claim_id, owner_id)
        yield guard
    finally:
        if (
            claim_id is not None
            and guard is not None
            and not guard.retained_for_reconcile
        ):
            # The top-level synchronous owner may release only its exact claim.
            # A coordinator crash or explicit ambiguous-outcome retention leaves
            # the durable claim behind for explicit reconcile.
            current = read_claim()
            if current is not None and current.get("claim_id") == claim_id:
                _append_audit({
                    "timestamp": _now_iso(),
                    "phase": "RESOURCE_RELEASED",
                    "claim_id": claim_id,
                    "claim_generation": current.get("claim_generation"),
                    "owner_kind": current.get("owner_kind"),
                    "owner_id": current.get("owner_id"),
                    "backend_type": current.get("backend_type"),
                    "backend_job_id": current.get("backend_job_id"),
                })
                CLAIM_PATH.unlink()
                _fsync_dir(CLAIM_PATH.parent)
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
