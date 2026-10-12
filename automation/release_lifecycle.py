"""Rev3.7 immutable release / patch lifecycle planning and gated activation.

A versioned source manifest, precise old-runtime diagnostics, positive
quiescence proof, atomic symlink switch, bounded rollback and explicit
RECONCILE_REQUIRED semantics. The current development release is dormant:
no production symlink may switch until the final acceptance gate is changed
in reviewed code. No standalone upgrade daemon/scheduler.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

RELEASES = Path("/opt/y700/workspaces")
ACTIVE = RELEASES / "y700-agent"
RELEASE_STATE = Path("/opt/y700/runtime/release-state.json")
_REQUIRED_CONTRACTS = {
    "gateway": 1, "bridge": 2, "ui_core": 2, "frame_guard": 1,
}
_PATCH_CLASSES = frozenset({
    "PATCH_SAFE", "QUIESCENT_MIGRATION", "MANUAL_ONLY",
})
_SHA = re.compile(r"^[0-9a-f]{40}$")
# No workflow/env/request flag can turn this on.
_RELEASE_SWITCH_ACCEPTED = False


class ReleaseUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _need(condition: bool, code: str) -> None:
    if not condition:
        raise ReleaseUnavailable(code)


@dataclass(frozen=True)
class ReleaseManifest:
    release_id: str
    git_revision: str
    patch_level: int
    migration_level: int
    state_schema: int
    upgrade_class: str
    min_source_patch_level: int
    rollback_compatible: bool
    contracts: Mapping[str, int]

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "ReleaseManifest":
        _need(isinstance(raw, Mapping), "RELEASE_MANIFEST_UNAVAILABLE")
        _need(raw.get("release_manifest_version") == 1,
              "RELEASE_MANIFEST_VERSION_MISMATCH")
        for key in ("runtime_release_id", "git_revision"):
            _need(isinstance(raw.get(key), str) and raw[key],
                  "RELEASE_MANIFEST_INVALID")
        _need(bool(_SHA.fullmatch(raw["git_revision"])),
              "RELEASE_REVISION_INVALID")
        for key in ("patch_level", "state_schema", "migration_level",
                    "min_source_patch_level"):
            _need(type(raw.get(key)) is int and raw[key] >= 0,
                  "RELEASE_MANIFEST_INVALID")
        _need(raw.get("upgrade_class") in _PATCH_CLASSES,
              "RELEASE_UPGRADE_CLASS_INVALID")
        _need(type(raw.get("rollback_compatible")) is bool,
              "RELEASE_ROLLBACK_CONTRACT_INVALID")
        contracts = raw.get("contracts")
        _need(isinstance(contracts, dict), "RELEASE_CONTRACT_INVALID")
        for key, version in _REQUIRED_CONTRACTS.items():
            _need(type(contracts.get(key)) is int
                  and contracts[key] == version,
                  "RUNTIME_CONTRACT_MISMATCH")
        return cls(
            raw["runtime_release_id"], raw["git_revision"],
            raw["patch_level"], raw["migration_level"],
            raw["state_schema"], raw["upgrade_class"],
            raw["min_source_patch_level"], raw["rollback_compatible"],
            dict(contracts),
        )


@dataclass(frozen=True)
class QuiescenceProof:
    admissions_stopped: bool
    live_ui_mutators_absent: bool
    android_ui_claim_resolved: bool
    unsafe_effects_resolved: bool
    candidate_owner_mode_verified: bool
    candidate_signature_verified: bool
    offline_gates_passed: bool

    def complete(self) -> bool:
        return all((
            self.admissions_stopped,
            self.live_ui_mutators_absent,
            self.android_ui_claim_resolved,
            self.unsafe_effects_resolved,
            self.candidate_owner_mode_verified,
            self.candidate_signature_verified,
            self.offline_gates_passed,
        ))


def _read_limited(path: Path, maximum: int = 32768) -> dict[str, Any]:
    """Bounded, no-follow, single-inode release metadata read.

    The active pointer/manifest can be read concurrently with staging;
    a pathname read without inode checks could accept attacker-swapped or
    partially written facts as quiescence/release authority.
    """
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key, value in pairs:
            _need(key not in data, "RELEASE_METADATA_DUPLICATE_KEY")
            data[key] = value
        return data
    _need(0 < maximum <= 256 * 1024, "RELEASE_METADATA_LIMIT_INVALID")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ReleaseUnavailable("RELEASE_METADATA_UNAVAILABLE") from exc
    try:
        before = os.fstat(fd)
        _need(stat.S_ISREG(before.st_mode)
              and before.st_uid == 0
              and (stat.S_IMODE(before.st_mode) & 0o022) == 0
              and 0 < before.st_size <= maximum,
              "RELEASE_METADATA_UNTRUSTED")
        payload = bytearray()
        while len(payload) <= maximum:
            chunk = os.read(fd, min(8192, maximum + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(fd)
        _need(len(payload) == before.st_size
              and (before.st_dev, before.st_ino, before.st_size,
                   before.st_mtime_ns)
              == (after.st_dev, after.st_ino, after.st_size,
                  after.st_mtime_ns),
              "RELEASE_METADATA_CHANGED_DURING_READ")
        try:
            parsed = json.loads(payload, object_pairs_hook=unique)
        except (UnicodeError, ValueError) as exc:
            raise ReleaseUnavailable("RELEASE_METADATA_INVALID") from exc
        _need(isinstance(parsed, dict), "RELEASE_METADATA_INVALID")
        return parsed
    finally:
        os.close(fd)


def inspect_candidate(release_dir: Path) -> ReleaseManifest:
    """No write, no package update; immutable release-name/path check."""
    _need(release_dir.parent == RELEASES
          and release_dir.name.startswith("y700-agent-release-")
          and not release_dir.is_symlink()
          and release_dir.is_dir(), "RELEASE_PATH_UNTRUSTED")
    metadata = release_dir.stat()
    _need(stat.S_ISDIR(metadata.st_mode)
          and metadata.st_uid == 0
          and (stat.S_IMODE(metadata.st_mode) & 0o022) == 0,
          "RELEASE_OWNER_OR_MODE_INVALID")
    return ReleaseManifest.parse(
        _read_limited(release_dir / "release-manifest.json"))


def diagnose_release(
    active: ReleaseManifest | None,
    required: ReleaseManifest,
    *,
    clock_healthy: bool,
    android_helper_compatible: bool | None,
) -> dict[str, Any]:
    """Readable patch drift, no deploy operations or hidden auto-upgrade."""
    if active is None:
        reason = "ACTIVE_RELEASE_UNAVAILABLE"
    elif active.patch_level < required.patch_level:
        reason = "RUNTIME_PATCH_OUTDATED"
    elif active.migration_level != required.migration_level:
        reason = "MIGRATION_LEVEL_MISMATCH"
    elif active.state_schema != required.state_schema:
        reason = "STATE_SCHEMA_MISMATCH"
    elif active.contracts != required.contracts:
        reason = "RUNTIME_CONTRACT_MISMATCH"
    elif android_helper_compatible is not True:
        reason = "ANDROID_HELPER_CONTRACT_UNVERIFIED"
    elif not clock_healthy:
        reason = "CLOCK_SUSPECT"
    else:
        reason = "RELEASE_COMPATIBLE"
    return {
        "status": "DIAGNOSTIC_ONLY",
        "reason_code": reason,
        "current_patch_level": active.patch_level if active else None,
        "required_patch_level": required.patch_level,
        "upgrade_class": required.upgrade_class,
        "upgrade_possible": reason == "RUNTIME_PATCH_OUTDATED"
                            and required.upgrade_class == "PATCH_SAFE"
                            and _RELEASE_SWITCH_ACCEPTED,
        "mutation_authorized": False,
        "release_switch_authorized": False,
    }


def plan_upgrade(
    *,
    active: ReleaseManifest,
    candidate: ReleaseManifest,
    quiescence: QuiescenceProof,
    explicit_maintenance_authorization: bool,
) -> dict[str, Any]:
    """Explains exact upgrade blockers; never switches active symlink."""
    reason: str
    if candidate.patch_level < active.patch_level:
        reason = "RELEASE_DOWNGRADE_UNSUPPORTED"
    elif active.patch_level < candidate.min_source_patch_level:
        reason = "UNSUPPORTED_SOURCE_PATCH"
    elif candidate.upgrade_class == "MANUAL_ONLY":
        reason = "MANUAL_UPGRADE_REQUIRED"
    elif candidate.upgrade_class == "QUIESCENT_MIGRATION" and (
        explicit_maintenance_authorization is not True
    ):
        reason = "MAINTENANCE_AUTHORIZATION_REQUIRED"
    elif not quiescence.complete():
        reason = "UPGRADE_REQUIRES_QUIESCENCE"
    elif not _RELEASE_SWITCH_ACCEPTED:
        reason = "RELEASE_SWITCH_NOT_ACCEPTED"
    else:
        reason = "READY_FOR_SEPARATE_ACTIVATION"
    return {
        "status": "BLOCKED" if reason != "READY_FOR_SEPARATE_ACTIVATION"
                  else "PLANNED_ONLY",
        "reason_code": reason,
        "active_release_id": active.release_id,
        "candidate_release_id": candidate.release_id,
        "upgrade_class": candidate.upgrade_class,
        "eligible_for_atomic_switch": reason == "READY_FOR_SEPARATE_ACTIVATION",
        "release_switched": False,
        "rollback_attempts": 0,
    }


def rollback_classification(
    *, candidate_mutation_occurred: bool,
    unresolved_effect: bool,
    irreversible_migration: bool,
    candidate: ReleaseManifest,
) -> str:
    """Uncertain state can never be reinterpreted as safe automatic rollback."""
    if (candidate_mutation_occurred or unresolved_effect
            or irreversible_migration or not candidate.rollback_compatible):
        return "UPGRADE_RECONCILE_REQUIRED"
    return "ROLLBACK_NOT_ACTIVATED"


def _sync_parent(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _save_release_state(path: Path, data: Mapping[str, Any]) -> None:
    """Write a crash-durable release record with atomic fsync replace."""
    import secrets
    raw = json.dumps(
        dict(data), sort_keys=True, separators=(",", ":")
    ).encode() + b"\n"
    _need(len(raw) <= 32768, "RELEASE_STATE_OVERSIZE")
    _need(not path.is_symlink(), "RELEASE_STATE_UNTRUSTED")
    _need(path.parent.is_dir(), "RELEASE_RUNTIME_UNAVAILABLE")
    tmp = path.parent / (".release-state-" + secrets.token_hex(8))
    try:
        fd = os.open(
            tmp,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            remaining = memoryview(raw)
            while remaining:
                written = os.write(fd, remaining)
                _need(written > 0, "RELEASE_STATE_INCOMPLETE_WRITE")
                remaining = remaining[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
        _sync_parent(path.parent)
    finally:
        # A failed partial write must not leave a plausible pending
        # durable release record. The last fsynced state remains SOT.
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()


def _atomic_release_link(active: Path, target: Path) -> None:
    """Absolute immutable path -> same-parent temporary symlink -> replace."""
    import secrets
    _need(active == ACTIVE and target.parent == RELEASES,
          "RELEASE_PATH_UNTRUSTED")
    tmp = active.parent / (".y700-agent-switch-" + secrets.token_hex(8))
    _need(not tmp.exists() and not tmp.is_symlink(),
          "RELEASE_SWITCH_PATH_CONFLICT")
    tmp.symlink_to(target)
    try:
        os.replace(tmp, active)
        _sync_parent(active.parent)
    finally:
        if tmp.is_symlink():
            tmp.unlink()


def inspect_release_restart_readonly(
    *, active_path: Path = ACTIVE,
    state_path: Path = RELEASE_STATE,
) -> dict[str, Any]:
    """Crash/reboot release classification WITHOUT implicit rollback.

    A crash between SWITCH_PREPARED -> atomic symlink replacement ->
    POST_SWITCH_VERIFY is not proof that either version is safe. Inspect
    the exact root-owned release SOT and active symlink together under
    the same admission/release locks as a future upgrade transaction.
    No attempt is made to repair or replace the active pointer, consume
    approvals, start a backend, or resume admission.
    """
    from automation.capability_job_store import (
        _locked, SUBMISSIONS, CapabilityStoreError,
    )
    from automation.admission_fence import observe_admission_fence_readonly

    refusal = {
        "status": "RELEASE_RECONCILE_REQUIRED",
        "reason_code": "RELEASE_STATE_UNAVAILABLE",
        "automatic_rollback": False,
        "new_release_activated": False,
        "admissions_resumed": False,
        "backend_replayed": False,
    }
    try:
        with _locked(SUBMISSIONS / ".release-transaction.lock", shared=True), \
                _locked(SUBMISSIONS / ".admission.lock", shared=True):
            _need(active_path == ACTIVE and active_path.is_symlink(),
                  "ACTIVE_RELEASE_POINTER_UNTRUSTED")
            actual_target = Path(os.readlink(active_path))
            _need(actual_target.is_absolute()
                  and actual_target.parent == RELEASES,
                  "ACTIVE_RELEASE_PATH_UNTRUSTED")
            current_manifest = inspect_candidate(actual_target)
            record = _read_limited(state_path)
            phase = record.get("upgrade_phase")
            _need(phase in {
                "ACTIVE", "SWITCH_PREPARED", "POST_SWITCH_VERIFY",
                "ROLLBACK_PREPARED", "ROLLED_BACK",
                "RECONCILE_REQUIRED",
            }, "RELEASE_PHASE_UNRECOGNIZED")
            old = record.get("last_known_good_release")
            candidate = record.get("candidate_release")
            expected_active = record.get("active_release")
            _need(isinstance(expected_active, str)
                  and Path(expected_active).is_absolute()
                  and Path(expected_active).parent == RELEASES,
                  "RELEASE_STATE_IDENTITY_MISMATCH")
            maybe_paths = {expected_active}
            for value in (old, candidate):
                if value is not None:
                    _need(isinstance(value, str)
                          and Path(value).is_absolute()
                          and Path(value).parent == RELEASES,
                          "RELEASE_STATE_PATH_UNTRUSTED")
                    maybe_paths.add(value)
            _need(str(actual_target) in maybe_paths,
                  "RELEASE_SYMLINK_OUTSIDE_JOURNAL")
            if (phase in {"ACTIVE", "ROLLED_BACK"}
                    and str(actual_target) == expected_active
                    and record.get("active_git_revision")
                        == current_manifest.git_revision):
                return {
                    "status": "READ_ONLY_RELEASE_STATE_CONSISTENT",
                    "upgrade_phase": phase,
                    "active_release_id": current_manifest.release_id,
                    "automatic_rollback": False,
                    "admissions_resumed": False,
                    "pointer_mutated": False,
                }
            release_id = (Path(candidate).name
                          if isinstance(candidate, str) else None)
            fence = observe_admission_fence_readonly(
                expected_release_id=release_id)
            return {
                "status": "RELEASE_RECONCILE_REQUIRED",
                "reason_code": "INTERRUPTED_OR_AMBIGUOUS_RELEASE_TRANSACTION",
                "upgrade_phase": phase,
                "active_release_id": current_manifest.release_id,
                "pointer_matches_candidate": (
                    candidate is not None
                    and str(actual_target) == candidate),
                "pointer_matches_prior": (
                    old is not None and str(actual_target) == old),
                "admission_fence_confirmed": (
                    fence.get("admissions_stopped_positive") is True),
                "manual_recovery_required": True,
                "automatic_rollback": False,
                "admissions_resumed": False,
                "pointer_mutated": False,
                "backend_replayed": False,
            }
    except (OSError, ValueError, ReleaseUnavailable,
            CapabilityStoreError) as exc:
        return {
            **refusal,
            "reason_code": getattr(
                exc, "code", "RELEASE_STORAGE_OR_LOCK_UNAVAILABLE"),
        }


def switch_release_after_acceptance(
    *,
    active_path: Path = ACTIVE,
    candidate_dir: Path,
    proof: QuiescenceProof,
) -> dict[str, Any]:
    """Serialize quiescence, switch, postcheck and rollback with admissions.

    A quiescence read followed by an unlocked symlink switch would race
    with a different release operator removing the admission fence, or
    with a fresh Capability admission. Hold the SAME canonical flock
    continuously through the entire release transaction. Shared mode
    permits nested read-only fence inspection; both fence removal and
    new admission require exclusive ownership.
    """
    _need(_RELEASE_SWITCH_ACCEPTED, "RELEASE_SWITCH_GATE_CLOSED")
    from automation.capability_job_store import _locked, SUBMISSIONS
    # Admission SH prevents new jobs/fence removal; a distinct exclusive
    # release transaction flock prevents TWO concurrent switch operators
    # from both reading the same old release and attempting a double flip.
    # Lock acquisition order is stable: release transaction -> admission.
    with _locked(SUBMISSIONS / ".release-transaction.lock"):
        with _locked(SUBMISSIONS / ".admission.lock", shared=True):
            return _switch_release_under_admission_lock(
                active_path=active_path, candidate_dir=candidate_dir,
                proof=proof,
            )


def _switch_release_under_admission_lock(
    *,
    active_path: Path,
    candidate_dir: Path,
    proof: QuiescenceProof,
) -> dict[str, Any]:
    """One signed candidate, one switch and at most one guarded rollback.

    Called ONLY with admission flock held; the frozen release gate is
    independently checked by the public entrypoint before lock acquisition.
    """
    _need(_RELEASE_SWITCH_ACCEPTED, "RELEASE_SWITCH_GATE_CLOSED")
    _need(active_path == ACTIVE, "RELEASE_PATH_UNTRUSTED")
    # The caller's QuiescenceProof is NOT the release authority. The
    # function re-observes signed candidate, admission fence, native
    # mutator absence and offline gates below before any write.
    # No caller callback or CLI-supplied boolean can authorize release
    # health or rollback; only fixed independent source evidence is used.
    from automation.release_postcheck import (
        positive_health_after_switch_readonly,
        positive_no_effect_since_switch_readonly,
    )
    from automation.authoritative_state_reader import (
        observe_authoritative_state,
    )
    _need(active_path.is_symlink(), "ACTIVE_RELEASE_NOT_SYMLINK")
    current_target = Path(os.readlink(active_path))
    _need(current_target.is_absolute() and current_target.parent == RELEASES,
          "ACTIVE_RELEASE_PATH_UNTRUSTED")
    active_manifest = inspect_candidate(current_target)
    candidate = inspect_candidate(candidate_dir)
    # "candidate_signature_verified" in an external proof is insufficient
    # by itself. Recheck the pinned offline key + full candidate inventory
    # at the actual switch boundary, before any symlink mutation.
    from automation.release_integrity import (
        ReleaseIntegrityUnavailable, verify_signed_candidate_readonly,
    )
    try:
        signed = verify_signed_candidate_readonly(candidate_dir)
    except ReleaseIntegrityUnavailable as exc:
        raise ReleaseUnavailable(exc.code) from exc
    _need(signed.get("signature_verified") is True
          and signed.get("all_listed_files_match") is True,
          "RELEASE_SIGNATURE_UNVERIFIED")
    # Do NOT let the caller manufacture the quiescence proof from booleans.
    # The release executor itself reads the existing canonical admission
    # fence, active jobs, signed candidate and native/CI source receipts.
    from automation.release_quiescence import (
        inspect_upgrade_quiescence_readonly,
    )
    facts = inspect_upgrade_quiescence_readonly(
        candidate_dir=candidate_dir)
    _need(facts.get("quiescence_complete") is True
          and facts.get("active_jobs_quiescent") is True
          and facts.get("admission_fence_proven") is True
          and facts.get("native_ui_mutators_absent_proven") is True
          and facts.get("offline_gates_accepted") is True,
          "UPGRADE_REQUIRES_POSITIVE_QUIESCENCE")
    proof = QuiescenceProof(
        admissions_stopped=True,
        live_ui_mutators_absent=True,
        android_ui_claim_resolved=(
            facts.get("android_ui_claim_resolved") is True),
        unsafe_effects_resolved=(
            facts.get("unsafe_capability_outcomes_resolved") is True),
        candidate_owner_mode_verified=True,
        candidate_signature_verified=True,
        offline_gates_passed=True,
    )
    _need(proof.complete(), "UPGRADE_REQUIRES_POSITIVE_QUIESCENCE")
    plan = plan_upgrade(
        active=active_manifest,
        candidate=candidate,
        quiescence=proof,
        explicit_maintenance_authorization=False,
    )
    _need(plan["reason_code"] == "READY_FOR_SEPARATE_ACTIVATION",
          plan["reason_code"])
    _need(candidate.upgrade_class == "PATCH_SAFE",
          "MAINTENANCE_AUTHORIZATION_REQUIRED")
    state = _read_limited(RELEASE_STATE)
    _need(state.get("active_release") == str(current_target)
          and state.get("active_git_revision") == active_manifest.git_revision,
          "RELEASE_STATE_IDENTITY_MISMATCH")
    # Record the exact root-owned switch baseline before touching the
    # active symlink. The subsequent postcheck/rollback must compare
    # independent fresh evidence against THIS durable snapshot.
    baseline = observe_authoritative_state()
    staged = {
        **state,
        "switch_baseline_boot_id": baseline.boot_id,
        "switch_baseline_epoch": baseline.state_epoch,
        "switch_baseline_revision": baseline.revision,
        "switch_baseline_boottime_ms": baseline.observed_boottime_ms,
        "candidate_release": str(candidate_dir),
        "last_known_good_release": str(current_target),
        "upgrade_phase": "SWITCH_PREPARED",
        "last_upgrade_result": "PENDING",
    }
    _save_release_state(RELEASE_STATE, staged)
    _atomic_release_link(active_path, candidate_dir)
    switched = {
        **staged,
        "active_release": str(candidate_dir),
        "active_git_revision": candidate.git_revision,
        "patch_level": candidate.patch_level,
        "migration_level": candidate.migration_level,
        "upgrade_phase": "POST_SWITCH_VERIFY",
    }
    _save_release_state(RELEASE_STATE, switched)
    healthy = False
    try:
        healthy = positive_health_after_switch_readonly(
            candidate_dir=candidate_dir, baseline=switched)
    except Exception:
        healthy = False
    if healthy:
        _save_release_state(RELEASE_STATE, {
            **switched,
            "candidate_release": None,
            "upgrade_phase": "ACTIVE",
            "last_upgrade_result": "SUCCEEDED",
        })
        return {
            "status": "ACTIVATED",
            "new_release": candidate.release_id,
            "rollback_attempts": 0,
        }

    # No replay or rollback after candidate-owned mutations/effects or when
    # the fact cannot be positively observed. One attempt only.
    safe_to_rollback = False
    try:
        safe_to_rollback = (
            positive_no_effect_since_switch_readonly(
                candidate_dir=candidate_dir, baseline=switched)
            and candidate.rollback_compatible
        )
    except Exception:
        safe_to_rollback = False
    if not safe_to_rollback:
        _save_release_state(RELEASE_STATE, {
            **switched,
            "upgrade_phase": "RECONCILE_REQUIRED",
            "last_upgrade_result": "ROLLBACK_NOT_SAFE",
        })
        raise ReleaseUnavailable("UPGRADE_RECONCILE_REQUIRED")
    _save_release_state(RELEASE_STATE, {
        **switched,
        "upgrade_phase": "ROLLBACK_PREPARED",
        "last_upgrade_result": "POST_SWITCH_HEALTH_FAILED",
    })
    _atomic_release_link(active_path, current_target)
    _save_release_state(RELEASE_STATE, {
        **state,
        "active_release": str(current_target),
        "active_git_revision": active_manifest.git_revision,
        "last_known_good_release": str(current_target),
        "candidate_release": str(candidate_dir),
        "upgrade_phase": "ROLLED_BACK",
        "last_upgrade_result": "AUTO_ROLLBACK_ONCE",
    })
    raise ReleaseUnavailable("UPGRADE_ROLLED_BACK")
