"""Rev3.7 exact-process/resource stop proof reader (NO cleanup).

This positive proof is for android_ui RELEASE ONLY, never a BUSINESS
verification, TikTok retry permission, or backend allocation.

The source is root-owned claim+original Backend SOT, Linux proc start ticks
and separately accepted native/subordinate UI quiescence evidence. A
STOPPED (T/t), HUNG, unreadable proc or unknown Android subjob is NOT
positive proof. PID number alone is never sufficient.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import os
import re

from automation import resource_arbiter
from automation.capability_job_store import (
    CAP_JOBS, CapabilityStoreError, _read_json,
)
from automation.authoritative_state_reader import (
    AuthorityUnavailable, observe_authoritative_state,
)
from automation.publisher_boundary_guard import (
    PublisherBoundaryError, _strict_json,
)

_NATIVE_MUTATOR_ABSENCE_ACCEPTED = False
_NATIVE_STOP_ROOT = Path("/opt/y700/runtime/native-ui-stop-receipts")
_CAP = re.compile(r"^cap-[0-9a-f]{48}$")


class StopProofUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise StopProofUnavailable(code)


def _linux_proc_stopped(owner: dict[str, Any], kernel_boot_id: str) -> bool:
    _need(type(owner.get("pid")) is int
          and owner["pid"] > 0
          and type(owner.get("proc_start_ticks")) is int
          and owner["proc_start_ticks"] > 0
          and isinstance(owner.get("boot_id"), str),
          "EXACT_OWNER_PROCESS_IDENTITY_UNAVAILABLE")
    if owner["boot_id"] != kernel_boot_id:
        # Linux process IDs from a different kernel boot cannot survive.
        return True
    pid = owner["pid"]
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(
            encoding="utf-8", errors="strict")
    except FileNotFoundError:
        return True
    except (OSError, UnicodeError) as exc:
        raise StopProofUnavailable("OWNER_PROC_UNREADABLE") from exc
    try:
        tail = raw.rsplit(") ", 1)[1].split()
        state = tail[0]
        ticks = int(tail[19])
    except (IndexError, ValueError) as exc:
        raise StopProofUnavailable("OWNER_PROC_UNREADABLE") from exc
    if ticks != owner["proc_start_ticks"]:
        return True  # PID reuse; exact original process is gone.
    if state in {"Z", "X", "x"}:
        return True
    # STOPPED T/t, sleeping, RUNNING or unknown state can resume action.
    return False


def positive_synchronous_ui_quiescence(
    current_guard: Mapping[str, Any],
    *, backend_job_id: str,
) -> bool:
    """Foreground-safe release proof without requiring owner PID death.

    A normally returning synchronous Gateway owner is STILL ALIVE; this
    proof instead requires that the native/UI Core executor positively
    observed every descendant mutator terminal under the exact Claim.
    No missing field/empty active-list may count as evidence.
    """
    from automation.authoritative_state_reader import (
        observe_authoritative_state,
    )
    if not _NATIVE_MUTATOR_ABSENCE_ACCEPTED:
        return False
    if not isinstance(current_guard, Mapping):
        return False
    try:
        claim = resource_arbiter.assert_guard(dict(current_guard))
        if (claim.get("backend_job_id") != backend_job_id
                or claim.get("active_ui_job_id") is not None
                or claim.get("active_session_id") is not None
                or claim.get("reconcile_required")):
            return False
        state = observe_authoritative_state()
        receipt = _strict_json(
            _NATIVE_STOP_ROOT / (
                str(claim["claim_id"]) + ".json"))
        at = receipt.get("observed_boottime_ms")
        return bool(
            receipt.get("native_stop_receipt_version") == 1
            and receipt.get("source") == "Y700_NATIVE_DRIVER_AND_BRIDGE"
            and receipt.get("claim_id") == claim["claim_id"]
            and receipt.get("owner_id") == claim["owner_id"]
            and receipt.get("backend_job_id") == backend_job_id
            and type(claim.get("ui_execution_generation")) is int
            and claim["ui_execution_generation"] > 0
            and receipt.get("ui_execution_generation")
                == claim["ui_execution_generation"]
            and receipt.get("boot_id") == state.boot_id
            and receipt.get("state_epoch") == state.state_epoch
            and receipt.get("native_ui_subjobs_absent") is True
            and receipt.get("linux_child_mutators_absent") is True
            and receipt.get("all_subordinates_terminal_positive") is True
            and type(at) is int
            and 0 <= state.observed_boottime_ms - at <= 1000
        )
    except (Exception):
        return False


def inspect_exact_stop_readonly(claim_id: str) -> dict[str, Any]:
    """Positive evidence requires native independently accepted receipt."""
    try:
        claim = resource_arbiter.read_claim()
        _need(isinstance(claim, dict)
              and claim.get("claim_id") == claim_id
              and claim.get("resource") == "android_ui",
              "EXACT_RESOURCE_CLAIM_NOT_FOUND")
        state = observe_authoritative_state()
        owner = claim.get("owner")
        _need(isinstance(owner, dict),
              "EXACT_OWNER_PROCESS_IDENTITY_UNAVAILABLE")
        stopped = _linux_proc_stopped(owner, state.boot_id)
        cap = claim.get("capability_job_id")
        backend_id = claim.get("backend_job_id")
        backend_positive = False
        if claim.get("owner_kind") == "CAPABILITY":
            _need(isinstance(cap, str) and _CAP.fullmatch(cap) is not None,
                  "EXACT_CAPABILITY_IDENTITY_INVALID")
            source = CAP_JOBS / "active" / cap
            archive = CAP_JOBS / "archive"
            if source.is_dir() and not source.is_symlink():
                binding = _read_json(source / "backend.json")
                execution = _read_json(source / "backend-execution.json")
                identity = _read_json(source / "identity.json")
                _need(binding.get("backend_job_id") == backend_id
                      and execution.get("backend_job_id") == backend_id
                      and binding.get("capability_job_id") == cap
                      and execution.get("capability_job_id") == cap
                      and identity.get("capability_job_id") == cap
                      and binding.get("request_sha256")
                          == identity.get("request_sha256")
                          == execution.get("request_sha256")
                          == claim.get("request_sha256"),
                      "EXACT_BACKEND_IDENTITY_MISMATCH")
                # Normal safe path: durable never-submitted plus dead owner.
                # Submission-possible needs a separate POSITIVE terminal.
                backend_positive = (
                    execution.get("phase") == "NEVER_CREATED"
                    and execution.get("submission_possible") is False
                    and execution.get("attempt_serial") == 0
                )
            else:
                _need(not source.exists() and not source.is_symlink(),
                      "CAPABILITY_PATH_UNTRUSTED")
                # Terminal archive must be proved by exact durable result;
                # absence from active is not sufficient.
                for cls in (
                    "verified", "outcome_not_achieved", "failed",
                    "cancelled", "expired"):
                    terminal = archive / cls / cap / "result.json"
                    if terminal.exists():
                        receipt = _read_json(terminal)
                        backend_positive = (
                            receipt.get("capability_job_id") == cap
                            and receipt.get("exact_backend_job_id")
                                == backend_id
                            and receipt.get("request_sha256")
                                == claim.get("request_sha256")
                            and receipt.get("external_effect_retry_allowed")
                                is False
                            and receipt.get("terminal") is True)
                        break
        # For legacy claims absence of a Capability Job is expected;
        # require native proof of exact legacy Backend quiescence.
        elif claim.get("owner_kind") in {"LEGACY", "ADMIN"}:
            backend_positive = False
        else:
            raise StopProofUnavailable("OWNER_KIND_UNSUPPORTED")
        native_absence = False
        if _NATIVE_MUTATOR_ABSENCE_ACCEPTED:
            receipt = _strict_json(_NATIVE_STOP_ROOT /
                                   (claim_id + ".json"))
            observed_ms = receipt.get("observed_boottime_ms")
            native_absence = (
                type(observed_ms) is int
                and 0 <= state.observed_boottime_ms - observed_ms <= 1000
                and receipt.get("state_epoch") == state.state_epoch
                and receipt.get("native_stop_receipt_version") == 1
                and receipt.get("source") == "Y700_NATIVE_DRIVER_AND_BRIDGE"
                and receipt.get("claim_id") == claim_id
                and receipt.get("owner_id") == claim.get("owner_id")
                and receipt.get("backend_job_id") == backend_id
                and type(claim.get("ui_execution_generation")) is int
                and claim["ui_execution_generation"] > 0
                and receipt.get("ui_execution_generation")
                    == claim["ui_execution_generation"]
                and receipt.get("boot_id") == state.boot_id
                and receipt.get("native_ui_subjobs_absent") is True
                and receipt.get("linux_child_mutators_absent") is True
                and receipt.get("all_subordinates_terminal_positive") is True
                and receipt.get("backend_terminal_positive") is True
            )
            backend_positive = backend_positive or (
                native_absence
                and receipt.get("backend_terminal_positive") is True)
        return {
            "status": "READ_ONLY_EXACT_STOP_INSPECTION",
            "claim_id": claim_id,
            "owner_kind": claim.get("owner_kind"),
            "backend_job_id": backend_id,
            "owner_process_not_running_positive": stopped,
            "backend_not_running_positive": backend_positive,
            "subordinate_ui_mutators_absent_positive": native_absence,
            "boot_identity_verified": True,
            "fully_quiescent_positive": (
                stopped and backend_positive and native_absence),
            "claim_released": False,
            "business_outcome_changed": False,
        }
    except (OSError, ValueError, KeyError, CapabilityStoreError,
            AuthorityUnavailable, PublisherBoundaryError,
            resource_arbiter.ResourceError, StopProofUnavailable) as exc:
        return {
            "status": "BLOCKED",
            "reason_code": getattr(
                exc, "code", "POSITIVE_STOP_EVIDENCE_UNAVAILABLE"),
            "fully_quiescent_positive": False,
            "claim_released": False,
            "business_outcome_changed": False,
        }
