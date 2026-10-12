"""Rev3.7 pre-admission facts: immutable request + privileged facts.

No client, workflow, LLM, requested_by field or JSON flags can mint its
own identity/permission/runtime readiness evidence. The first-party
control-plane sensor must separately publish a root-owned immutable
record for the precise request/policy and current kernel boot/SOT epoch.

This file is an evidence CONSUMER. The independently authenticated
producer has not been accepted; the source-level producer gate is false.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from automation.authoritative_state_reader import observe_authoritative_state
from automation.capability_job_store import _sha
from automation.runtime_authority import RuntimeEvidenceUnavailable

ROOT = Path("/opt/y700/runtime/pre-admission-authority")
_SENSOR_ACCEPTED = False
_MAX_BYTES = 12288
_MAX_AGE_MS = 500
_PERMISSIONS = {
    "identity_authenticated", "effective_policy_allows",
    "current_approval_valid",
}
_READINESS = {
    "adapter_present", "app_ui_contract_match", "runtime_compatible",
    "reconcile_required", "resource_busy", "dependencies_ready",
    "runtime_available", "runtime_degraded",
}


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise RuntimeEvidenceUnavailable(code)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for k, v in pairs:
        _require(k not in data, "PRE_ADMISSION_EVIDENCE_DUPLICATE_KEY")
        data[k] = v
    return data


def _record(path: Path) -> dict[str, Any]:
    try:
        parent = ROOT.lstat()
        _require(stat.S_ISDIR(parent.st_mode)
                 and parent.st_uid == 0
                 and stat.S_IMODE(parent.st_mode) == 0o700,
                 "PRE_ADMISSION_ROOT_UNTRUSTED")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise RuntimeEvidenceUnavailable(
            "PRE_ADMISSION_EVIDENCE_UNAVAILABLE") from exc
    try:
        meta = os.fstat(fd)
        _require(stat.S_ISREG(meta.st_mode)
                 and meta.st_uid == 0
                 and stat.S_IMODE(meta.st_mode) == 0o600
                 and 0 < meta.st_size <= _MAX_BYTES,
                 "PRE_ADMISSION_EVIDENCE_UNTRUSTED")
        data = bytearray()
        while len(data) <= _MAX_BYTES:
            chunk = os.read(fd, min(4096, _MAX_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        newer = os.fstat(fd)
        _require(
            len(data) == meta.st_size
            and (meta.st_dev, meta.st_ino, meta.st_size, meta.st_mtime_ns)
                == (newer.st_dev, newer.st_ino, newer.st_size,
                    newer.st_mtime_ns),
            "PRE_ADMISSION_EVIDENCE_RACED")
        try:
            result = json.loads(data, object_pairs_hook=_unique)
        except (UnicodeError, ValueError) as exc:
            raise RuntimeEvidenceUnavailable(
                "PRE_ADMISSION_EVIDENCE_MALFORMED") from exc
        _require(isinstance(result, dict),
                 "PRE_ADMISSION_EVIDENCE_MALFORMED")
        return result
    finally:
        os.close(fd)


def _facts(value: Any, fields: set[str]) -> dict[str, bool]:
    _require(isinstance(value, dict) and set(value) == fields
             and all(type(value[k]) is bool for k in fields),
             "PRE_ADMISSION_FACTS_UNAVAILABLE")
    return dict(value)


def read_trusted_pre_admission(
    *, immutable_request: Mapping[str, Any],
    effective_policy: Mapping[str, Any],
) -> dict[str, Any]:
    if not _SENSOR_ACCEPTED:
        raise RuntimeEvidenceUnavailable(
            "PRE_ADMISSION_SENSOR_NOT_ACCEPTED")
    _require(isinstance(immutable_request, Mapping)
             and isinstance(effective_policy, Mapping),
             "PRE_ADMISSION_CONTRACT_INVALID")
    request_hash = _sha(immutable_request)
    policy_hash = _sha(effective_policy)
    before = observe_authoritative_state()
    record = _record(ROOT / (request_hash + ".json"))
    after = observe_authoritative_state()
    observed = record.get("observed_boottime_ms")
    _require(
        record.get("evidence_version") == 1
        and record.get("producer") == "Y700_TRUSTED_PRE_ADMISSION_OBSERVER"
        and record.get("request_sha256") == request_hash
        and record.get("effective_policy_sha256") == policy_hash
        and record.get("capability")
            == immutable_request.get("capability")
        and record.get("boot_id") == before.boot_id == after.boot_id
        and record.get("state_epoch")
            == before.state_epoch == after.state_epoch
        and record.get("revision") == before.revision == after.revision
        and type(observed) is int
        and before.observed_boottime_ms - _MAX_AGE_MS <= observed
        <= after.observed_boottime_ms
        and record.get("clock_health") == "HEALTHY",
        "PRE_ADMISSION_IDENTITY_STALE",
    )
    readiness = _facts(record.get("runtime_facts"), _READINESS)
    permission = _facts(record.get("identity_facts"), _PERMISSIONS)
    permission["clock_health"] = "HEALTHY"
    return {
        "runtime_facts": readiness,
        "identity_facts": permission,
        "request_sha256": request_hash,
        "effective_policy_sha256": policy_hash,
        "observed_boottime_ms": after.observed_boottime_ms,
        "execution_authorized": False,
    }
