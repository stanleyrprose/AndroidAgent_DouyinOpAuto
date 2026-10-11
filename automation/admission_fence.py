"""Rev3.7 shared admission fence for quiescent release upgrades.

One root-owned durable fence, under the SAME submission admission flock
used by CapabilityStore.admit(), ensures a newly admitted capability
cannot appear after release quiescence is established.

Only a trusted foreground release operator may install/remove it. All
mutation gates are source-level CLOSED until final review and acceptance.
Read-only inspection cannot change the fence or grant execution rights.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import errno
import os
import re
import stat

from automation.capability_job_store import (
    SUBMISSIONS, CapabilityStoreError,
    _locked, _read_json, _atomic_new, _need,
)
from automation.authoritative_state_reader import (
    AuthorityUnavailable, observe_authoritative_state,
)

FENCE_PATH = SUBMISSIONS / "release-admission-fence.json"
_LOCK_PATH = SUBMISSIONS / ".admission.lock"
_FENCE_MUTATION_ACCEPTED = False
_RELEASE_ID = re.compile(r"^[A-Za-z0-9_.-]{8,120}$")


class AdmissionFenceUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


_RELEASE_OPERATOR_PROOF_SOURCE_ACCEPTED = False
_RELEASE_OPERATOR_ROOT = Path("/opt/y700/runtime/release-operator-authorizations")


def _require_release_operator_authority(
    *, release_id: str, action: str,
) -> str:
    """A bool passed by a CLI does not establish release operator identity.

    Exact action/release are attested by the separately authenticated
    first-party controller and persisted as a root-only one-use grant.
    Absence, staleness, clock ambiguity or a changed SOT is a refusal.
    """
    if not _RELEASE_OPERATOR_PROOF_SOURCE_ACCEPTED:
        raise AdmissionFenceUnavailable(
            "RELEASE_OPERATOR_PROOF_SOURCE_NOT_ACCEPTED")
    from datetime import datetime, timezone
    from automation.trusted_ingress_approval import (
        _root_owned_record, _utc, IngressAuthorizationUnavailable,
    )
    if action not in {"INSTALL_FENCE", "REMOVE_FENCE"}:
        raise AdmissionFenceUnavailable("RELEASE_OPERATOR_ACTION_INVALID")
    try:
        before = observe_authoritative_state()
        proof = _root_owned_record(
            _RELEASE_OPERATOR_ROOT / (release_id + "-" + action + ".json"))
        after = observe_authoritative_state()
        now = datetime.now(timezone.utc)
        signed = _utc(proof.get("approved_at"))
        expires = _utc(proof.get("expires_at"))
        principal = proof.get("approved_by")
    except (OSError, ValueError, IngressAuthorizationUnavailable,
            AuthorityUnavailable) as exc:
        raise AdmissionFenceUnavailable(
            "RELEASE_OPERATOR_PROOF_UNAVAILABLE") from exc
    if not (
        before.boot_id == after.boot_id
        and before.state_epoch == after.state_epoch
        and before.revision == after.revision
        and proof.get("operator_authorization_version") == 1
        and proof.get("source") == "TRUSTED_FIRST_PARTY_CONTROLLER"
        and proof.get("release_id") == release_id
        and proof.get("action") == action
        and proof.get("boot_id") == after.boot_id
        and proof.get("state_epoch") == after.state_epoch
        and proof.get("revision") == after.revision
        and proof.get("single_use") is True
        and isinstance(proof.get("nonce"), str)
        and len(proof["nonce"]) >= 16
        and isinstance(principal, dict)
        and principal.get("principal_type") == "TRUSTED_LOCAL_CONTROLLER"
        and isinstance(principal.get("principal_id"), str)
        and bool(principal["principal_id"])
        and signed <= now < expires
        and (expires - signed).total_seconds() <= 600
    ):
        raise AdmissionFenceUnavailable(
            "RELEASE_OPERATOR_PROOF_MISMATCH")
    return proof["nonce"]


def _consume_release_operator_grant(
    *, release_id: str, action: str, nonce: str,
) -> None:
    """Consume exactly one approved operation BEFORE mutating its fence.

    A crash after this fsync must require new explicit operator
    authorization; old one-use grants are never reusable via CLI retry.
    """
    import hashlib
    from automation.capability_job_store import _root_dir, _atomic_new
    consumed_root = SUBMISSIONS / "release-operator-consumptions"
    _root_dir(consumed_root)
    key = hashlib.sha256(
        (release_id + ":" + action + ":" + nonce).encode("utf-8")
    ).hexdigest()
    try:
        _atomic_new(consumed_root / (key + ".json"), {
            "operator_consumption_version": 1,
            "release_id": release_id,
            "action": action,
            "nonce_sha256": hashlib.sha256(nonce.encode()).hexdigest(),
            "consumed_before_fence_mutation": True,
        })
    except (CapabilityStoreError, OSError) as exc:
        # On the second call the file already exists. A previous attempt
        # might have crashed after consumption, so never auto-replay.
        raise AdmissionFenceUnavailable(
            "RELEASE_OPERATOR_GRANT_ALREADY_USED_OR_UNAVAILABLE") from exc


def assert_admission_unfenced_readonly(
    *, submissions_root: Path = SUBMISSIONS,
) -> None:
    """Under admission flock, only a proven ENOENT permits new admission.

    A permission failure, unreadable directory or malformed fence is
    NOT equivalent to no fence. Never follow a symlink or auto-expire a
    stale release fence after a reboot.
    """
    fence = submissions_root / "release-admission-fence.json"
    try:
        parent = os.lstat(submissions_root)
        if (not stat.S_ISDIR(parent.st_mode)
                or parent.st_uid != 0
                or stat.S_IMODE(parent.st_mode) != 0o700):
            raise AdmissionFenceUnavailable("ADMISSION_FENCE_ROOT_UNTRUSTED")
        entry = os.lstat(fence)
    except FileNotFoundError as exc:
        if exc.filename == str(fence):
            return
        raise AdmissionFenceUnavailable("ADMISSION_FENCE_ROOT_UNAVAILABLE") from exc
    except OSError as exc:
        raise AdmissionFenceUnavailable("ADMISSION_FENCE_UNAVAILABLE") from exc
    if not stat.S_ISREG(entry.st_mode):
        raise AdmissionFenceUnavailable("ADMISSION_FENCE_UNTRUSTED")
    try:
        record = _read_json(fence)
    except CapabilityStoreError as exc:
        raise AdmissionFenceUnavailable("ADMISSION_FENCE_CORRUPT") from exc
    if record.get("admission_fence_version") != 1:
        raise AdmissionFenceUnavailable("ADMISSION_FENCE_CORRUPT")
    # Even stale release fences must NOT auto-expire without positive
    # operator-confirmed clean lifecycle reconciliation.
    raise AdmissionFenceUnavailable("ADMISSIONS_PAUSED_FOR_RELEASE")


def observe_admission_fence_readonly(
    *, expected_release_id: str | None = None,
) -> dict[str, Any]:
    try:
        with _locked(_LOCK_PATH, shared=True):
            if not FENCE_PATH.exists() or FENCE_PATH.is_symlink():
                raise AdmissionFenceUnavailable("ADMISSION_FENCE_UNAVAILABLE")
            record = _read_json(FENCE_PATH)
            current = observe_authoritative_state()
            matched = (
                record.get("admission_fence_version") == 1
                and record.get("status") == "ACTIVE"
                and record.get("kernel_boot_id") == current.boot_id
                and isinstance(record.get("release_id"), str)
                and (
                    expected_release_id is None
                    or record["release_id"] == expected_release_id
                )
            )
            return {
                "status": "READ_ONLY_FENCE_OBSERVED"
                    if matched else "BLOCKED",
                "reason_code": None if matched
                    else "ADMISSION_FENCE_IDENTITY_MISMATCH",
                "admissions_stopped_positive": matched,
                "release_id": record.get("release_id") if matched else None,
                "fence_mutated": False,
                "release_switched": False,
            }
    except (OSError, ValueError,
            AdmissionFenceUnavailable, CapabilityStoreError) as exc:
        return {
            "status": "BLOCKED",
            "reason_code": getattr(
                exc, "code", "ADMISSION_FENCE_UNAVAILABLE"),
            "admissions_stopped_positive": False,
            "fence_mutated": False,
        }


def install_release_admission_fence(
    *, release_id: str, trusted_maintenance_session: bool,
) -> dict[str, Any]:
    if not _FENCE_MUTATION_ACCEPTED:
        raise AdmissionFenceUnavailable("ADMISSION_FENCE_GATE_CLOSED")
    if trusted_maintenance_session is not True:
        raise AdmissionFenceUnavailable("RELEASE_OPERATOR_UNVERIFIED")
    if not isinstance(release_id, str) or not _RELEASE_ID.fullmatch(release_id):
        raise AdmissionFenceUnavailable("RELEASE_ID_INVALID")
    with _locked(_LOCK_PATH):
        nonce = _require_release_operator_authority(
            release_id=release_id, action="INSTALL_FENCE")
        if FENCE_PATH.exists() or FENCE_PATH.is_symlink():
            raise AdmissionFenceUnavailable("ADMISSION_FENCE_ALREADY_EXISTS")
        boot = observe_authoritative_state()
        _consume_release_operator_grant(
            release_id=release_id, action="INSTALL_FENCE", nonce=nonce)
        _atomic_new(FENCE_PATH, {
            "admission_fence_version": 1,
            "status": "ACTIVE",
            "release_id": release_id,
            "kernel_boot_id": boot.boot_id,
            "state_epoch": boot.state_epoch,
            "revision_at_fence": boot.revision,
        })
    return {
        "status": "ADMISSIONS_PAUSED_FOR_RELEASE",
        "release_id": release_id,
        "jobs_started_by_operation": 0,
    }


def remove_release_admission_fence(
    *, expected_release_id: str, trusted_maintenance_session: bool,
) -> dict[str, Any]:
    """Never auto-open admission based on a clock or a failed health probe."""
    if not _FENCE_MUTATION_ACCEPTED:
        raise AdmissionFenceUnavailable("ADMISSION_FENCE_GATE_CLOSED")
    if trusted_maintenance_session is not True:
        raise AdmissionFenceUnavailable("RELEASE_OPERATOR_UNVERIFIED")
    if (not isinstance(expected_release_id, str)
            or _RELEASE_ID.fullmatch(expected_release_id) is None):
        raise AdmissionFenceUnavailable("RELEASE_ID_INVALID")
    with _locked(_LOCK_PATH):
        nonce = _require_release_operator_authority(
            release_id=expected_release_id, action="REMOVE_FENCE")
        existing = _read_json(FENCE_PATH)
        if (existing.get("status") != "ACTIVE"
                or existing.get("release_id") != expected_release_id):
            raise AdmissionFenceUnavailable("ADMISSION_FENCE_IDENTITY_MISMATCH")
        # A stale ACTIVE marker is NOT sufficient to reopen admission.
        # Reconcile release journal, exact candidate and the actual
        # symlink target under the admission flock already held here.
        from automation.release_lifecycle import (
            ACTIVE, RELEASES, RELEASE_STATE, _read_limited, inspect_candidate,
        )
        state = _read_limited(RELEASE_STATE)
        candidate = RELEASES / expected_release_id
        phase = state.get("upgrade_phase")
        active_release = state.get("active_release")
        if not ACTIVE.is_symlink():
            raise AdmissionFenceUnavailable("RELEASE_POINTER_UNAVAILABLE")
        actual = Path(os.readlink(ACTIVE))
        if (not actual.is_absolute()
                or actual.parent != RELEASES
                or str(actual) != active_release):
            raise AdmissionFenceUnavailable("RELEASE_POINTER_DRIFT")
        from automation.release_lifecycle import ReleaseUnavailable
        try:
            active_manifest = inspect_candidate(actual)
        except (ReleaseUnavailable, OSError) as exc:
            raise AdmissionFenceUnavailable(
                "RELEASE_ACTIVE_MANIFEST_UNAVAILABLE") from exc
        if state.get("active_git_revision") != active_manifest.git_revision:
            raise AdmissionFenceUnavailable("RELEASE_REVISION_DRIFT")
        if phase == "ACTIVE":
            if (active_release != str(candidate)
                    or state.get("candidate_release") is not None
                    or state.get("last_upgrade_result") != "SUCCEEDED"):
                raise AdmissionFenceUnavailable("RELEASE_RECOVERY_UNRESOLVED")
        elif phase == "ROLLED_BACK":
            prior = state.get("last_known_good_release")
            if (state.get("candidate_release") != str(candidate)
                    or not isinstance(prior, str)
                    or active_release != prior
                    or active_release == str(candidate)
                    or state.get("last_upgrade_result")
                        != "AUTO_ROLLBACK_ONCE"):
                raise AdmissionFenceUnavailable("RELEASE_RECOVERY_UNRESOLVED")
        else:
            raise AdmissionFenceUnavailable("RELEASE_RECOVERY_UNRESOLVED")
        # Independently confirm there is no still-owned Android UI Claim,
        # active Capability Job or partial staging admission before the
        # one-use operator grant is consumed and the fence is removed.
        from automation.resource_arbiter import read_claim, ResourceError
        from automation.recovery_inventory import (
            inspect_startup_inventory_readonly,
        )
        try:
            claim = read_claim()
        except ResourceError as exc:
            raise AdmissionFenceUnavailable(
                "ADMISSION_RESUME_RESOURCE_UNKNOWN") from exc
        if claim is not None:
            raise AdmissionFenceUnavailable(
                "ADMISSION_RESUME_RESOURCE_UNRESOLVED")
        inventory = inspect_startup_inventory_readonly()
        if (inventory.get("status") != "READ_ONLY_STARTUP_INVENTORY"
                or inventory.get("active_count") != 0
                or inventory.get("staging_count") != 0):
            raise AdmissionFenceUnavailable(
                "ADMISSION_RESUME_CAPABILITY_NOT_QUIESCENT")
        _consume_release_operator_grant(
            release_id=expected_release_id, action="REMOVE_FENCE",
            nonce=nonce)
        FENCE_PATH.unlink()
        from automation.capability_job_store import _fsync_directory
        _fsync_directory(FENCE_PATH.parent)
    return {
        "status": "ADMISSIONS_RESUMED",
        "release_id": expected_release_id,
        "effect_retried": False,
    }
