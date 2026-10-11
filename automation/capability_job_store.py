"""Rev3.7 durable capability admission and top-level backend binding.

The foreground Gateway must persist intent/identity/policy before a resource
claim or backend submission. This module is infrastructure, NOT an active
execution endpoint. It does not invoke Android, execute scripts, authorize
BUSINESS, or retry uncertain effects.

Only trusted, already-resolved Catalog/policy arguments belong here. The
caller request cannot override resource, replay, approval or backend identity.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, Iterator, Mapping

CAP_JOBS = Path("/opt/y700/capability-jobs")
SUBMISSIONS = Path("/opt/y700/runtime/submissions")
_SUBMISSION = re.compile(r"^[A-Za-z0-9_.-]{16,128}$")
_JOB = re.compile(r"^cap-[0-9a-f]{48}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_MAX_JSON = 256 * 1024
_PHASES = frozenset({
    "ADMITTED", "BACKEND_BOUND", "BACKEND_SUBMITTING", "WAITING_RESOURCE",
    "BACKEND_SUBMITTED", "BACKEND_RUNNING", "RUNNING_SAFE",
    "RUNNING_UNSAFE", "CANCELLING", "VERIFYING",
    "VERIFIED", "OUTCOME_NOT_ACHIEVED", "FAILED", "CANCELLED", "EXPIRED",
    "RECONCILE_REQUIRED", "BLOCKED_CLOCK_SUSPECT",
})
_TERMINAL = frozenset({"VERIFIED", "OUTCOME_NOT_ACHIEVED", "FAILED", "CANCELLED", "EXPIRED"})
_ARCHIVE_CLASS = {
    "VERIFIED": "verified", "OUTCOME_NOT_ACHIEVED": "outcome_not_achieved",
    "FAILED": "failed", "CANCELLED": "cancelled", "EXPIRED": "expired",
}


def inspect_public_commit_authority_readonly(
        source: Path, *, capability_job_id: str,
        backend_job_id: str, request_sha256: str,
        effective_policy_sha256: str,
        content_sha256: str, caption_sha256: str) -> bool:
    """Match one-use approval to the sole fsynced effect crossing.

    No missing/corrupt/symlinked authority is ever interpreted as a
    successful COMMIT. Both recovery and terminalization use this rule.
    """
    try:
        approval_path = source / "approval.json"
        effect_path = source / "effect-boundary.json"
        if (approval_path.is_symlink() or effect_path.is_symlink()
                or not approval_path.is_file() or not effect_path.is_file()):
            return False
        approval = _read_json(approval_path)
        effect = _read_json(effect_path)
        return (
            approval.get("approval_version") == 1
            and approval.get("approved") is True
            and approval.get("single_use") is True
            and approval.get("capability") == "tiktok.publish"
            and approval.get("capability_version") == "1.0"
            and approval.get("job_id") == capability_job_id
            and approval.get("request_sha256") == request_sha256
            and approval.get("effective_policy_sha256")
                == effective_policy_sha256
            and approval.get("content_sha256") == content_sha256
            and approval.get("caption_sha256") == caption_sha256
            and approval.get("visibility") == "PUBLIC"
            and approval.get("nonce") == approval.get("approval_nonce")
            and approval.get("approval_state") == "RECORDED"
            and isinstance(approval.get("approved_by"), dict)
            and bool(approval["approved_by"].get("principal_type"))
            and bool(approval["approved_by"].get("principal_id"))
            and isinstance(approval.get("approval_id"), str)
            and bool(approval["approval_id"])
            and isinstance(approval.get("approval_nonce"), str)
            and bool(approval["approval_nonce"])
            and effect.get("effect_boundary_version") == 1
            and effect.get("phase") == "EFFECT_BOUNDARY_CROSSED"
            and effect.get("boundary") == "before_final_publish"
            and effect.get("capability") == "tiktok.publish"
            and effect.get("capability_job_id") == capability_job_id
            and effect.get("backend_job_id") == backend_job_id
            and effect.get("request_sha256") == request_sha256
            and effect.get("effective_policy_sha256")
                == effective_policy_sha256
            and effect.get("content_sha256") == content_sha256
            and effect.get("visibility") == "PUBLIC"
            and effect.get("approval_id") == approval["approval_id"]
            and effect.get("approval_nonce") == approval["approval_nonce"]
            and effect.get("approval_sha256") == _sha(approval)
            and effect.get("external_effect_attempts_allowed") == 1
            and effect.get("external_effect_attempts_observed") == 0
        )
    except (OSError, ValueError, TypeError, CapabilityStoreError):
        return False


class CapabilityStoreError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _need(value: bool, code: str) -> None:
    if not value:
        raise CapabilityStoreError(code)


def _canonical(obj: Mapping[str, Any]) -> bytes:
    try:
        raw = json.dumps(
            obj, ensure_ascii=False, separators=(",", ":"),
            sort_keys=True, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CapabilityStoreError("JOB_PAYLOAD_INVALID") from exc
    _need(len(raw) <= _MAX_JSON, "JOB_PAYLOAD_TOO_LARGE")
    return raw


def _sha(obj: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _ttl_witness_matches(
        request: Mapping[str, Any],
        witness: Mapping[str, Any] | None,
        effective_policy: Mapping[str, Any]) -> bool:
    """Exact accepted intent and bounded same-boot deadline witness."""
    if not isinstance(witness, Mapping):
        return False
    try:
        deadline = datetime.fromisoformat(
            str(request["expires_at"]).replace("Z", "+00:00"))
        recorded = datetime.fromisoformat(
            str(witness["expires_at"]).replace("Z", "+00:00"))
        accepted = datetime.fromisoformat(
            str(witness["accepted_wall_time"]).replace("Z", "+00:00"))
        accepted_ms = witness["accepted_boottime_ms"]
        until_ms = witness["deadline_boottime_ms"]
        maximum = effective_policy["max_ttl_sec"]
        return (
            witness.get("ttl_clock_version") == 1
            and deadline.tzinfo is not None
            and recorded.tzinfo is not None
            and accepted.tzinfo is not None
            and deadline.astimezone(timezone.utc)
                == recorded.astimezone(timezone.utc)
            and isinstance(witness.get("accepted_boot_id"), str)
            and len(witness["accepted_boot_id"]) >= 32
            and type(accepted_ms) is int and accepted_ms >= 0
            and type(until_ms) is int and until_ms > accepted_ms
            and type(maximum) is int and 0 < maximum <= 86400
            and until_ms - accepted_ms <= maximum * 1000
        )
    except (ValueError, TypeError, KeyError, OverflowError):
        return False


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _expected_protected_owner(path: Path) -> int:
    """Root for fixed Y700 SOT; invoking uid for isolated Mac test roots.

    Production call sites do not accept caller-controlled storage roots.
    This preserves isolated temporary-file unit fixtures without making
    /opt/y700 root-owned records optional.
    """
    try:
        path.absolute().relative_to(Path("/opt/y700"))
        return 0
    except ValueError:
        return os.geteuid()


def _root_dir(path: Path) -> None:
    # Never silently follow a directory symlink into an untrusted location.
    _need(not path.is_symlink(), "CAPABILITY_PATH_UNTRUSTED")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    _need(path.is_dir(), "CAPABILITY_PATH_UNTRUSTED")
    st = path.stat()
    _need(st.st_uid == _expected_protected_owner(path)
          and stat.S_ISDIR(st.st_mode)
          and (stat.S_IMODE(st.st_mode) & 0o022) == 0,
          "CAPABILITY_PATH_OWNER_OR_MODE_UNTRUSTED")
    if path == CAP_JOBS or path == SUBMISSIONS:
        os.chmod(path, 0o700)


def _write_all(fd: int, data: bytes) -> None:
    """An interrupted/short write must not be mistaken for a durable record."""
    remaining = memoryview(data)
    while remaining:
        written = os.write(fd, remaining)
        _need(written > 0, "DURABLE_WRITE_INCOMPLETE")
        remaining = remaining[written:]


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _need(key not in result, "DURABLE_DUPLICATE_KEY")
        result[key] = value
    return result


def _atomic_new(path: Path, value: Mapping[str, Any]) -> None:
    """Exclusive O_EXCL creation. Call only under the admission/job lock."""
    raw = _canonical(value) + b"\n"
    _root_dir(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        _write_all(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_directory(path.parent)


def _atomic_replace(path: Path, value: Mapping[str, Any]) -> None:
    """Crash-safe replace with fsync; no mutable production release files."""
    _root_dir(path.parent)
    tmp = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    _atomic_new(tmp, value)
    try:
        os.replace(tmp, path)
        _fsync_directory(path.parent)
    finally:
        if tmp.exists():
            tmp.unlink()


def _read_json(path: Path) -> dict[str, Any]:
    """No-follow bounded single-inode read; never bootstrap missing state."""
    import stat
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise CapabilityStoreError("DURABLE_STATE_UNAVAILABLE") from exc
    try:
        before = os.fstat(fd)
        _need(stat.S_ISREG(before.st_mode)
              and before.st_uid == _expected_protected_owner(path)
              and stat.S_IMODE(before.st_mode) == 0o600
              and 0 < before.st_size <= _MAX_JSON,
              "DURABLE_STATE_CORRUPT")
        raw = bytearray()
        while len(raw) <= _MAX_JSON:
            part = os.read(fd, min(8192, _MAX_JSON + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        after = os.fstat(fd)
        _need(len(raw) == before.st_size
              and (before.st_dev, before.st_ino, before.st_size,
                   before.st_mtime_ns)
              == (after.st_dev, after.st_ino, after.st_size,
                  after.st_mtime_ns), "DURABLE_STATE_CHANGED_DURING_READ")
        try:
            out = json.loads(raw, object_pairs_hook=_no_duplicate_keys)
        except (UnicodeError, ValueError) as exc:
            raise CapabilityStoreError("DURABLE_STATE_CORRUPT") from exc
        _need(isinstance(out, dict), "DURABLE_STATE_CORRUPT")
        return out
    finally:
        os.close(fd)


def _append(path: Path, entry: Mapping[str, Any]) -> None:
    """Durable single-writer append; all call sites hold the job lock."""
    _root_dir(path.parent)
    row = _canonical(entry) + b"\n"
    fd = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_APPEND
        | getattr(os, "O_NOFOLLOW", 0), 0o600,
    )
    try:
        _write_all(fd, row)
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def _locked(path: Path, *, shared: bool = False) -> Iterator[None]:
    """Per-job transition flock; a shared status lookup NEVER creates files."""
    if shared or path.name == "transition.lock":
        _need(path.parent.is_dir() and not path.parent.is_symlink(),
              "CAPABILITY_PATH_UNTRUSTED")
        # A persisted job's lock is minted only in .staging before
        # publication. Missing lock = corrupt/incomplete identity, never
        # silently create a new lock inode (which would split owners).
        flags = (os.O_RDONLY if shared else os.O_RDWR) \
                | getattr(os, "O_NOFOLLOW", 0)
    else:
        _root_dir(path.parent)
        flags = (os.O_RDWR | os.O_CREAT
                 | getattr(os, "O_NOFOLLOW", 0))
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise CapabilityStoreError("TRANSITION_LOCK_UNAVAILABLE") from exc
    try:
        metadata = os.fstat(fd)
        _need(stat.S_ISREG(metadata.st_mode)
              and metadata.st_uid == _expected_protected_owner(path)
              and stat.S_IMODE(metadata.st_mode) == 0o600,
              "TRANSITION_LOCK_UNTRUSTED")
        fcntl.flock(fd, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _job_id(submission_id: str) -> str:
    _need(bool(_SUBMISSION.fullmatch(submission_id))
          and submission_id not in {".", ".."}, "SUBMISSION_ID_INVALID")
    return "cap-" + hashlib.sha256(
        ("rev37-capability-job-v1:" + submission_id).encode()
    ).hexdigest()[:48]


@dataclass(frozen=True)
class AdmittedJob:
    job_id: str
    path: Path
    request_sha256: str
    effective_policy_sha256: str
    replayed: bool


class CapabilityStore:
    """Durable admission, state and deterministic binding, no backend calls."""

    def __init__(self, jobs: Path = CAP_JOBS,
                 submissions: Path = SUBMISSIONS):
        self.jobs = jobs
        self.submissions = submissions

    @staticmethod
    def _request(request: Mapping[str, Any]) -> dict[str, Any]:
        _need(isinstance(request, Mapping), "JOB_PAYLOAD_INVALID")
        submission_id = request.get("submission_id")
        capability = request.get("capability")
        version = request.get("version")
        _need(isinstance(submission_id, str)
              and bool(_SUBMISSION.fullmatch(submission_id)),
              "SUBMISSION_ID_INVALID")
        _need(isinstance(capability, str)
              and bool(re.fullmatch(r"[a-z][a-z0-9_.]{2,96}", capability)),
              "CAPABILITY_REQUEST_INVALID")
        _need(isinstance(version, str)
              and bool(re.fullmatch(r"[0-9]+\.[0-9]+", version)),
              "CAPABILITY_REQUEST_INVALID")
        _need(isinstance(request.get("payload"), dict), "JOB_PAYLOAD_INVALID")
        for forbidden in (
            "resources", "approval", "verification", "replay", "backend_job_id",
            "effective_policy", "execution_route", "resource_guard",
        ):
            _need(forbidden not in request, "CALLER_POLICY_OVERRIDE_DENIED")
        _canonical(request)
        return dict(request)

    def admit(self, request: Mapping[str, Any],
              *, trusted_contract: Mapping[str, Any],
              trusted_effective_policy: Mapping[str, Any],
              ttl_clock_evidence: Mapping[str, Any] | None = None) -> AdmittedJob:
        """Unique stable mapping: same submission + altered request fails."""
        req = self._request(request)
        _need(isinstance(trusted_contract, Mapping)
              and trusted_contract.get("capability") == req["capability"]
              and trusted_contract.get("version") == req["version"],
              "RUNTIME_CONTRACT_MISMATCH")
        _need(isinstance(trusted_effective_policy, Mapping)
              and trusted_effective_policy.get("version") == 1,
              "POLICY_UNRESOLVED")
        submission_id = req["submission_id"]
        job_id = _job_id(submission_id)
        request_hash = _sha(req)
        policy_hash = _sha(trusted_effective_policy)
        _root_dir(self.jobs)
        _root_dir(self.submissions)
        # Submission index is the sole binding SOT for transport retries.
        bind = self.submissions / (
            hashlib.sha256(submission_id.encode()).hexdigest() + ".json")
        active_root = self.jobs / "active"
        staging_root = self.jobs / ".staging"
        _root_dir(active_root)
        _root_dir(staging_root)
        job = active_root / job_id
        stage = staging_root / job_id
        with _locked(self.submissions / ".admission.lock"):
            _need(not bind.is_symlink(),
                  "SUBMISSION_BINDING_PATH_UNTRUSTED")
            # Read-only transport replays may still inspect their existing
            # immutable binding while an upgrade fence is installed.
            # Brand-new admissions and partial-index recovery are stopped
            # under this SAME canonical flock.
            if bind.exists():
                previous = _read_json(bind)
                _need(previous.get("capability_job_id") == job_id
                      and previous.get("request_sha256") == request_hash
                      and previous.get("effective_policy_sha256") == policy_hash,
                      "SUBMISSION_IDENTITY_CONFLICT")
                # The durable binding is written BEFORE activation.
                # Crash after binding fsync but before stage -> active
                # rename must finish only the exact same pre-side-effect
                # stage, never allocate another capability ID or backend.
                if (stage.exists() or stage.is_symlink()):
                    # Merely *reading* an existing binding is allowed during
                    # release freeze; stage -> active activation is not.
                    from automation.admission_fence import (
                        assert_admission_unfenced_readonly,
                        AdmissionFenceUnavailable,
                    )
                    try:
                        assert_admission_unfenced_readonly(
                            submissions_root=self.submissions)
                    except AdmissionFenceUnavailable as exc:
                        raise CapabilityStoreError(exc.code) from exc
                    _need(not job.exists() and not job.is_symlink()
                          and stage.is_dir() and not stage.is_symlink(),
                          "ADMISSION_ACTIVATION_CONFLICT")
                    staged_request = _read_json(stage / "request.json")
                    staged_policy = _read_json(stage / "effective_policy.json")
                    staged_identity = _read_json(stage / "identity.json")
                    staged_state = _read_json(stage / "state.json")
                    _need(
                        _sha(staged_request) == request_hash
                        and _sha(staged_policy) == policy_hash
                        and staged_identity.get("capability_job_id") == job_id
                        and staged_identity.get("request_sha256")
                            == request_hash
                        and staged_identity.get("effective_policy_sha256")
                            == policy_hash
                        and staged_state.get("capability_job_id") == job_id
                        and staged_state.get("request_sha256")
                            == request_hash
                        and staged_state.get("effective_policy_sha256")
                            == policy_hash
                        and staged_state.get("phase") == "ADMITTED"
                        and staged_state.get("state_revision") == 0
                        and staged_state.get("backend_submitted") is False
                        and staged_state.get("effect_uncertain") is False
                        and staged_state.get("mutation_uncertain") is False
                        and not (stage / "backend.json").exists()
                        and not (stage / "effect-boundary.json").exists()
                        and not (stage / "cancel.json").exists()
                        and not (stage / "result.json").exists()
                        and not (stage / "backend-execution.json").exists(),
                        "ADMISSION_STAGING_RECONCILE_REQUIRED",
                    )
                    if req.get("expires_at") is not None:
                        staged_ttl = _read_json(stage / "ttl-clock.json")
                        _need(_ttl_witness_matches(
                                  staged_request, staged_ttl,
                                  staged_policy),
                              "ADMISSION_RECOVERY_CLOCK_UNAVAILABLE")
                    _need(
                        not (stage / "transition.lock").is_symlink()
                        and (stage / "transition.lock").is_file()
                        and (stage / "journal.jsonl").is_file()
                        and not (stage / "journal.jsonl").is_symlink(),
                        "ADMISSION_STAGING_RECORDS_INCOMPLETE",
                    )
                    _fsync_directory(stage)
                    os.replace(stage, job)
                    _fsync_directory(staging_root)
                    _fsync_directory(active_root)
                existing_job = self._locate_existing(job_id)
                stored_identity = _read_json(existing_job / "identity.json")
                _need(stored_identity.get("request_sha256") == request_hash
                      and stored_identity.get("effective_policy_sha256")
                          == policy_hash,
                      "ADMISSION_BINDING_BROKEN")
                return AdmittedJob(
                    job_id, existing_job, request_hash, policy_hash, True)
            from automation.admission_fence import (
                assert_admission_unfenced_readonly,
                AdmissionFenceUnavailable,
            )
            try:
                assert_admission_unfenced_readonly(
                            submissions_root=self.submissions)
            except AdmissionFenceUnavailable as exc:
                raise CapabilityStoreError(exc.code) from exc
            # In the frozen Rev3.7 ordering an activated Job without a
            # durable submission binding is a corruption/legacy migration
            # case, NEVER grounds for minting a new binding silently.
            _need(not job.exists() and not job.is_symlink(),
                  "ADMISSION_INDEX_MISSING_RECONCILE_REQUIRED")
            _need(not stage.exists() and not stage.is_symlink(),
                  "ADMISSION_STAGING_RECONCILE_REQUIRED")
            if req.get("expires_at") is not None:
                _need(_ttl_witness_matches(
                          req, ttl_clock_evidence, trusted_effective_policy),
                      "TTL_ACCEPTANCE_EVIDENCE_UNAVAILABLE")
            stage.mkdir(mode=0o700)
            _fsync_directory(staging_root)
            _atomic_new(stage / "request.json", req)
            _atomic_new(stage / "identity.json", {
                "identity_version": 1,
                "capability_job_id": job_id,
                "submission_id_sha256":
                    hashlib.sha256(submission_id.encode()).hexdigest(),
                "request_sha256": request_hash,
                "effective_policy_sha256": policy_hash,
            })
            _atomic_new(stage / "effective_policy.json",
                        dict(trusted_effective_policy))
            if req.get("expires_at") is not None:
                # This clock witness belongs to initial admission, not
                # transport retries. Never rewrite it to extend validity.
                _atomic_new(stage / "ttl-clock.json",
                            dict(ttl_clock_evidence))
            # Lock file is part of the immutable published job directory,
            # so a read-only status call never creates a new inode.
            _atomic_new(stage / "transition.lock", {"lock_version": 1})
            _atomic_new(stage / "state.json", {
                "state_version": 1,
                "state_revision": 0,
                "lifecycle_state": "ADMITTED",
                "phase_reason_code": None,
                "phase": "ADMITTED",
                "capability_job_id": job_id,
                "request_sha256": request_hash,
                "effective_policy_sha256": policy_hash,
                "updated_at": _utc(),
                "backend_submitted": False,
                "effect_uncertain": False,
                "mutation_uncertain": False,
                "terminal": False,
            })
            _append(stage / "journal.jsonl", {
                "event": "ADMITTED",
                "timestamp": _utc(),
                "capability_job_id": job_id,
                "request_sha256": request_hash,
                "policy_sha256": policy_hash,
            })
            # Lock inode must already exist for strictly read-only status.
            with _locked(stage / "transition.lock"):
                pass
            _fsync_directory(stage)
            # Frozen §13 durable ordering: publish immutable submission
            # binding SOT BEFORE exposing an active Capability Job.
            # Crash now leaves the exact stage and binding, which replay
            # reactivates under the same admission flock without a new ID.
            _atomic_new(bind, {
                "submission_registry_version": 1,
                "capability_job_id": job_id,
                "request_sha256": request_hash,
                "effective_policy_sha256": policy_hash,
            })
            _need(not job.exists() and not job.is_symlink(),
                  "ADMISSION_ACTIVATION_CONFLICT")
            os.replace(stage, job)
            _fsync_directory(staging_root)
            _fsync_directory(active_root)
        return AdmittedJob(job_id, job, request_hash, policy_hash, False)

    def bind_backend(self, admitted: AdmittedJob, *,
                     backend_type: str) -> dict[str, Any]:
        """Backend identity BEFORE resources or submission, no execution."""
        _need(backend_type in {
                  "ui_workflow", "publisher", "root_exec", "observation"
              },
              "BACKEND_TYPE_UNSUPPORTED")
        suffix = {
            "ui_workflow": "ui", "publisher": "publisher",
            "root_exec": "root", "observation": "observe",
        }[backend_type]
        backend_id = f"{admitted.job_id}--{suffix}-01"
        path = admitted.path
        with _locked(path / "transition.lock"):
            state = _read_json(path / "state.json")
            _need(not state.get("effect_uncertain")
                  and not state.get("mutation_uncertain"),
                  "RECONCILE_REQUIRED")
            _need(state.get("phase") in {"ADMITTED", "BACKEND_BOUND",
                                          "WAITING_RESOURCE"},
                  "BACKEND_ALREADY_ACTIVE")
            binding = {
                "backend_binding_version": 1,
                "capability_job_id": admitted.job_id,
                "backend_type": backend_type,
                "backend_job_id": backend_id,
                "request_sha256": admitted.request_sha256,
                "created_at": _utc(),
            }
            backend_file = path / "backend.json"
            if backend_file.exists():
                old = _read_json(backend_file)
                execution = _read_json(path / "backend-execution.json")
                _need(execution.get("backend_job_id") == backend_id,
                      "BACKEND_EXECUTION_BINDING_BROKEN")
                _need(all(old.get(k) == binding[k] for k in (
                    "capability_job_id", "backend_type", "backend_job_id",
                    "request_sha256")), "JOB_CONTRACT_VIOLATION")
                return old
            _atomic_new(backend_file, binding)
            _atomic_new(path / "backend-execution.json", {
                "backend_execution_version": 1,
                "capability_job_id": admitted.job_id,
                "backend_job_id": backend_id,
                "request_sha256": admitted.request_sha256,
                "phase": "NEVER_CREATED",
                "submission_possible": False,
                "attempt_serial": 0,
                "updated_at": _utc(),
            })
            self._advance_locked(path, state, "BACKEND_BOUND",
                                 {"backend_job_id": backend_id})
            return binding

    def record_pre_submit_prerequisite_block(
        self, admitted: AdmittedJob, *, reason_code: str,
    ) -> None:
        """Durable bounded availability block eligible for exact-ID retry.

        Only a trusted coordinator can record an allowlisted transient
        prerequisite failure BEFORE any Backend could have been created.
        This status never constitutes permission to submit again: a
        subsequent invocation must independently re-check the original
        Backend ID, current policy, state, TTL and resource ownership.
        """
        accepted = frozenset({
            "CLOCK_SUSPECT_PRE_SUBMIT",
            "RESOURCE_BUSY_PRE_SUBMIT",
        })
        _need(reason_code in accepted, "PRE_SUBMIT_REASON_NOT_RETRIABLE")
        with _locked(admitted.path / "transition.lock"):
            state = _read_json(admitted.path / "state.json")
            binding = _read_json(admitted.path / "backend.json")
            execution = _read_json(
                admitted.path / "backend-execution.json")
            _need(state.get("phase") in {
                      "BACKEND_BOUND", "WAITING_RESOURCE",
                  }
                  and state.get("backend_submitted") is False
                  and state.get("effect_uncertain") is False
                  and state.get("mutation_uncertain") is False
                  and not (admitted.path / "cancel.json").exists()
                  and not (admitted.path / "result.json").exists()
                  and not (admitted.path / "effect-boundary.json").exists()
                  and binding.get("capability_job_id") == admitted.job_id
                  and binding.get("request_sha256")
                      == admitted.request_sha256
                  and execution.get("backend_job_id")
                      == binding.get("backend_job_id")
                  and execution.get("request_sha256")
                      == admitted.request_sha256
                  and execution.get("phase") == "NEVER_CREATED"
                  and execution.get("submission_possible") is False
                  and execution.get("attempt_serial") == 0,
                  "PRE_SUBMIT_NEVER_CREATED_UNPROVEN")
            if (state.get("phase") == "WAITING_RESOURCE"
                    and state.get("phase_reason_code") == reason_code):
                return
            self._advance_locked(
                admitted.path, state, "WAITING_RESOURCE",
                {"reason_code": reason_code},
            )

    def begin_backend_submission(
        self, admitted: AdmittedJob, *,
        exact_backend_job_id: str,
        exact_resource_claim: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Durably close the never-created window BEFORE external call.

        If a crash happens after this fsync but before backend submission,
        recovery must conservatively reconcile this SAME Backend ID. A
        transport retry cannot create a second attempt. The caller owns
        the canonical claim for the entire synchronous dispatch lifetime.
        """
        from automation import resource_arbiter
        from automation.admission_fence import (
            assert_admission_unfenced_readonly, AdmissionFenceUnavailable,
        )
        # A previously admitted job must not start its FIRST Backend call
        # after an upgrade fence has been fsynced. Hold the SAME shared
        # admission flock throughout the durable SUBMISSION_POSSIBLE write:
        # upgrade installation uses exclusive admission flock, preventing
        # the classic "quiescent -> new backend appears" race.
        with _locked(self.submissions / ".admission.lock", shared=True), \
                _locked(admitted.path / "transition.lock"):
            try:
                assert_admission_unfenced_readonly(
                            submissions_root=self.submissions)
            except AdmissionFenceUnavailable as exc:
                raise CapabilityStoreError(exc.code) from exc
            _need(not (admitted.path / "result.json").exists()
                  and not (admitted.path / "cancel.json").exists()
                  and not (admitted.path / "effect-boundary.json").exists(),
                  "BACKEND_SUBMISSION_NOT_ALLOWED")
            state = _read_json(admitted.path / "state.json")
            binding = _read_json(admitted.path / "backend.json")
            witness = _read_json(admitted.path / "backend-execution.json")
            _need(state.get("phase") in {"BACKEND_BOUND",
                                         "WAITING_RESOURCE"}
                  and state.get("backend_submitted") is False
                  and state.get("effect_uncertain") is False
                  and state.get("mutation_uncertain") is False,
                  "BACKEND_ALREADY_ACTIVE")
            _need(binding.get("backend_job_id") == exact_backend_job_id
                  and binding.get("request_sha256")
                      == admitted.request_sha256
                  and witness.get("backend_job_id") == exact_backend_job_id
                  and witness.get("request_sha256")
                      == admitted.request_sha256
                  and witness.get("phase") == "NEVER_CREATED"
                  and witness.get("submission_possible") is False
                  and witness.get("attempt_serial") == 0,
                  "BACKEND_SUBMISSION_RECONCILE_REQUIRED")
            if binding.get("backend_type") in {"publisher", "ui_workflow"}:
                _need(isinstance(exact_resource_claim, Mapping),
                      "RESOURCE_OWNERSHIP_REQUIRED")
                try:
                    claim = resource_arbiter.assert_guard(
                        dict(exact_resource_claim))
                except resource_arbiter.ResourceError as exc:
                    raise CapabilityStoreError(
                        "STALE_RESOURCE_OWNERSHIP") from exc
                _need(claim.get("owner_kind") == "CAPABILITY"
                      and claim.get("capability_job_id") == admitted.job_id
                      and claim.get("backend_job_id")
                          == exact_backend_job_id
                      and claim.get("request_sha256")
                          == admitted.request_sha256,
                      "RESOURCE_IDENTITY_MISMATCH")
            elif exact_resource_claim is not None:
                raise CapabilityStoreError("RESOURCE_CONTRACT_MISMATCH")

            possible = dict(witness)
            possible.update(
                phase="SUBMISSION_POSSIBLE",
                submission_possible=True,
                attempt_serial=1,
                updated_at=_utc(),
                resource_guard={
                    "resource": "android_ui",
                    "claim_id": exact_resource_claim["claim_id"],
                    "owner_id": exact_resource_claim["owner_id"],
                } if exact_resource_claim is not None else None,
            )
            _atomic_replace(admitted.path / "backend-execution.json", possible)
            self._advance_locked(
                admitted.path, state, "BACKEND_SUBMITTING",
                {"reason_code": "BACKEND_SUBMISSION_MAY_HAVE_STARTED",
                 "mutation_uncertain": True},
            )
            return {
                "status": "SUBMISSION_POSSIBLE",
                "capability_job_id": admitted.job_id,
                "backend_job_id": exact_backend_job_id,
                "attempt_serial": 1,
                "repeat_submission_allowed": False,
            }

    def record_backend_submission(
        self, admitted: AdmittedJob, *,
        exact_backend_job_id: str,
        backend_identity_confirmed: bool,
    ) -> None:
        """Persist that the ONE bound backend was submitted, never allocate."""
        _need(backend_identity_confirmed is True,
              "BACKEND_SUBMISSION_UNVERIFIED")
        with _locked(admitted.path / "transition.lock"):
            binding = _read_json(admitted.path / "backend.json")
            state = _read_json(admitted.path / "state.json")
            _need(binding.get("backend_job_id") == exact_backend_job_id
                  and binding.get("request_sha256")
                      == admitted.request_sha256,
                  "JOB_CONTRACT_VIOLATION")
            # Advanced phases are legal ONLY as idempotent observations:
            # never regress RUNNING_UNSAFE/VERIFYING back to SUBMITTED when
            # a delayed Backend ACK arrives or an inconsistent state exists.
            _need(state.get("phase") in {"BACKEND_SUBMITTING",
                                          "BACKEND_SUBMITTED",
                                          "RUNNING_SAFE", "RUNNING_UNSAFE",
                                          "VERIFYING"},
                  "BACKEND_STATE_INVALID")
            if state.get("backend_submitted") is True:
                _need(state.get("phase") in {"BACKEND_SUBMITTED",
                                               "RUNNING_SAFE", "RUNNING_UNSAFE",
                                               "VERIFYING"},
                      "BACKEND_STATE_INVALID")
                execution = _read_json(
                    admitted.path / "backend-execution.json")
                _need(
                    execution.get("backend_job_id") == exact_backend_job_id
                    and execution.get("request_sha256")
                        == admitted.request_sha256
                    and execution.get("phase") == "SUBMITTED_ACKNOWLEDGED"
                    and execution.get("attempt_serial") == 1,
                    "BACKEND_IDEMPOTENT_ACK_CONFLICT",
                )
                return
            _need(state.get("phase") == "BACKEND_SUBMITTING",
                  "BACKEND_STATE_REGRESSION_DENIED")
            execution = _read_json(admitted.path / "backend-execution.json")
            _need(execution.get("phase") == "SUBMISSION_POSSIBLE"
                  and execution.get("attempt_serial") == 1,
                  "BACKEND_SUBMISSION_WITNESS_MISSING")
            accepted = dict(execution)
            accepted.update(phase="SUBMITTED_ACKNOWLEDGED",
                            updated_at=_utc())
            _atomic_replace(admitted.path / "backend-execution.json", accepted)
            self._advance_locked(
                admitted.path, state, "BACKEND_SUBMITTED",
                {"backend_submitted": True,
                 "reason_code": "EXACT_BACKEND_ID_SUBMITTED",
                 "mutation_uncertain": False},
            )

    def mark_backend_uncertain(
        self, admitted: AdmittedJob, *,
        reason_code: str,
        effect_may_have_occurred: bool,
    ) -> None:
        """Uncertain submit/effect never becomes FAILED or retry-eligible."""
        with _locked(admitted.path / "transition.lock"):
            state = _read_json(admitted.path / "state.json")
            if state.get("phase") == "RECONCILE_REQUIRED":
                return
            _need(not state.get("terminal"), "CAPABILITY_JOB_TERMINAL")
            self._advance_locked(
                admitted.path, state, "RECONCILE_REQUIRED",
                {"backend_submitted": state.get("backend_submitted") is True,
                 "effect_uncertain": bool(effect_may_have_occurred),
                 "mutation_uncertain": True,
                 "reason_code": reason_code[:120]},
            )

    def _advance_locked(self, path: Path, old: Mapping[str, Any],
                        phase: str, detail: Mapping[str, Any]) -> None:
        _need(phase in _PHASES, "CAPABILITY_PHASE_INVALID")
        _need(old.get("phase") in _PHASES, "DURABLE_STATE_CORRUPT")
        _need(not bool(old.get("terminal")), "CAPABILITY_JOB_TERMINAL")
        _need(phase not in _TERMINAL, "TERMINAL_RESULT_REQUIRED")
        _need(type(old.get("state_revision")) is int
              and old["state_revision"] >= 0,
              "STATE_STORE_CORRUPT")
        next_state = dict(old)
        next_state.update(
            phase=phase,
            lifecycle_state=phase,
            state_revision=old["state_revision"] + 1,
            phase_reason_code=str(detail.get("reason_code", ""))[:120] or None,
            updated_at=_utc(),
            terminal=False,
        )
        for flag in ("backend_submitted", "effect_uncertain",
                     "mutation_uncertain"):
            if flag in detail:
                _need(type(detail[flag]) is bool, "STATE_FLAG_INVALID")
                next_state[flag] = detail[flag]
        _atomic_replace(path / "state.json", next_state)
        _append(path / "journal.jsonl", {
            "event": "STATE_TRANSITION",
            "timestamp": next_state["updated_at"],
            "from": old["phase"],
            "to": phase,
            "reason_code": str(detail.get("reason_code", ""))[:120],
        })

    def advance_no_effect(self, job_id: str, *,
                          phase: str,
                          reason_code: str = "",
                          backend_never_created_positive_proof: bool = False) -> None:
        """Restricted pre-submit state transitions, never finalizes an effect."""
        _need(bool(_JOB.fullmatch(job_id)), "CAPABILITY_JOB_ID_INVALID")
        _need(phase in {"WAITING_RESOURCE", "BLOCKED_CLOCK_SUSPECT",
                        "EXPIRED", "CANCELLED"},
              "CAPABILITY_PHASE_FORBIDDEN")
        if phase in {"EXPIRED", "CANCELLED"}:
            self.finalize_terminal(
                job_id,
                outcome=phase,
                backend_never_created_proven=
                    backend_never_created_positive_proof is True,
                business_outcome_verified=False,
                reason_code=reason_code,
            )
            return
        job = self.jobs / "active" / job_id
        with _locked(job / "transition.lock"):
            state = _read_json(job / "state.json")
            _need(state.get("backend_submitted") is False
                  and state.get("effect_uncertain") is False
                  and state.get("mutation_uncertain") is False,
                  "PRE_SUBMIT_TERMINALIZATION_FORBIDDEN")
            self._advance_locked(job, state, phase,
                                 {"reason_code": reason_code})

    def finalize_terminal(
        self, job_id: str, *,
        outcome: str,
        backend_never_created_proven: bool,
        business_outcome_verified: bool,
        reason_code: str = "",
        exact_backend_id: str | None = None,
    ) -> dict[str, Any]:
        """Single durable result marker, then archive by final outcome.

        Pre-submit terminalization requires positive backend never-created
        evidence; post-submit final outcome requires independently verified
        backend/business facts. Uncertain outcomes remain in active/.
        """
        _need(bool(_JOB.fullmatch(job_id)), "CAPABILITY_JOB_ID_INVALID")
        _need(outcome in _TERMINAL, "TERMINAL_OUTCOME_INVALID")
        archive = self.jobs / "archive" / _ARCHIVE_CLASS[outcome]
        _root_dir(archive)
        source = self.jobs / "active" / job_id
        destination = archive / job_id
        if destination.exists() or destination.is_symlink():
            # A durable terminal archive is the final namespace. Seeing
            # the same Capability ID under active/ as well is corruption,
            # not a harmless idempotent replay.
            _need(destination.is_dir() and not destination.is_symlink()
                  and not source.exists() and not source.is_symlink(),
                  "TERMINAL_ARCHIVE_CONFLICT")
            result = _read_json(destination / "result.json")
            identity = _read_json(destination / "identity.json")
            _need(result.get("outcome") == outcome
                  and result.get("terminal") is True
                  and result.get("capability_job_id") == job_id
                  and result.get("request_sha256")
                      == identity.get("request_sha256")
                  and result.get("external_effect_retry_allowed") is False,
                  "TERMINAL_RESULT_CONFLICT")
            return result
        _need(source.is_dir() and not source.is_symlink(),
              "CAPABILITY_JOB_NOT_ACTIVE")
        with _locked(source / "transition.lock"):
            state = _read_json(source / "state.json")
            identity = _read_json(source / "identity.json")
            _need(state.get("capability_job_id") == job_id
                  and identity.get("capability_job_id") == job_id,
                  "CAPABILITY_IDENTITY_MISMATCH")
            _need(
                (not state.get("effect_uncertain")
                 and not state.get("mutation_uncertain"))
                or (business_outcome_verified is True
                    and outcome in {"VERIFIED", "OUTCOME_NOT_ACHIEVED"}
                    and exact_backend_id is not None),
                "RECONCILE_REQUIRED")
            effect_boundary_exists = (source / "effect-boundary.json").exists()
            _need(not effect_boundary_exists
                  or outcome in {"VERIFIED", "OUTCOME_NOT_ACHIEVED"},
                  "EFFECT_BOUNDARY_PREVENTS_CANCEL_OR_FAILURE")
            # A process may crash after the durable SUBMISSION_POSSIBLE
            # witness but before backend ACK/state.json is advanced. That
            # is NEVER "pre-submit" even if state.backend_submitted=False.
            execution_file = source / "backend-execution.json"
            execution = (
                _read_json(execution_file)
                if execution_file.exists() or execution_file.is_symlink()
                else None
            )
            submission_possible = (
                isinstance(execution, dict)
                and execution.get("submission_possible") is True
                and execution.get("attempt_serial") == 1
                and execution.get("phase") in {
                    "SUBMISSION_POSSIBLE", "SUBMITTED_ACKNOWLEDGED",
                }
            )
            already_submitted = (
                state.get("backend_submitted") is True
                or submission_possible
            )
            if already_submitted:
                _need(outcome in {"VERIFIED", "OUTCOME_NOT_ACHIEVED",
                                  "FAILED"},
                      "POST_SUBMIT_TERMINAL_OUTCOME_UNSUPPORTED")
                _need(business_outcome_verified is True
                      and exact_backend_id is not None,
                      "BACKEND_TERMINAL_PROOF_MISSING")
                binding = _read_json(source / "backend.json")
                _need(binding.get("backend_job_id") == exact_backend_id
                      and binding.get("capability_job_id") == job_id
                      and binding.get("request_sha256")
                          == identity["request_sha256"]
                      and execution is not None
                      and execution.get("backend_job_id") == exact_backend_id
                      and execution.get("request_sha256")
                          == identity["request_sha256"]
                      and submission_possible,
                      "JOB_CONTRACT_VIOLATION")
                # Final results need a capability-specific DURABLE receipt,
                # not only a returned bool or a successful Backend ACK.
                if outcome == "VERIFIED":
                    backend_type = binding.get("backend_type")
                    if backend_type == "publisher":
                        request = _read_json(source / "request.json")
                        payload = request.get("payload")
                        _need(isinstance(payload, dict),
                              "PUBLISHER_RECEIPT_UNAVAILABLE")
                        publisher_id = payload.get(
                            "existing_publisher_job_id")
                        _need(isinstance(publisher_id, str)
                              and re.fullmatch(
                                  r"[A-Za-z0-9_.-]{1,96}", publisher_id)
                              is not None,
                              "PUBLISHER_RECEIPT_UNAVAILABLE")
                        if payload.get("publish_mode") == "DRY_RUN":
                            preview = _read_json(
                                source / "publisher-dryrun-result.json")
                            _need(
                                preview.get("publisher_dryrun_result_version") == 1
                                and preview.get("capability_job_id") == job_id
                                and preview.get("backend_job_id")
                                    == exact_backend_id
                                and preview.get("publisher_job_id")
                                    == publisher_id
                                and preview.get("request_sha256")
                                    == identity["request_sha256"]
                                and preview.get("content_sha256")
                                    == payload.get("content_sha256")
                                and preview.get("caption_sha256")
                                    == payload.get("caption_sha256")
                                and preview.get("preview_state") == "POST_CONFIG"
                                and preview.get("caption_verified") is True
                                and preview.get("visibility") == "PUBLIC"
                                and preview.get("ui_cleanup_complete") is True
                                and preview.get("external_effect_attempts") == 0
                                and preview.get("external_effect_retry_allowed")
                                    is False
                                and not effect_boundary_exists,
                                "PUBLISHER_DRY_RUN_PROOF_MISSING")
                            # Publisher's UI cleanup claim alone is not a
                            # proof that every Android/UI Core descendant
                            # stopped. Do not terminalize a preview until
                            # exact accepted native quiescence is positive.
                            from automation.resource_stop_observer import (
                                positive_synchronous_ui_quiescence,
                                inspect_exact_stop_readonly,
                            )
                            guard = execution.get("resource_guard")
                            _need(isinstance(guard, Mapping)
                                  and guard.get("resource") == "android_ui"
                                  and isinstance(guard.get("claim_id"), str)
                                  and isinstance(guard.get("owner_id"), str),
                                  "PUBLISHER_DRY_RUN_RESOURCE_PROOF_MISSING")
                            live_safe = positive_synchronous_ui_quiescence(
                                guard, backend_job_id=exact_backend_id)
                            dead_owner = (
                                {} if live_safe else inspect_exact_stop_readonly(
                                    guard["claim_id"]))
                            _need(live_safe or dead_owner.get(
                                "fully_quiescent_positive") is True,
                                "PUBLISHER_DRY_RUN_QUIESCENCE_UNVERIFIED")
                        else:
                            _need(payload.get("publish_mode") == "COMMIT",
                                  "PUBLISHER_MODE_INVALID")
                            _need(inspect_public_commit_authority_readonly(
                                source,
                                capability_job_id=job_id,
                                backend_job_id=exact_backend_id,
                                request_sha256=identity["request_sha256"],
                                effective_policy_sha256=identity[
                                    "effective_policy_sha256"],
                                content_sha256=payload.get("content_sha256"),
                                caption_sha256=payload.get("caption_sha256")),
                                "PUBLISHER_PUBLIC_COMMIT_AUTHORITY_UNVERIFIED")
                            published = Path("/opt/y700/media/published")
                            receipt = _read_json(
                                published / publisher_id / "publish-result.json")
                            _need(receipt.get("status") == "PUBLISHED"
                                  and receipt.get("job_id") == publisher_id
                                  and receipt.get("capability_job_id") == job_id
                                  and receipt.get("backend_job_id")
                                      == exact_backend_id
                                  and receipt.get("request_sha256")
                                      == identity["request_sha256"]
                                  and receipt.get("content_sha256")
                                      == payload.get("content_sha256")
                                  and receipt.get("caption_sha256")
                                      == payload.get("caption_sha256")
                                  and receipt.get("visibility") == "PUBLIC"
                                  and isinstance(receipt.get("verification"), dict)
                                  and receipt["verification"].get("verified")
                                      is True,
                                  "PUBLISHER_PROFILE_PROOF_MISSING")
                    elif backend_type == "ui_workflow":
                        restored = _read_json(
                            source / "settings-restore-result.json")
                        _need(restored.get("capability_job_id") == job_id
                              and restored.get("backend_job_id")
                                  == exact_backend_id
                              and restored.get("request_sha256")
                                  == identity["request_sha256"]
                              and restored.get("settings_restore_result_version") == 1
                              and restored.get("restored_verified") is True
                              and restored.get("initial_mode")
                                  == restored.get("restored_mode"),
                              "SETTINGS_RESTORE_PROOF_MISSING")
                    elif backend_type == "observation":
                        observed = _read_json(
                            source / "observation-result.json")
                        _need(observed.get("capability_job_id") == job_id
                              and observed.get("backend_job_id")
                                  == exact_backend_id
                              and observed.get("request_sha256")
                                  == identity["request_sha256"]
                              and observed.get("authoritative_state_observed")
                                  is True
                              and observed.get("read_only") is True,
                              "OBSERVATION_VERIFIER_UNAVAILABLE")
                    elif backend_type == "root_exec":
                        root_receipt = _read_json(
                            source / "root-result.json")
                        _need(root_receipt.get("capability_job_id") == job_id
                              and root_receipt.get("backend_job_id")
                                  == exact_backend_id
                              and root_receipt.get("request_sha256")
                                  == identity["request_sha256"]
                              and root_receipt.get("command_exited_zero") is True
                              and root_receipt.get("root_epoch_advanced") is True,
                              "ROOT_VERIFIER_UNAVAILABLE")
                    else:
                        _need(False, "CAPABILITY_TERMINAL_VERIFIER_UNAVAILABLE")
                if outcome == "FAILED":
                    # Backend failure after a possible submit is NOT a
                    # terminal outcome merely because an adapter raised.
                    # Require independently recorded no-effect, no-mutator
                    # and exact stopped-backend proof. Any uncertainty
                    # stays active/RECONCILE_REQUIRED.
                    failed = _read_json(
                        source / "positive-failed-verifier.json")
                    _need(failed.get("capability_job_id") == job_id
                          and failed.get("backend_job_id")
                              == exact_backend_id
                          and failed.get("request_sha256")
                              == identity["request_sha256"]
                          and failed.get("backend_stopped_positive") is True
                          and failed.get("no_external_effect_positive") is True
                          and failed.get("subordinate_mutators_absent") is True
                          and failed.get("independent_verifier") is True,
                          "POSITIVE_FAILED_PROOF_MISSING")
                if outcome == "OUTCOME_NOT_ACHIEVED":
                    negative = _read_json(
                        source / "positive-negative-verifier.json")
                    _need(negative.get("capability_job_id") == job_id
                          and negative.get("backend_job_id")
                              == exact_backend_id
                          and negative.get("outcome_not_achieved") is True
                          and negative.get("verifier_independent") is True,
                          "POSITIVE_NEGATIVE_PROOF_MISSING")
            else:
                _need(outcome in {"EXPIRED", "CANCELLED", "FAILED"}
                      and backend_never_created_proven is True,
                      "PRE_SUBMIT_TERMINAL_PROOF_MISSING")
                _need(not (source / "effect-boundary.json").exists(),
                      "EFFECT_RECONCILE_REQUIRED")
                execution_path = source / "backend-execution.json"
                if execution_path.exists() or execution_path.is_symlink():
                    execution = _read_json(execution_path)
                    _need(execution.get("phase") == "NEVER_CREATED"
                          and execution.get("submission_possible") is False
                          and execution.get("attempt_serial") == 0,
                          "PRE_SUBMIT_TERMINAL_PROOF_MISSING")
                else:
                    _need(
                        not (source / "backend.json").exists()
                        and (
                            state.get("phase") == "ADMITTED"
                            or (
                                outcome == "CANCELLED"
                                and state.get("phase") == "CANCELLING"
                                and (source / "cancel.json").is_file()
                                and not (source / "cancel.json").is_symlink()
                            )
                        ),
                        "PRE_SUBMIT_TERMINAL_PROOF_MISSING",
                    )
            result = {
                "result_version": 1,
                "capability_job_id": job_id,
                "outcome": outcome,
                "terminal": True,
                "request_sha256": identity["request_sha256"],
                "exact_backend_job_id": exact_backend_id,
                "reason_code": reason_code[:128],
                "completed_at": _utc(),
                "external_effect_retry_allowed": False,
            }
            existing_result = source / "result.json"
            if existing_result.exists() or existing_result.is_symlink():
                # Crash between fsynced terminal result and archive rename:
                # never trust a partial/forged result as terminal authority.
                prior = _read_json(existing_result)
                _need(prior.get("result_version") == 1
                      and prior.get("outcome") == outcome
                      and prior.get("terminal") is True
                      and prior.get("capability_job_id") == job_id
                      and prior.get("request_sha256") == result["request_sha256"]
                      and prior.get("exact_backend_job_id") == exact_backend_id
                      and prior.get("external_effect_retry_allowed") is False
                      and isinstance(prior.get("completed_at"), str)
                      and bool(prior["completed_at"]),
                      "TERMINAL_RESULT_CONFLICT")
                result = prior
            else:
                _atomic_new(existing_result, result)
            # result.json is terminal truth: state.json remains last
            # non-terminal lifecycle and must not hide a durable result.
            _need(not destination.exists() and not destination.is_symlink(),
                  "TERMINAL_ARCHIVE_CONFLICT")
            os.replace(source, destination)
            _fsync_directory(source.parent)
            _fsync_directory(archive)
            return result

    def _locate_existing(self, job_id: str) -> Path:
        _need(bool(_JOB.fullmatch(job_id)), "CAPABILITY_JOB_ID_INVALID")
        # Status is never allowed to hide duplicate active/terminal
        # namespaces after a crash or manually corrupted archive.
        paths = [self.jobs / "active" / job_id] + [
            self.jobs / "archive" / category / job_id
            for category in sorted(set(_ARCHIVE_CLASS.values()))
        ]
        discovered: list[Path] = []
        for path in paths:
            _need(not path.is_symlink(), "CAPABILITY_PATH_UNTRUSTED")
            if path.exists():
                _need(path.is_dir(), "CAPABILITY_PATH_UNTRUSTED")
                discovered.append(path)
        _need(len(discovered) <= 1,
              "CAPABILITY_DUPLICATE_NAMESPACE_RECONCILE_REQUIRED")
        if not discovered:
            raise CapabilityStoreError("CAPABILITY_JOB_NOT_FOUND")
        return discovered[0]

    def observe(self, job_id: str) -> dict[str, Any]:
        """Read-only status, never repairs, restarts or reconciles a job."""
        _need(bool(_JOB.fullmatch(job_id)), "CAPABILITY_JOB_ID_INVALID")
        job = self._locate_existing(job_id)
        with _locked(job / "transition.lock", shared=True):
            ident = _read_json(job / "identity.json")
            _need(ident.get("capability_job_id") == job_id,
                  "CAPABILITY_IDENTITY_MISMATCH")
            terminal_file = job / "result.json"
            # A forged symlink or non-regular terminal marker must not
            # silently fall through to non-terminal state.json, potentially
            # permitting another backend or hiding completed business work.
            _need(not terminal_file.is_symlink(),
                  "TERMINAL_RESULT_UNTRUSTED")
            if terminal_file.exists():
                _need(terminal_file.is_file(),
                      "TERMINAL_RESULT_UNTRUSTED")
                result = _read_json(terminal_file)
                _need(result.get("capability_job_id") == job_id
                      and result.get("request_sha256")
                          == ident.get("request_sha256")
                      and result.get("outcome") in _TERMINAL
                      and result.get("terminal") is True,
                      "TERMINAL_RESULT_CORRUPT")
                return {
                    "capability_job_id": job_id,
                    "phase": result["outcome"],
                    "terminal": True,
                    "backend_submitted": None,
                    "reconcile_required": False,
                    "outcome_authority": "result.json",
                    "observation_only": True,
                    "execution_authorized": False,
                }
            try:
                state = _read_json(job / "state.json")
                _need(state.get("capability_job_id") == job_id
                      and state.get("request_sha256")
                          == ident.get("request_sha256")
                      and type(state.get("state_revision")) is int
                      and state["state_revision"] >= 0
                      and state.get("lifecycle_state") == state.get("phase"),
                      "STATE_STORE_CORRUPT")
            except CapabilityStoreError:
                return {
                    "capability_job_id": job_id,
                    "phase": "RECONCILE_REQUIRED",
                    "terminal": False,
                    "reason_code": "STATE_STORE_CORRUPT",
                    "next_action": "RECONCILE",
                    "observation_only": True,
                    "execution_authorized": False,
                }
            return {
                "capability_job_id": job_id,
                "phase": state["lifecycle_state"],
                "state_revision": state["state_revision"],
                "terminal": False,
                "backend_submitted": state.get("backend_submitted"),
                "effect_uncertain": state.get("effect_uncertain"),
                "mutation_uncertain": state.get("mutation_uncertain"),
                "reconcile_required": (
                    state["lifecycle_state"] == "RECONCILE_REQUIRED"
                ),
                "outcome_authority": "state.json",
                "observation_only": True,
                "execution_authorized": False,
            }
