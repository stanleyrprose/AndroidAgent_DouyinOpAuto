"""Rev3.7 fresh runtime authority from root-owned local evidence.

This module is a SOURCE-DORMANT observer, not an authorization issuer.

Before a backend's first possible effect, the foreground Coordinator must
observe facts from the actual Y700 host, never copied from the request. A
root-owned, permission-restricted record is emitted by a separately
authenticated/accepted runtime-health + identity observer; this module only
reads and checks it against immutable Capability Job identity, policy, boot,
epoch and semantic revision. Missing, malformed or stale data fails closed.

No tests or production execution are performed by this implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from automation.authoritative_state_reader import (
    AuthorityUnavailable, observe_authoritative_state,
)
from automation.capability_job_store import (
    CAP_JOBS, CapabilityStoreError, _read_json, _need, _sha,
)

EVIDENCE_ROOT = Path("/opt/y700/runtime/capability-authority")
_JOB = re.compile(r"^cap-[0-9a-f]{48}$")
_BACKEND = re.compile(r"^cap-[0-9a-f]{48}--(?:observe|ui|root|publisher)-01$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_MAX_RECORD_BYTES = 16384
_MAX_AGE_MS = 750
_RUNTIME_FIELDS = frozenset({
    "adapter_present", "app_ui_contract_match", "runtime_compatible",
    "reconcile_required", "resource_busy", "dependencies_ready",
    "runtime_available", "runtime_degraded",
})
_IDENTITY_FIELDS = frozenset({
    "identity_authenticated", "effective_policy_allows",
    "current_approval_valid",
})
# Independent acceptance of the evidence producer has NOT occurred.
_EVIDENCE_PRODUCER_ACCEPTED = False


class RuntimeEvidenceUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _expect(predicate: bool, code: str) -> None:
    if not predicate:
        raise RuntimeEvidenceUnavailable(code)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        _expect(name not in result, "RUNTIME_AUTH_DUPLICATE_KEY")
        result[name] = value
    return result


def _root_mode(path: Path, *, directory: bool) -> None:
    try:
        st = path.lstat()
    except OSError as exc:
        raise RuntimeEvidenceUnavailable("RUNTIME_AUTH_PATH_UNAVAILABLE") from exc
    _expect(
        (stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode))
        and st.st_uid == 0
        and stat.S_IMODE(st.st_mode) == (0o700 if directory else 0o600),
        "RUNTIME_AUTH_PATH_UNTRUSTED",
    )


def _read_no_follow(path: Path) -> dict[str, Any]:
    _root_mode(EVIDENCE_ROOT, directory=True)
    _root_mode(path, directory=False)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise RuntimeEvidenceUnavailable("RUNTIME_AUTH_UNAVAILABLE") from exc
    try:
        before = os.fstat(fd)
        _expect(
            stat.S_ISREG(before.st_mode)
            and before.st_uid == 0
            and stat.S_IMODE(before.st_mode) == 0o600
            and 0 < before.st_size <= _MAX_RECORD_BYTES,
            "RUNTIME_AUTH_RECORD_UNTRUSTED",
        )
        raw = bytearray()
        while len(raw) <= _MAX_RECORD_BYTES:
            part = os.read(fd, min(4096, _MAX_RECORD_BYTES + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        after = os.fstat(fd)
        _expect(
            len(raw) == before.st_size
            and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            "RUNTIME_AUTH_RECORD_CHANGED",
        )
        try:
            document = json.loads(raw, object_pairs_hook=_unique)
        except (ValueError, UnicodeError) as exc:
            raise RuntimeEvidenceUnavailable("RUNTIME_AUTH_MALFORMED") from exc
        _expect(isinstance(document, dict), "RUNTIME_AUTH_MALFORMED")
        return document
    finally:
        os.close(fd)


def _typed_facts(obj: Any, keys: frozenset[str]) -> dict[str, bool]:
    _expect(isinstance(obj, dict)
            and set(obj) == keys
            and all(type(obj[key]) is bool for key in keys),
            "RUNTIME_AUTH_FACTS_INCOMPLETE")
    return dict(obj)


@dataclass(frozen=True)
class LocalRootRuntimeAuthority:
    """Strict read-only authority; never creates or refreshes evidence."""

    jobs_root: Path = CAP_JOBS

    def observe_fresh(
        self, capability_job_id: str, backend_job_id: str,
    ) -> dict[str, Any]:
        if not _EVIDENCE_PRODUCER_ACCEPTED:
            raise RuntimeEvidenceUnavailable("RUNTIME_EVIDENCE_PRODUCER_NOT_ACCEPTED")
        _expect(
            isinstance(capability_job_id, str)
            and _JOB.fullmatch(capability_job_id) is not None
            and isinstance(backend_job_id, str)
            and _BACKEND.fullmatch(backend_job_id) is not None
            and backend_job_id.startswith(capability_job_id + "--"),
            "RUNTIME_AUTH_IDENTITY_INVALID",
        )
        job_dir = self.jobs_root / "active" / capability_job_id
        _expect(job_dir.is_dir() and not job_dir.is_symlink(),
                "RUNTIME_AUTH_JOB_UNAVAILABLE")
        try:
            immutable = _read_json(job_dir / "identity.json")
            policy = _read_json(job_dir / "effective_policy.json")
            backend = _read_json(job_dir / "backend.json")
            state = _read_json(job_dir / "state.json")
        except CapabilityStoreError as exc:
            raise RuntimeEvidenceUnavailable(exc.code) from exc

        _expect(
            immutable.get("capability_job_id") == capability_job_id
            and backend.get("backend_job_id") == backend_job_id
            and backend.get("capability_job_id") == capability_job_id
            and backend.get("request_sha256") == immutable.get("request_sha256")
            and immutable.get("effective_policy_sha256") == _sha(policy)
            and state.get("capability_job_id") == capability_job_id
            and state.get("effective_policy_sha256") == _sha(policy)
            and state.get("terminal") is False
            and state.get("effect_uncertain") is False
            and state.get("mutation_uncertain") is False,
            "RUNTIME_AUTH_JOB_STATE_MISMATCH",
        )

        # SOT must be observed independently before and after the supplied
        # privileged evidence: same exact boot/epoch/revision/monotonic clock.
        before = observe_authoritative_state()
        path = EVIDENCE_ROOT / (capability_job_id + ".json")
        record = _read_no_follow(path)
        after = observe_authoritative_state()
        _expect(
            before.boot_id == after.boot_id
            and before.state_epoch == after.state_epoch
            and before.revision == after.revision,
            "RUNTIME_AUTH_SOT_DRIFT",
        )
        at = record.get("observed_boottime_ms")
        _expect(
            record.get("authority_evidence_version") == 1
            and record.get("capability_job_id") == capability_job_id
            and record.get("backend_job_id") == backend_job_id
            and record.get("request_sha256") == immutable.get("request_sha256")
            and record.get("effective_policy_sha256") == _sha(policy)
            and record.get("boot_id") == after.boot_id
            and record.get("state_epoch") == after.state_epoch
            and record.get("revision") == after.revision
            and record.get("producer") == "Y700_TRUSTED_RUNTIME_OBSERVER"
            and record.get("producer_contract_version") == 1
            and type(at) is int
            and at >= before.observed_boottime_ms - _MAX_AGE_MS
            and at <= after.observed_boottime_ms,
            "RUNTIME_AUTH_STALE_OR_MISMATCHED",
        )
        runtime = _typed_facts(record.get("runtime_facts"), _RUNTIME_FIELDS)
        identity = _typed_facts(record.get("identity_facts"), _IDENTITY_FIELDS)
        _expect(record.get("clock_health") == "HEALTHY",
                "RUNTIME_AUTH_CLOCK_SUSPECT")
        identity["clock_health"] = "HEALTHY"

        # Even an accurate read is an internal readiness fact, not a
        # capability permission token or D-G3 authorization.
        return {
            "boot_id": after.boot_id,
            "state_epoch": after.state_epoch,
            "revision": after.revision,
            "observed_boottime_ms": after.observed_boottime_ms,
            "capability_job_id": capability_job_id,
            "backend_job_id": backend_job_id,
            "effective_policy_sha256": _sha(policy),
            "identity_facts": identity,
            "runtime_facts": runtime,
            "execution_authorized": False,
            "dg3_status": "OPEN",
        }
