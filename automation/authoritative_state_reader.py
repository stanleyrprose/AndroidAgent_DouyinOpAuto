"""Rev3.7 authoritative read-only state boundary for the Y700 host.

Runs INSIDE the trusted Debian host only. This is not an Android-app API,
a caller-supplied token, or a substitute for compare-before-mutate.

Reads the existing root-owned State Integrity SOT; there is no cache, daemon,
state initialization, file repair, or configuration switch that authorizes
an Android action. Production visual mutation stays independently disabled.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Any, Mapping

STATE_PATH = Path("/opt/y700/runtime/ui-state/device-state.json")
BOOT_PATH = Path("/proc/sys/kernel/random/boot_id")
_EPOCH = re.compile(r"^epoch-[0-9a-f]{32}$")
_BOOT = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_SOT_MAX_BYTES = 8192
# An observation budget, NOT a calibrated visual route frame-age threshold.
_MAX_READ_DURATION_MS = 250


class AuthorityUnavailable(RuntimeError):
    """No safe claim about authoritative state can be made."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class AuthoritativeState:
    boot_id: str
    state_epoch: str
    revision: int
    observed_boottime_ms: int

    def internal_fields(self) -> dict[str, Any]:
        """Internal data for an independently observed JIT comparison only."""
        return {
            "boot_id": self.boot_id,
            "state_epoch": self.state_epoch,
            "revision": self.revision,
            "observed_boottime_ms": self.observed_boottime_ms,
        }

    def safe_receipt(self) -> dict[str, Any]:
        """No raw boot/epoch values in diagnostic logs or external responses."""
        return {
            "status": "READ_ONLY_SOT_OBSERVED",
            "revision_nonnegative": self.revision >= 0,
            "observed_boottime_ms": self.observed_boottime_ms,
            "dg3_status": "OPEN",
            "production_dispatch_authorized": False,
            "action_attempts": 0,
        }


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise AuthorityUnavailable(code)


def _object_unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in out, "SOT_DUPLICATE_KEY")
        out[key] = value
    return out


def _read_fixed_state() -> tuple[str, int, tuple[int, int, int, int]]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(STATE_PATH, flags)
    except OSError as exc:
        raise AuthorityUnavailable("SOT_UNAVAILABLE") from exc
    try:
        pre = os.fstat(fd)
        _require(stat.S_ISREG(pre.st_mode), "SOT_NOT_REGULAR")
        _require(pre.st_uid == 0 and stat.S_IMODE(pre.st_mode) == 0o600,
                 "SOT_PERMISSIONS_INVALID")
        _require(0 < pre.st_size <= _SOT_MAX_BYTES, "SOT_SIZE_INVALID")
        with os.fdopen(os.dup(fd), "rb") as file:
            raw = file.read(_SOT_MAX_BYTES + 1)
        post = os.fstat(fd)
        generation = (pre.st_dev, pre.st_ino, pre.st_mtime_ns, pre.st_size)
        _require(generation == (
            post.st_dev, post.st_ino, post.st_mtime_ns, post.st_size
        ) and len(raw) == pre.st_size, "SOT_CHANGED_DURING_READ")
        try:
            data = json.loads(raw, object_pairs_hook=_object_unique)
        except (ValueError, UnicodeError) as exc:
            raise AuthorityUnavailable("SOT_MALFORMED") from exc
        _require(isinstance(data, dict) and
                 type(data.get("state_version")) is int and data["state_version"] == 1
                 and data.get("fingerprint_version") == "semantic-v1",
                 "SOT_SCHEMA_INVALID")
        epoch, revision = data.get("state_epoch"), data.get("revision")
        _require(type(epoch) is str and _EPOCH.fullmatch(epoch) is not None
                 and type(revision) is int and revision >= 0,
                 "SOT_SCHEMA_INVALID")
        return epoch, revision, generation
    finally:
        os.close(fd)


def _kernel_boot() -> str:
    # The boot identity must be obtained from the local kernel, never from a
    # workflow/LLM payload or cached screenshot metadata.
    try:
        boot = BOOT_PATH.read_text(encoding="ascii").strip().lower()
    except (OSError, UnicodeError) as exc:
        raise AuthorityUnavailable("BOOT_ID_UNAVAILABLE") from exc
    _require(_BOOT.fullmatch(boot) is not None, "BOOT_ID_INVALID")
    return boot


def _now_boottime_ms() -> int:
    try:
        return time.clock_gettime_ns(time.CLOCK_BOOTTIME) // 1_000_000
    except (AttributeError, OSError) as exc:
        raise AuthorityUnavailable("BOOTTIME_UNAVAILABLE") from exc


def observe_authoritative_state() -> AuthoritativeState:
    """Two SOT reads around boot+clock sampling, no writes, fixed paths.

    This short cross-check reduces accidental races with atomic state swaps.
    It does NOT lock the writer or make the later Android dispatch atomic.
    Consumers must reobserve immediately before any contemplated action.
    """
    start = _now_boottime_ms()
    first = _read_fixed_state()
    boot_before = _kernel_boot()
    observed = _now_boottime_ms()
    boot_after = _kernel_boot()
    second = _read_fixed_state()
    finished = _now_boottime_ms()
    _require(boot_before == boot_after, "BOOT_ID_DRIFT")
    _require(first == second, "SOT_CHANGED_DURING_READ")
    _require(start <= observed <= finished
             and finished - start <= _MAX_READ_DURATION_MS,
             "SOT_OBSERVATION_STALE")
    epoch, revision, _ = first
    return AuthoritativeState(
        boot_id=boot_after, state_epoch=epoch,
        revision=revision, observed_boottime_ms=observed,
    )


def validate_against_authority(
    candidate: Mapping[str, Any], observed: AuthoritativeState
) -> None:
    """Strict internal proof comparison; NEVER issues action permission."""
    _require(isinstance(candidate, Mapping), "STATE_GUARD_UNAVAILABLE")
    _require(type(candidate.get("revision")) is int,
             "FRAME_REVISION_STALE")
    _require(type(candidate.get("state_epoch")) is str,
             "FRAME_STALE")
    _require(type(candidate.get("observed_boot_id")) is str,
             "FRAME_BOOT_MISMATCH")
    _require(candidate["observed_boot_id"] == observed.boot_id,
             "FRAME_BOOT_MISMATCH")
    _require(candidate["state_epoch"] == observed.state_epoch,
             "FRAME_STALE")
    _require(candidate["revision"] == observed.revision,
             "FRAME_REVISION_STALE")


def readonly_authority_verdict(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """External diagnostics intentionally never return VERIFIED FOR DISPATCH."""
    base = {
        "scope": "READ_ONLY_AUTHORITY_COMPARISON",
        "status": "BLOCKED",
        "dg3_status": "OPEN",
        "production_dispatch_authorized": False,
        "action_attempts": 0,
    }
    try:
        observed = observe_authoritative_state()
        validate_against_authority(candidate, observed)
        # No mutation authorization or signed/sufficient Android token.
        return {**base, "status": "MATCHED_READ_ONLY"}
    except AuthorityUnavailable as exc:
        return {**base, "reason": exc.code}
