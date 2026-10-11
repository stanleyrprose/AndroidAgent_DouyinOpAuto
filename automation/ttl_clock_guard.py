"""Rev3.7 BOOTTIME-aware pre-submit TTL identity and reboot recovery.

This module does NOT expire post-submit backend jobs, authorize a retry or
use wall-clock duration as state-token/frame freshness proof.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Any, Mapping


class ClockGuardUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _parse_wall(iso: str) -> datetime:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ClockGuardUnavailable("TTL_INVALID") from exc
    if dt.tzinfo is None:
        raise ClockGuardUnavailable("TTL_INVALID")
    return dt.astimezone(timezone.utc)


def _boottime() -> int:
    try:
        return time.clock_gettime_ns(time.CLOCK_BOOTTIME) // 1_000_000
    except (AttributeError, OSError) as exc:
        raise ClockGuardUnavailable("CLOCK_BOOTTIME_UNAVAILABLE") from exc


@dataclass(frozen=True)
class TtlClockEvidence:
    version: int
    accepted_wall_time: str
    accepted_boot_id: str
    accepted_boottime_ms: int
    deadline_boottime_ms: int
    expires_at: str

    def durable(self) -> dict[str, Any]:
        return {
            "ttl_clock_version": self.version,
            "accepted_wall_time": self.accepted_wall_time,
            "accepted_boot_id": self.accepted_boot_id,
            "accepted_boottime_ms": self.accepted_boottime_ms,
            "deadline_boottime_ms": self.deadline_boottime_ms,
            "expires_at": self.expires_at,
        }


def accept_ttl(*, expires_at: str, boot_id: str,
               contract_max_ttl_sec: int,
               wall_time: datetime | None = None,
               current_boottime_ms: int | None = None) -> TtlClockEvidence:
    """Acceptance called once per submission; durable evidence before submit."""
    if (type(contract_max_ttl_sec) is not int
            or not 0 < contract_max_ttl_sec <= 86400
            or not isinstance(boot_id, str) or not boot_id):
        raise ClockGuardUnavailable("TTL_CONTRACT_INVALID")
    current = wall_time or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ClockGuardUnavailable("CLOCK_SUSPECT")
    current = current.astimezone(timezone.utc)
    when = _parse_wall(expires_at)
    delta = (when - current).total_seconds()
    if delta <= 0:
        raise ClockGuardUnavailable("REQUEST_EXPIRED")
    if delta > contract_max_ttl_sec:
        raise ClockGuardUnavailable("TTL_EXCEEDS_CONTRACT")
    now_boot = (_boottime() if current_boottime_ms is None
                else current_boottime_ms)
    if type(now_boot) is not int or now_boot < 0:
        raise ClockGuardUnavailable("CLOCK_BOOTTIME_UNAVAILABLE")
    return TtlClockEvidence(
        version=1,
        accepted_wall_time=current.isoformat(),
        accepted_boot_id=boot_id,
        accepted_boottime_ms=now_boot,
        deadline_boottime_ms=now_boot + int(delta * 1000),
        expires_at=when.isoformat(),
    )


def classify_pre_submit_ttl(
    *,
    evidence: Mapping[str, Any],
    current_boot_id: str,
    backend_submitted: bool,
    current_clock_health: str,
    current_wall_time: datetime | None = None,
    current_boottime_ms: int | None = None,
    backend_never_created_positive_proof: bool,
) -> dict[str, Any]:
    """Pre-submit only; clock suspect leaves original nonterminal phase."""
    if backend_submitted is True:
        return {
            "status": "POST_SUBMIT_TTL_NOT_APPLICABLE",
            "terminal": False,
            "repeat_backend_allowed": False,
        }
    if backend_never_created_positive_proof is not True:
        return {
            "status": "BLOCKED",
            "reason_code": "BACKEND_EXISTENCE_UNPROVEN",
            "terminal": False,
        }
    if evidence.get("ttl_clock_version") != 1:
        raise ClockGuardUnavailable("TTL_EVIDENCE_UNAVAILABLE")
    if (not isinstance(current_boot_id, str) or not current_boot_id
            or current_clock_health != "HEALTHY"):
        return {
            "status": "BLOCKED",
            "reason_code": "CLOCK_SUSPECT_PRE_SUBMIT",
            "terminal": False,
            "next_action": "REPAIR_CLOCK",
        }
    original_boot = evidence.get("accepted_boot_id")
    if original_boot == current_boot_id:
        now = (_boottime() if current_boottime_ms is None
               else current_boottime_ms)
        deadline = evidence.get("deadline_boottime_ms")
        if type(now) is not int or type(deadline) is not int or now < 0:
            raise ClockGuardUnavailable("TTL_EVIDENCE_UNAVAILABLE")
        expired = now >= deadline
    else:
        # Original boottime deadline is not transferable across kernel boots.
        current = current_wall_time or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ClockGuardUnavailable("CLOCK_SUSPECT_PRE_SUBMIT")
        expired = current.astimezone(timezone.utc) >= _parse_wall(
            evidence["expires_at"]
        )
    return {
        "status": "EXPIRED" if expired else "PRE_SUBMIT_TTL_VALID",
        "terminal": expired,
        "backend_submitted": False,
        "external_effect_attempts": 0,
        "new_backend_allocated": False,
    }
