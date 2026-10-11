"""Rev3.7 exact-owner best-effort ADMIN stop source adapter.

Only used by audited ADMIN force-reset after durable epoch bump. Signals
EXACT original Linux owner PID when its kernel boot and /proc start-time
still match. Never kill by substring/name/pkill, never signal the current
process, never assume SIGTERM proves any UI or Backend quiescence.

Subordinate Android/native mutators are separately proven by the retained
resource_stop_observer; this module NEVER releases the Claim or retries
business effects. Admin entrypoint and source-level release gate stay OFF.
"""
from __future__ import annotations

from pathlib import Path
import os
import signal
from typing import Any, Mapping

from automation import resource_arbiter
from automation.authoritative_state_reader import observe_authoritative_state
from automation.resource_reconcile_v37 import (
    ResourceRecoveryRefused,
)


def terminate_exact_owner_best_effort(
    claim: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(claim, Mapping):
        raise ResourceRecoveryRefused("EXACT_STOP_CLAIM_UNAVAILABLE")
    current = resource_arbiter.read_claim()
    if (not isinstance(current, dict)
            or current.get("claim_id") != claim.get("claim_id")
            or current.get("owner_id") != claim.get("owner_id")):
        raise ResourceRecoveryRefused("EXACT_STOP_CLAIM_CHANGED")
    owner = current.get("owner")
    if not isinstance(owner, dict):
        raise ResourceRecoveryRefused("EXACT_STOP_OWNER_UNAVAILABLE")
    boot = observe_authoritative_state()
    if owner.get("boot_id") != boot.boot_id:
        return {"stop_attempted": False, "owner_on_previous_boot": True}
    pid = owner.get("pid")
    ticks = owner.get("proc_start_ticks")
    if (type(pid) is not int or type(ticks) is not int
            or pid <= 1 or ticks <= 0 or pid == os.getpid()):
        raise ResourceRecoveryRefused("EXACT_STOP_OWNER_UNSAFE")
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"stop_attempted": False, "owner_not_found": True}
    except (OSError, UnicodeError) as exc:
        raise ResourceRecoveryRefused("EXACT_STOP_PROC_UNREADABLE") from exc
    try:
        entries = raw.rsplit(") ", 1)[1].split()
        state = entries[0]
        observed_ticks = int(entries[19])
    except (IndexError, ValueError) as exc:
        raise ResourceRecoveryRefused("EXACT_STOP_PROC_UNREADABLE") from exc
    if observed_ticks != ticks or state in {"Z", "X", "x"}:
        return {"stop_attempted": False, "exact_owner_dead": True}
    if state in {"T", "t"}:
        # A stopped job can resume; must not assume it has exited.
        return {"stop_attempted": False, "owner_stopped_unsafe": True}
    # An OS PID could still be reallocated between /proc read and kill,
    # so this is best-effort only, never a positive stopping proof.
    # pidfd gives the kernel-stable original process identity, avoiding
    # the otherwise unavoidable PID-reuse race between stat() and kill().
    # No raw os.kill fallback: old kernels/unsupported runtimes fail closed.
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise ResourceRecoveryRefused("EXACT_STOP_PIDFD_UNAVAILABLE")
    try:
        pidfd = os.pidfd_open(pid, 0)
    except ProcessLookupError:
        return {"stop_attempted": False, "owner_not_found": True}
    except OSError as exc:
        raise ResourceRecoveryRefused("EXACT_STOP_PIDFD_UNAVAILABLE") from exc
    try:
        # Re-observe process start ticks AFTER binding the pidfd; if
        # recycled, do not touch the process attached to this PID.
        try:
            current = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            current_ticks = int(current.rsplit(") ", 1)[1].split()[19])
        except (FileNotFoundError, OSError, UnicodeError, IndexError, ValueError):
            return {"stop_attempted": False, "owner_identity_unavailable": True}
        if current_ticks != ticks:
            return {"stop_attempted": False, "pid_reused": True}
        try:
            signal.pidfd_send_signal(pidfd, signal.SIGTERM, None, 0)
        except ProcessLookupError:
            return {"stop_attempted": False, "owner_already_exited": True}
        except (PermissionError, OSError):
            return {"stop_attempted": True, "stop_result": "UNKNOWN"}
        return {
            "stop_attempted": True,
            "stop_result": "PIDFD_SIGNAL_SENT_UNVERIFIED",
        }
    finally:
        os.close(pidfd)
