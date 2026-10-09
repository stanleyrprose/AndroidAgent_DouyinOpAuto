#!/usr/bin/env python3
"""Rev3.7 one-shot, READ-ONLY authoritative Debian State Integrity probe.

This is a boundary diagnostic, NOT a driver-dispatch oracle.
Reads the existing owner-protected SOT without calling load_state() (which
may auto-initialize). Never writes a state file, serves network requests,
authorizes action, or exports raw state_epoch.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Callable

DEFAULT_SOT = Path("/opt/y700/runtime/ui-state/device-state.json")
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
EPOCH = re.compile(r"^epoch-[0-9a-f]{32}$")
BOOT = re.compile(r"^[0-9a-f-]{36}$")
MAX_SIZE = 8 * 1024


class ProbeRefusal(Exception):
    pass


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise ProbeRefusal(code)


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        _need(key not in result, "SOT_DUPLICATE_KEY")
        result[key] = value
    return result


def _read_sot(sot_path: Path, *, enforce_root_owner: bool) -> dict:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(sot_path, flags)
    except (OSError, ValueError) as exc:
        raise ProbeRefusal("SOT_UNAVAILABLE") from exc
    try:
        before = os.fstat(fd)
        _need(stat.S_ISREG(before.st_mode), "SOT_NOT_REGULAR")
        _need(before.st_size > 0 and before.st_size <= MAX_SIZE, "SOT_SIZE_INVALID")
        _need(stat.S_IMODE(before.st_mode) == 0o600, "SOT_PERMISSIONS_INVALID")
        if enforce_root_owner:
            _need(before.st_uid == 0, "SOT_OWNER_INVALID")
        with os.fdopen(os.dup(fd), "rb", closefd=True) as f:
            raw = f.read(MAX_SIZE + 1)
        after = os.fstat(fd)
        _need(len(raw) <= MAX_SIZE and len(raw) == before.st_size, "SOT_SIZE_INVALID")
        _need((before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size)
              == (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size),
              "SOT_CHANGED_DURING_READ")
        try:
            state = json.loads(raw, object_pairs_hook=_unique_keys)
        except (ValueError, UnicodeError) as exc:
            raise ProbeRefusal("SOT_JSON_INVALID") from exc
        _need(type(state) is dict and type(state.get("state_version")) is int
              and state["state_version"] == 1, "SOT_SCHEMA_INVALID")
        epoch = state.get("state_epoch")
        rev = state.get("revision")
        _need(type(epoch) is str and EPOCH.fullmatch(epoch) is not None
              and type(rev) is int and rev >= 0, "SOT_SCHEMA_INVALID")
        _need(state.get("fingerprint_version") == "semantic-v1",
              "SOT_FINGERPRINT_INVALID")
        return {"epoch": epoch, "revision": rev, "inode": before.st_ino}
    finally:
        os.close(fd)


def probe(sot_path: Path = DEFAULT_SOT, *, enforce_root_owner: bool = True,
          boot_path: Path = BOOT_ID,
          fixture_clock: Callable[[], int] | None = None) -> dict:
    """Read-only health proof; no production dispatch authority."""
    outcome = {"probe": "rev37-authoritative-sot-readonly-v1",
               "status": "BLOCKED", "dg3_status": "OPEN",
               "production_dispatch_authorized": False,
               "action_attempts": 0, "state_mutated": False}
    try:
        before_ns = fixture_clock() if fixture_clock else time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        state = _read_sot(sot_path, enforce_root_owner=enforce_root_owner)
        boot_raw = boot_path.read_text(encoding="ascii").strip().lower()
        _need(bool(BOOT.fullmatch(boot_raw)), "BOOT_ID_INVALID")
        after_ns = fixture_clock() if fixture_clock else time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        _need(after_ns >= before_ns, "CLOCK_NOT_MONOTONIC")
        # Reopen current path: a rename-based epoch/revision change concurrent
        # with our read must not be mistaken for one immutable SOT generation.
        again = _read_sot(sot_path, enforce_root_owner=enforce_root_owner)
        _need(state == again, "SOT_CHANGED_DURING_READ")
        outcome.update(
            status="READ_ONLY_SOT_CONSISTENT",
            source_permissions_verified=True,
            epoch_present=True,
            revision_nonnegative=True,
            boot_id_readable=True,
            boot_clock_monotonic=True,
            sample_read_duration_ms=(after_ns - before_ns) // 1_000_000,
            # Do not disclose raw state epoch, boot ID, or filesystem content.
            epoch_digest_prefix=hashlib.sha256(
                state["epoch"].encode("ascii")).hexdigest()[:12],
            revision=state["revision"],
            observed_boottime_ms=after_ns // 1_000_000,
            boot_digest_prefix=hashlib.sha256(
                boot_raw.encode("ascii")).hexdigest()[:12],
        )
    except (ProbeRefusal, OSError, AttributeError, UnicodeError) as exc:
        outcome["reason"] = str(exc) if isinstance(exc, ProbeRefusal) else "SOURCE_UNAVAILABLE"
    return outcome


def main() -> int:
    # Fixed-path CLI: no caller-controlled path, owner/clock, or bypass flag.
    result = probe(DEFAULT_SOT)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "READ_ONLY_SOT_CONSISTENT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
