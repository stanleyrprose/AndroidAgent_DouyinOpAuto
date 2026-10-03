#!/usr/bin/env python3
"""Bridge v2 filesystem client for the Y700 Android host executor.

The filesystem is the durable source of truth. This module intentionally
contains no socket/MQ transport and can be used both as a Python API and CLI.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import fcntl
import json
import os
import re
import secrets
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = 2
JOB_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,96}$")
RESERVED_JOB_IDS = {"active", "archive", "control", ".staging"}
TERMINAL_CLASSES = ("succeeded", "failed", "cancelled", "reconcile_required")
TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELLED", "RECONCILE_REQUIRED"}
REQUEST_MAX_BYTES = int(os.environ.get("Y700_BRIDGE_REQUEST_MAX_BYTES", 256 * 1024))
CANCEL_MAX_BYTES = int(os.environ.get("Y700_BRIDGE_CANCEL_MAX_BYTES", 16 * 1024))
STATE_MAX_BYTES = int(os.environ.get("Y700_BRIDGE_STATE_MAX_BYTES", 64 * 1024))
JOURNAL_ROW_MAX_BYTES = int(os.environ.get("Y700_BRIDGE_JOURNAL_ROW_MAX_BYTES", 64 * 1024))
MIN_FREE_MB = int(os.environ.get("Y700_MIN_FREE_MB", 5120))
STATUS_GRACE_SECONDS = float(os.environ.get("Y700_BRIDGE_STATUS_GRACE_SECONDS", "0.1"))


class BridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class BridgePaths:
    jobs: Path
    runtime: Path

    @classmethod
    def from_env(cls) -> "BridgePaths":
        return cls(
            jobs=Path(os.environ.get("Y700_BRIDGE_JOBS", "/opt/y700/jobs")),
            runtime=Path(os.environ.get("Y700_RUNTIME", "/opt/y700/runtime")),
        )

    @property
    def staging(self) -> Path:
        return self.jobs / ".staging"

    @property
    def active(self) -> Path:
        return self.jobs / "active"

    @property
    def archive(self) -> Path:
        return self.jobs / "archive"

    @property
    def control(self) -> Path:
        return self.jobs / "control"

    @property
    def legacy_history(self) -> Path:
        return self.runtime / "job-history"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ensure_dir(path: Path, mode: int = 0o700) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    os.chmod(path, mode)


def atomic_write(path: Path, data: bytes, *, mode: int = 0o600, max_bytes: int | None = None) -> None:
    if max_bytes is not None and len(data) > max_bytes:
        raise BridgeError(f"payload too large for {path.name}: {len(data)} > {max_bytes}")
    ensure_dir(path.parent)
    tmp = path.parent / f".{path.name}.tmp-{os.getpid()}-{secrets.token_hex(4)}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb", closefd=False) as f:
            f.write(data)
            f.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
    fsync_dir(path.parent)


def atomic_json(path: Path, obj: Any, *, max_bytes: int = STATE_MAX_BYTES) -> None:
    raw = (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    atomic_write(path, raw, max_bytes=max_bytes)


def read_json(path: Path, *, max_bytes: int = STATE_MAX_BYTES) -> Any:
    size = path.stat().st_size
    if size > max_bytes:
        raise BridgeError(f"oversized JSON: {path} ({size} bytes)")
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BridgeError(f"malformed durable JSON: {path}: {exc}") from exc


def append_journal(path: Path, row: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    raw = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    if len(raw) > JOURNAL_ROW_MAX_BYTES:
        raise BridgeError("journal row too large")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, raw)
        os.fsync(fd)
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def validate_job_id(job_id: str) -> str:
    if (
        not JOB_ID_RE.fullmatch(job_id)
        or job_id in {".", ".."}
        or job_id in RESERVED_JOB_IDS
    ):
        raise BridgeError("invalid job_id")
    return job_id


def ensure_layout(paths: BridgePaths) -> None:
    for path in (paths.jobs, paths.staging, paths.active, paths.archive, paths.control, paths.runtime):
        ensure_dir(path)
    for cls in TERMINAL_CLASSES:
        ensure_dir(paths.archive / cls)


def check_disk_guard(paths: BridgePaths) -> None:
    usage = shutil.disk_usage(paths.jobs)
    free_mb = usage.free // (1024 * 1024)
    free_pct = int(usage.free * 100 / usage.total) if usage.total else 0
    if free_mb < MIN_FREE_MB or free_pct < 5:
        raise BridgeError(
            f"DISK_GUARD_BLOCKED free_mb={free_mb} free_percent={free_pct} min_free_mb={MIN_FREE_MB}"
        )


def make_job_id(prefix: str = "root") -> str:
    return f"{prefix}-{time.time_ns() // 1_000_000}-{secrets.token_hex(4)}"


def submit_root(
    command: str,
    *,
    timeout_ms: int = 90_000,
    job_id: str | None = None,
    paths: BridgePaths | None = None,
    retry_of: str | None = None,
) -> str:
    paths = paths or BridgePaths.from_env()
    ensure_layout(paths)
    check_disk_guard(paths)
    if not command:
        raise BridgeError("command must not be empty")
    if not 1_000 <= timeout_ms <= 3_600_000:
        raise BridgeError("timeout_ms out of range")
    job_id = validate_job_id(job_id or make_job_id())
    if retry_of is not None:
        validate_job_id(retry_of)

    stage = paths.staging / job_id
    active = paths.active / job_id
    occupied = [stage, active]
    occupied.extend(paths.archive / cls / job_id for cls in TERMINAL_CLASSES)
    occupied.extend([paths.jobs / job_id, paths.legacy_history / job_id])
    if any(p.exists() or p.is_symlink() for p in occupied):
        raise BridgeError("job already exists")
    stage.mkdir(mode=0o700)
    os.chmod(stage, 0o700)
    ensure_dir(stage / "artifacts")

    request: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "job_id": job_id,
        "action": "root_exec",
        "created_at": now_iso(),
        "created_monotonic_ms": round(time.monotonic() * 1000),
        "timeout_ms": int(timeout_ms),
        "execution_policy": {
            "replay": "NEVER",
            "cancellation": "BEFORE_START_OR_COOPERATIVE",
        },
        "payload": {"command_b64": base64.b64encode(command.encode()).decode()},
    }
    if retry_of:
        request["retry_of"] = retry_of
    request_raw = (json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    if len(request_raw) > REQUEST_MAX_BYTES:
        shutil.rmtree(stage, ignore_errors=True)
        raise BridgeError(f"JOB_PAYLOAD_TOO_LARGE: {len(request_raw)} > {REQUEST_MAX_BYTES}")

    try:
        atomic_write(stage / "request.json", request_raw, max_bytes=REQUEST_MAX_BYTES)
        atomic_json(
            stage / "state.json",
            {
                "protocol_version": PROTOCOL_VERSION,
                "job_id": job_id,
                "state": "QUEUED",
                "updated_at": now_iso(),
                "attempt": 0,
                "cancel_requested": False,
            },
        )
        append_journal(
            stage / "journal.jsonl",
            {"timestamp": now_iso(), "event": "JOB_CREATED", "job_id": job_id, "protocol_version": 2},
        )
        fsync_dir(stage)
        os.replace(stage, active)
        fsync_dir(paths.active)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise
    return job_id


def _v2_candidates(paths: BridgePaths, job_id: str) -> list[Path]:
    return [paths.archive / cls / job_id for cls in TERMINAL_CLASSES] + [paths.active / job_id]


def locate_job(
    job_id: str,
    *,
    paths: BridgePaths | None = None,
    include_v1: bool = True,
) -> tuple[Path, int] | None:
    paths = paths or BridgePaths.from_env()
    validate_job_id(job_id)
    for attempt in range(2):
        for candidate in _v2_candidates(paths, job_id):
            if candidate.is_symlink():
                raise BridgeError(f"SYMLINK_JOB_ROOT: {candidate}")
            if candidate.is_dir():
                return candidate, 2
        if attempt == 0:
            time.sleep(STATUS_GRACE_SECONDS)

    if include_v1:
        direct = paths.jobs / job_id
        if direct.is_symlink():
            raise BridgeError(f"SYMLINK_JOB_ROOT: {direct}")
        if direct.is_dir():
            return direct, 1
        legacy = paths.legacy_history / job_id
        if legacy.is_symlink():
            raise BridgeError(f"SYMLINK_JOB_ROOT: {legacy}")
        if legacy.is_dir():
            return legacy, 1
    return None


def status(job_id: str, *, paths: BridgePaths | None = None) -> dict[str, Any]:
    paths = paths or BridgePaths.from_env()
    validate_job_id(job_id)
    for _ in range(3):
        located = locate_job(job_id, paths=paths)
        if located is None:
            raise BridgeError("JOB_NOT_FOUND")
        directory, version = located
        try:
            if version == 2:
                state = read_json(directory / "state.json")
                result = read_json(directory / "result.json") if (directory / "result.json").exists() else None
                heartbeat = read_json(directory / "heartbeat.json") if (directory / "heartbeat.json").exists() else None
                owner = (
                    read_json(directory / "claim" / "owner.json")
                    if (directory / "claim" / "owner.json").exists()
                    else None
                )
                return {
                    "protocol_version": 2,
                    "job_id": job_id,
                    "location": str(directory),
                    "state": state,
                    "result": result,
                    "heartbeat": heartbeat,
                    "owner": owner,
                }

            state = read_json(directory / "state.json") if (directory / "state.json").exists() else {}
            result = read_json(directory / "result.json") if (directory / "result.json").exists() else None
            return {
                "protocol_version": 1,
                "job_id": job_id,
                "location": str(directory),
                "state": state,
                "result": result,
            }
        except FileNotFoundError:
            time.sleep(STATUS_GRACE_SECONDS)
    raise BridgeError("JOB_LOOKUP_RACE")


def terminal_status(snapshot: dict[str, Any]) -> str | None:
    result = snapshot.get("result") or {}
    value = result.get("status")
    if value in TERMINAL_STATES:
        return value
    state = snapshot.get("state") or {}
    value = state.get("state") or state.get("status")
    return value if value in TERMINAL_STATES else None


def cancel(
    job_id: str,
    *,
    reason: str = "user_requested",
    paths: BridgePaths | None = None,
) -> dict[str, Any]:
    paths = paths or BridgePaths.from_env()
    validate_job_id(job_id)
    located = locate_job(job_id, paths=paths)
    if located is None:
        raise BridgeError("JOB_NOT_FOUND")
    directory, version = located
    if version != 2:
        raise BridgeError("CANCEL_UNSUPPORTED_FOR_V1")
    snap = status(job_id, paths=paths)
    if terminal_status(snap) or directory.parent != paths.active:
        return snap

    payload = {
        "protocol_version": 2,
        "requested_at": now_iso(),
        "requested_by": "controller",
        "reason": str(reason)[:256],
    }
    atomic_json(directory / "cancel.json", payload, max_bytes=CANCEL_MAX_BYTES)
    append_journal(
        directory / "journal.jsonl",
        {"timestamp": now_iso(), "event": "CANCEL_REQUESTED", "reason": payload["reason"]},
    )
    return status(job_id, paths=paths)


def wait(
    job_id: str,
    *,
    timeout: float | None = None,
    poll: float = 0.2,
    paths: BridgePaths | None = None,
) -> dict[str, Any]:
    paths = paths or BridgePaths.from_env()
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        snap = status(job_id, paths=paths)
        if terminal_status(snap):
            return snap
        if deadline is not None and time.monotonic() >= deadline:
            raise BridgeError("WAIT_TIMEOUT")
        time.sleep(max(0.05, poll))


def request_reconcile(job_id: str | None = None, *, paths: BridgePaths | None = None) -> dict[str, Any]:
    paths = paths or BridgePaths.from_env()
    ensure_layout(paths)
    target = "all" if job_id is None else validate_job_id(job_id)
    payload = {"protocol_version": 2, "requested_at": now_iso(), "target": target}
    atomic_json(paths.control / "reconcile.request", payload, max_bytes=CANCEL_MAX_BYTES)
    return payload


def _safe_control_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return read_json(path)
    except BridgeError as exc:
        return {"status": "CORRUPT", "error": str(exc)}


def health(*, paths: BridgePaths | None = None) -> dict[str, Any]:
    paths = paths or BridgePaths.from_env()
    ensure_layout(paths)
    staging_count = 0
    staging_bytes = 0
    for entry in paths.staging.iterdir():
        if entry.is_symlink() or not entry.is_dir():
            continue
        staging_count += 1
        for root, _dirs, files in os.walk(entry):
            for name in files:
                try:
                    staging_bytes += (Path(root) / name).stat().st_size
                except FileNotFoundError:
                    pass
    active_count = sum(1 for p in paths.active.iterdir() if p.is_dir() and not p.is_symlink())
    usage = shutil.disk_usage(paths.jobs)
    return {
        "protocol_version": 2,
        "executor": _safe_control_json(paths.control / "executor.json"),
        "protocol": _safe_control_json(paths.control / "protocol.json"),
        "metrics": _safe_control_json(paths.control / "metrics.json"),
        "active_job_count_observed": active_count,
        "staging_job_count": staging_count,
        "staging_bytes": staging_bytes,
        "disk_free_mb": usage.free // (1024 * 1024),
        "disk_free_percent": int(usage.free * 100 / usage.total) if usage.total else 0,
    }


def cleanup_staging(*, ttl_seconds: int = 86_400, paths: BridgePaths | None = None) -> dict[str, Any]:
    paths = paths or BridgePaths.from_env()
    ensure_layout(paths)
    now = time.time()
    removed: list[str] = []
    for entry in paths.staging.iterdir():
        if entry.is_symlink() or not entry.is_dir() or not JOB_ID_RE.fullmatch(entry.name):
            continue
        try:
            age = now - entry.stat().st_mtime
        except FileNotFoundError:
            continue
        if age < ttl_seconds:
            continue
        shutil.rmtree(entry)
        removed.append(entry.name)
        append_journal(
            paths.control / "maintenance.jsonl",
            {
                "timestamp": now_iso(),
                "event": "STALE_STAGING_REMOVED",
                "job_id": entry.name,
                "age_seconds": int(age),
            },
        )
    if removed:
        fsync_dir(paths.staging)
    return {"removed": removed, "ttl_seconds": ttl_seconds}


def emit_job_logs(snapshot: dict[str, Any]) -> None:
    directory = Path(snapshot["location"])
    out = directory / "stdout.log"
    err = directory / "stderr.log"
    if out.exists():
        sys.stdout.write(out.read_text(encoding="utf-8", errors="replace"))
    if err.exists():
        sys.stderr.write(err.read_text(encoding="utf-8", errors="replace"))


def exec_root(command: str, *, timeout_ms: int, paths: BridgePaths | None = None) -> int:
    paths = paths or BridgePaths.from_env()
    job_id = submit_root(command, timeout_ms=timeout_ms, paths=paths)
    try:
        snap = wait(job_id, timeout=timeout_ms / 1000 + 30, paths=paths)
    except BridgeError as exc:
        print(f"root_exec wait failed job={job_id}: {exc}", file=sys.stderr)
        return 124
    emit_job_logs(snap)
    result = snap.get("result") or {}
    code = result.get("exit_code")
    if isinstance(code, int):
        return max(0, min(255, code))
    terminal = terminal_status(snap)
    if terminal == "CANCELLED":
        return 130
    if terminal == "RECONCILE_REQUIRED":
        return 125
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Y700 Bridge v2 filesystem client")
    sp = p.add_subparsers(dest="cmd", required=True)

    q = sp.add_parser("submit-root")
    q.add_argument("--timeout-ms", type=int, default=int(os.environ.get("Y700_BRIDGE_TIMEOUT_MS", "90000")))
    q.add_argument("command", nargs=argparse.REMAINDER)

    q = sp.add_parser("exec-root")
    q.add_argument("--timeout-ms", type=int, default=int(os.environ.get("Y700_BRIDGE_TIMEOUT_MS", "90000")))
    q.add_argument("command", nargs=argparse.REMAINDER)

    q = sp.add_parser("status")
    q.add_argument("job_id")

    q = sp.add_parser("cancel")
    q.add_argument("job_id")
    q.add_argument("--reason", default="user_requested")

    q = sp.add_parser("wait")
    q.add_argument("job_id")
    q.add_argument("--timeout", type=float, default=None)

    q = sp.add_parser("reconcile")
    q.add_argument("job_id", nargs="?")

    sp.add_parser("health")

    q = sp.add_parser("cleanup-staging")
    q.add_argument("--ttl-seconds", type=int, default=86_400)
    return p


def main() -> int:
    args = build_parser().parse_args()
    paths = BridgePaths.from_env()
    try:
        if args.cmd in {"submit-root", "exec-root"}:
            command_parts = list(args.command)
            if command_parts and command_parts[0] == "--":
                command_parts = command_parts[1:]
            command = " ".join(command_parts).strip()
            if not command:
                raise BridgeError("missing root command")
            if args.cmd == "submit-root":
                job_id = submit_root(command, timeout_ms=args.timeout_ms, paths=paths)
                print(json.dumps({"job_id": job_id, "protocol_version": 2}))
                return 0
            return exec_root(command, timeout_ms=args.timeout_ms, paths=paths)

        if args.cmd == "status":
            obj = status(args.job_id, paths=paths)
        elif args.cmd == "cancel":
            obj = cancel(args.job_id, reason=args.reason, paths=paths)
        elif args.cmd == "wait":
            obj = wait(args.job_id, timeout=args.timeout, paths=paths)
        elif args.cmd == "reconcile":
            obj = request_reconcile(args.job_id, paths=paths)
        elif args.cmd == "health":
            obj = health(paths=paths)
        elif args.cmd == "cleanup-staging":
            obj = cleanup_staging(ttl_seconds=args.ttl_seconds, paths=paths)
        else:
            raise BridgeError("unsupported command")
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        return 0
    except BridgeError as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
