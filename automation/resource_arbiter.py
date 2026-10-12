#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import stat
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
    """Never chmod/follow an untrusted Runtime symlink or parent inode."""
    if RUNTIME.is_symlink():
        raise ResourceError("RESOURCE_RUNTIME_SYMLINK_UNTRUSTED")
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = os.lstat(RUNTIME)
    if (not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ResourceError("RESOURCE_RUNTIME_OWNER_OR_MODE_UNTRUSTED")


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _ensure_runtime()
    tmp = path.with_name(path.name + ".tmp-" + secrets.token_hex(4))
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if not hasattr(os, "O_NOFOLLOW"):
        raise ResourceError("RESOURCE_NOFOLLOW_UNAVAILABLE")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        _ensure_runtime()
        try:
            existing = os.lstat(path)
        except FileNotFoundError:
            existing = None
        if existing is not None and (
                not stat.S_ISREG(existing.st_mode)
                or existing.st_uid != os.geteuid()
                or existing.st_nlink != 1
                or stat.S_IMODE(existing.st_mode) != 0o600):
            raise ResourceError("RESOURCE_CLAIM_TARGET_UNTRUSTED")
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def _append_audit(row: dict[str, Any]) -> None:
    """Append-only audit under root-owned no-follow file, no silent chmod."""
    _ensure_runtime()
    raw = (json.dumps(
        row, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > 8192:
        raise ResourceError("RESOURCE_AUDIT_ENTRY_OVERSIZE")
    try:
        fd = os.open(
            AUDIT_PATH, os.O_WRONLY | os.O_APPEND | os.O_CREAT
            | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except OSError as exc:
        raise ResourceError("RESOURCE_AUDIT_UNAVAILABLE") from exc
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode)
                or meta.st_uid != os.geteuid()
                or meta.st_nlink != 1
                or stat.S_IMODE(meta.st_mode) != 0o600):
            raise ResourceError("RESOURCE_AUDIT_UNTRUSTED")
        remaining = memoryview(raw)
        while remaining:
            n = os.write(fd, remaining)
            if n <= 0:
                raise ResourceError("RESOURCE_AUDIT_SHORT_WRITE")
            remaining = remaining[n:]
        os.fsync(fd)
    finally:
        os.close(fd)


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
    """Fail-closed owner-protected exact Claim SOT, no implicit repair.

    Missing regular file means no claim; unreadable, symlink, non-root,
    group-writable, truncated or concurrently changed claim is corruption,
    NEVER an available resource.
    """
    def _unique(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise ResourceError(
                    "RESOURCE_STATE_INTEGRITY_FAILURE: duplicate claim key")
            out[key] = value
        return out
    # A missing runtime ROOT is never proof that android_ui is free.
    # Only ENOENT for the exact claim file under an already authenticated
    # owner-protected runtime directory may mean no durable Claim.
    try:
        directory = os.lstat(RUNTIME)
    except OSError as exc:
        raise ResourceError(
            "RESOURCE_STATE_INTEGRITY_FAILURE: runtime root unavailable") from exc
    if (not stat.S_ISDIR(directory.st_mode)
            or directory.st_uid != os.geteuid()
            or stat.S_IMODE(directory.st_mode) != 0o700):
        raise ResourceError(
            "RESOURCE_STATE_INTEGRITY_FAILURE: runtime root untrusted")
    if not hasattr(os, "O_NOFOLLOW"):
        raise ResourceError("RESOURCE_STATE_INTEGRITY_FAILURE: nofollow unavailable")
    try:
        fd = os.open(
            CLAIM_PATH,
            os.O_RDONLY | os.O_NOFOLLOW,
        )
    except FileNotFoundError as exc:
        if exc.filename != str(CLAIM_PATH):
            raise ResourceError(
                "RESOURCE_STATE_INTEGRITY_FAILURE: claim parent unavailable") from exc
        return None
    except OSError as exc:
        raise ResourceError(
            "RESOURCE_STATE_INTEGRITY_FAILURE: claim unreadable") from exc
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_uid != 0
                or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o600
                or not 0 < before.st_size <= 8192):
            raise ResourceError(
                "RESOURCE_STATE_INTEGRITY_FAILURE: claim untrusted")
        raw = bytearray()
        while len(raw) <= 8192:
            part = os.read(fd, min(4096, 8193 - len(raw)))
            if not part:
                break
            raw.extend(part)
        after = os.fstat(fd)
        try:
            current = os.stat(CLAIM_PATH, follow_symlinks=False)
            runtime_after = os.lstat(RUNTIME)
        except OSError as exc:
            raise ResourceError("RESOURCE_STATE_INTEGRITY_FAILURE: claim path changed") from exc
        if ((directory.st_dev, directory.st_ino) != (runtime_after.st_dev, runtime_after.st_ino)
                or (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns)
                != (current.st_dev, current.st_ino, current.st_size,
                    current.st_mtime_ns, current.st_ctime_ns)
                or not stat.S_ISREG(current.st_mode)
                or len(raw) != before.st_size
                or (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns)):
            raise ResourceError(
                "RESOURCE_STATE_INTEGRITY_FAILURE: claim changed")
        try:
            value = json.loads(raw, object_pairs_hook=_unique)
        except (ValueError, UnicodeError) as exc:
            raise ResourceError(
                "RESOURCE_STATE_INTEGRITY_FAILURE: claim malformed") from exc
        if (not isinstance(value, dict)
                or value.get("claim_version") != 1
                or value.get("resource") != "android_ui"
                or not isinstance(value.get("claim_id"), str)
                or not value["claim_id"].startswith("ui-claim-")):
            raise ResourceError(
                "RESOURCE_STATE_INTEGRITY_FAILURE: claim invalid")
        return value
    finally:
        os.close(fd)


def _lineage(owner_id: str) -> tuple[int, str | None]:
    """Bounded append-only Claim history, with no-follow and exact inode.

    A tampered, oversized or partially written journal must never grant
    a fresh claim generation. Maintenance/rotation needs an independent
    accepted snapshot protocol; silently truncating history is forbidden.
    """
    maximum = 32 * 1024 * 1024
    if not hasattr(os, "O_NOFOLLOW"):
        raise ResourceError("RESOURCE_STATE_INTEGRITY_FAILURE: nofollow unavailable")
    try:
        fd = os.open(
            AUDIT_PATH,
            os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return 1, None
    except OSError as exc:
        raise ResourceError(
            "RESOURCE_STATE_INTEGRITY_FAILURE: claim audit unreadable") from exc
    try:
        first = os.fstat(fd)
        if (not stat.S_ISREG(first.st_mode)
                or first.st_uid != os.geteuid()
                or first.st_nlink != 1
                or stat.S_IMODE(first.st_mode) != 0o600
                or first.st_size > maximum):
            raise ResourceError(
                "RESOURCE_STATE_INTEGRITY_FAILURE: claim audit untrusted")
        data = bytearray()
        while len(data) <= maximum:
            part = os.read(fd, min(32768, maximum + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        last = os.fstat(fd)
        try:
            current = os.stat(AUDIT_PATH, follow_symlinks=False)
        except OSError as exc:
            raise ResourceError("RESOURCE_STATE_INTEGRITY_FAILURE: claim audit path changed") from exc
        if ((first.st_dev, first.st_ino, first.st_size,
             first.st_mtime_ns, first.st_ctime_ns)
                != (current.st_dev, current.st_ino, current.st_size,
                    current.st_mtime_ns, current.st_ctime_ns)
                or not stat.S_ISREG(current.st_mode)
                or len(data) != first.st_size
                or (first.st_dev, first.st_ino, first.st_size,
                    first.st_mtime_ns, first.st_ctime_ns)
                != (last.st_dev, last.st_ino, last.st_size,
                    last.st_mtime_ns, last.st_ctime_ns)):
            raise ResourceError(
                "RESOURCE_STATE_INTEGRITY_FAILURE: claim audit changed")
    finally:
        os.close(fd)
    if data and not data.endswith(b"\n"):
        raise ResourceError(
            "RESOURCE_STATE_INTEGRITY_FAILURE: claim audit truncated")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        record: dict[str, Any] = {}
        for key, value in pairs:
            if key in record:
                raise ResourceError(
                    "RESOURCE_STATE_INTEGRITY_FAILURE: duplicate audit key")
            record[key] = value
        return record
    generation = 0
    prior: str | None = None
    seen_generations: dict[int, str] = {}
    try:
        for line in bytes(data).splitlines():
            row = json.loads(line, object_pairs_hook=unique)
            if not isinstance(row, dict):
                raise ResourceError(
                    "RESOURCE_STATE_INTEGRITY_FAILURE: invalid audit row")
            if (row.get("owner_id") == owner_id
                    and row.get("phase") in {
                        "RESOURCE_ACQUIRED", "RESOURCE_REACQUIRED"}):
                value = row.get("claim_generation")
                if type(value) is not int or value <= 0:
                    raise ResourceError(
                        "RESOURCE_STATE_INTEGRITY_FAILURE: invalid lineage")
                cid = row.get("claim_id")
                if not isinstance(cid, str) or not cid:
                    raise ResourceError(
                        "RESOURCE_STATE_INTEGRITY_FAILURE: invalid claim ID")
                previous = seen_generations.get(value)
                if previous is not None and previous != cid:
                    raise ResourceError(
                        "RESOURCE_STATE_INTEGRITY_FAILURE: lineage conflict")
                seen_generations[value] = cid
                if value > generation:
                    generation = value
                    prior = cid
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ResourceError(
            "RESOURCE_STATE_INTEGRITY_FAILURE: claim audit corrupt") from exc
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
    # Under the canonical owner, no second subordinate may overwrite an
    # existing active execution or erase a retained uncertainty marker.
    # The exact same UI Job ID is NOT an idempotent nested submission:
    # recovery must inspect the original durable receipt instead.
    if (current.get("reconcile_required") is True
            or current.get("active_ui_job_id") is not None
            or current.get("active_session_id") is not None
            or current.get("active_backend_type") is not None):
        raise ResourceError("RESOURCE_ACTIVE_EXECUTION_ALREADY_BOUND")
    previous_generation = current.get("ui_execution_generation")
    if type(previous_generation) is not int or not 0 <= previous_generation < 2147483647:
        raise ResourceError("RESOURCE_UI_EXECUTION_GENERATION_INVALID")
    updated = dict(current)
    updated["ui_execution_generation"] = previous_generation + 1
    updated["active_ui_job_id"] = ui_job_id
    updated["active_session_id"] = session_id
    updated["active_backend_type"] = "ui_job"
    updated["active_bound_at"] = _now_iso()
    _atomic_json(CLAIM_PATH, updated)
    _append_audit({
        "timestamp": _now_iso(),
        "phase": "RESOURCE_BACKEND_BOUND",
        "claim_id": updated["claim_id"],
        "ui_execution_generation": updated["ui_execution_generation"],
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
    # A missing active marker is NOT permission to pretend cleanup
    # succeeded. The exact original subjob identity must still be live
    # and belong to this Claim.
    if (active != ui_job_id
            or current.get("reconcile_required") is True
            or not isinstance(current.get("active_session_id"), str)
            or not current["active_session_id"]
            or current.get("active_backend_type") != "ui_job"):
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
        "ui_execution_generation": updated.get("ui_execution_generation"),
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
    try:
        fd = os.open(
            LOCK_PATH, os.O_CREAT | os.O_RDWR
            | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except OSError as exc:
        raise ResourceError("RESOURCE_LOCK_UNAVAILABLE") from exc
    metadata = os.fstat(fd)
    if (not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600):
        os.close(fd)
        raise ResourceError("RESOURCE_LOCK_OWNER_OR_MODE_UNTRUSTED")
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
            # Bumped at EVERY subordinate bind. A native stop receipt
            # from a preceding subjob cannot release a later generation.
            "ui_execution_generation": 0,
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
        try:
            if (
                claim_id is not None
                and guard is not None
                and not guard.retained_for_reconcile
            ):
                # A corrupt/replaced claim must remain in place for explicit
                # reconciliation. Never silently clear another owner's SOT.
                # The outer finally MUST still release the kernel flock
                # after any read, audit, unlink or fsync failure.
                current = read_claim()
                if current is not None and current.get("claim_id") == claim_id:
                    # A Python scope exiting is NOT proof that the native
                    # Driver and UI Core descendants have stopped. Preserve
                    # the durable Claim on an active/ambiguous subordinate
                    # even when its caller forgot to call retain_for_reconcile.
                    unfinished = (
                        current.get("active_ui_job_id") is not None
                        or current.get("active_session_id") is not None
                        or current.get("active_backend_type") is not None
                        or current.get("reconcile_required") is True
                    )
                    if unfinished:
                        guard.retained_for_reconcile = True
                        if current.get("reconcile_required") is not True:
                            mark_reconcile_required(
                                guard.as_dict(),
                                reason="LEASE_EXIT_WITH_UNFINISHED_UI_MUTATOR",
                            )
                    else:
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
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
