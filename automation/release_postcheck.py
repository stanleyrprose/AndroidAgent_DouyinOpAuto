"""Rev3.7 source-owned post-switch health and rollback safety facts.

Never accept caller-supplied callbacks/booleans for deciding whether to
retain an active candidate or roll it back. Trusted native/host observers
record root-owned evidence for the exact release, boot, switch-baseline and
fresh monotonic time. Any missing/stale/ambiguous fact fails CLOSED.

Development-only source. Both evidence producers stay independently
unaccepted until real-device verification; no link mutation or daemon here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import stat

from automation.authoritative_state_reader import observe_authoritative_state
from automation.publisher_boundary_guard import _strict_json
from automation.admission_fence import observe_admission_fence_readonly
from automation.recovery_inventory import inspect_startup_inventory_readonly
from automation.resource_arbiter import read_claim, ResourceError

ROOT = Path("/opt/y700/runtime/release-postcheck")
HEALTH = ROOT / "health.json"
NO_EFFECTS = ROOT / "no-effects.json"
_ACTIVE = Path("/opt/y700/workspaces/y700-agent")
_HEALTH_PRODUCER_ACCEPTED = False
_NO_EFFECT_PRODUCER_ACCEPTED = False


def _restricted_receipt(path: Path) -> dict[str, Any] | None:
    try:
        parent = ROOT.lstat()
        if (not stat.S_ISDIR(parent.st_mode)
                or parent.st_uid != 0
                or stat.S_IMODE(parent.st_mode) != 0o700):
            return None
        return _strict_json(path)
    except Exception:
        return None


def _exact(
    receipt: Mapping[str, Any], baseline: Mapping[str, Any],
    candidate_dir: Path, *, producer: str, version: int,
) -> bool:
    try:
        state = observe_authoritative_state()
        observed = receipt.get("observed_boottime_ms")
        return bool(
            receipt.get("post_switch_version") == version
            and receipt.get("producer") == producer
            and receipt.get("release_id") == candidate_dir.name
            and receipt.get("candidate_release") == str(candidate_dir)
            and receipt.get("baseline_boot_id")
                == baseline.get("switch_baseline_boot_id")
            and receipt.get("boot_id") == state.boot_id
            and state.boot_id == baseline.get("switch_baseline_boot_id")
            and type(observed) is int
            and 0 <= state.observed_boottime_ms - observed <= 1500
            and _ACTIVE.is_symlink()
            and _ACTIVE.resolve(strict=True) == candidate_dir
        )
    except (OSError, ValueError, TypeError):
        return False


def positive_health_after_switch_readonly(
    *, candidate_dir: Path, baseline: Mapping[str, Any],
) -> bool:
    if not _HEALTH_PRODUCER_ACCEPTED:
        return False
    receipt = _restricted_receipt(HEALTH)
    if receipt is None or not _exact(
            receipt, baseline, candidate_dir,
            producer="Y700_ACCEPTED_RELEASE_HEALTH", version=1):
        return False
    # A single 'healthy' flag is never enough. Independent supervisors
    # must positively verify the candidate identity and nonmutating startup.
    return (
        receipt.get("candidate_imports_ready") is True
        and receipt.get("bridge_protocol_compatible") is True
        and receipt.get("ui_core_protocol_compatible") is True
        and receipt.get("capability_catalog_accepted") is True
        and receipt.get("runtime_owner_identity_unchanged") is True
        and type(receipt.get("observed_effect_attempts")) is int
        and receipt["observed_effect_attempts"] == 0
    )


def positive_no_effect_since_switch_readonly(
    *, candidate_dir: Path, baseline: Mapping[str, Any],
) -> bool:
    if not _NO_EFFECT_PRODUCER_ACCEPTED:
        return False
    receipt = _restricted_receipt(NO_EFFECTS)
    if receipt is None or not _exact(
            receipt, baseline, candidate_dir,
            producer="Y700_ACCEPTED_NATIVE_EFFECT_AUDITOR", version=1):
        return False
    try:
        now = observe_authoritative_state()
        if (now.state_epoch != baseline.get("switch_baseline_epoch")
                or now.revision != baseline.get("switch_baseline_revision")
                or receipt.get("state_epoch") != now.state_epoch
                or receipt.get("revision") != now.revision):
            return False
        fence = observe_admission_fence_readonly(
            expected_release_id=candidate_dir.name)
        if fence.get("admissions_stopped_positive") is not True:
            return False
        if read_claim() is not None:
            return False
        inventory = inspect_startup_inventory_readonly()
        if (inventory.get("status") != "READ_ONLY_STARTUP_INVENTORY"
                or inventory.get("active_count") != 0
                or inventory.get("staging_count") != 0):
            return False
        return (
            receipt.get("all_android_mutators_absent") is True
            and receipt.get("all_linux_backend_mutators_absent") is True
            and receipt.get("all_capability_effects_absent") is True
            and receipt.get("unknown_effects_present") is False
            and receipt.get("claim_reallocation_absent") is True
        )
    except (OSError, ValueError, ResourceError):
        return False
