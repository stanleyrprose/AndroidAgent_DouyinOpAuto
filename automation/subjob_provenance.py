"""Rev3.7 top-backend/subordinate UI job provenance, development-only.

The existing TikTok Publisher remains the sole publication implementation.
Any future delegated UI subjob must be bound to one durable capability and
the CURRENT exact android_ui claim. Old-claim subjobs are never rebound.
This module writes binding evidence but never spawns a subjob or dispatches UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import stat
import re
from typing import Any, Mapping

from automation.capability_job_store import (
    AdmittedJob, CapabilityStoreError, _locked,
    _append, _read_json, _need, _utc,
)

_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_ROLES = frozenset({
    "prepare", "precommit", "commit", "verify", "reconcile", "other-v1",
})


@dataclass(frozen=True)
class SubjobProvenance:
    parent_capability_job_id: str
    top_backend_job_id: str
    subjob_id: str
    subjob_role: str
    claim_id: str | None
    owner_id: str | None
    mutation_expected: bool

    def to_record(self) -> dict[str, Any]:
        payload = {
            "parent_capability_job_id": self.parent_capability_job_id,
            "top_backend_job_id": self.top_backend_job_id,
            "subjob_id": self.subjob_id,
            "subjob_role": self.subjob_role,
            "mutation_expected": self.mutation_expected,
        }
        if self.mutation_expected:
            payload["resource_guard"] = {
                "resource": "android_ui",
                "claim_id": self.claim_id,
                "owner_id": self.owner_id,
            }
        return payload


def bind_subordinate_job(
    job: AdmittedJob, *,
    subjob_id: str,
    subjob_role: str,
    mutation_expected: bool,
    current_claim: Mapping[str, Any] | None,
    authoritative_claim_observer: Mapping[str, Any] | None,
) -> SubjobProvenance:
    """Persist SUBJOB_BOUND before the subordinate is created/submitted.

    The observer MUST be a trusted read from resource_arbiter SOT, never
    workflow payload. Callers cannot change resource claim session identity.
    """
    _need(bool(_ID.fullmatch(subjob_id)), "SUBORDINATE_BINDING_INVALID")
    _need(subjob_role in _ROLES, "SUBORDINATE_ROLE_UNSUPPORTED")
    _need(type(mutation_expected) is bool, "SUBORDINATE_BINDING_INVALID")
    with _locked(job.path / "transition.lock"):
        state = _read_json(job.path / "state.json")
        backend = _read_json(job.path / "backend.json")
        _need(backend.get("capability_job_id") == job.job_id
              and backend.get("request_sha256") == job.request_sha256,
              "PARENT_BACKEND_IDENTITY_INVALID")
        _need(not state.get("terminal")
              and not state.get("effect_uncertain")
              and not state.get("mutation_uncertain"),
              "RECONCILE_REQUIRED")
        backend_job_id = backend.get("backend_job_id")
        _need(isinstance(backend_job_id, str) and backend_job_id,
              "PARENT_BACKEND_IDENTITY_INVALID")
        claim_id = owner_id = None
        if mutation_expected:
            _need(isinstance(current_claim, Mapping)
                  and isinstance(authoritative_claim_observer, Mapping),
                  "SUBORDINATE_BINDING_INVALID")
            # Reopen the ORIGINAL canonical android_ui Claim at the actual
            # durable SUBJOB_BOUND linearization point. Two caller-provided
            # dictionaries matching each other are not ownership proof.
            from automation import resource_arbiter
            try:
                independently_observed = resource_arbiter.assert_guard(
                    dict(current_claim))
            except resource_arbiter.ResourceError as exc:
                raise CapabilityStoreError("STALE_RESOURCE_OWNERSHIP") from exc
            _need(independently_observed.get("owner_kind") == "CAPABILITY"
                  and independently_observed.get("capability_job_id")
                      == job.job_id
                  and independently_observed.get("backend_job_id")
                      == backend_job_id
                  and independently_observed.get("request_sha256")
                      == job.request_sha256
                  and independently_observed.get("claim_id")
                      == current_claim.get("claim_id")
                  and independently_observed.get("owner_id")
                      == current_claim.get("owner_id"),
                  "SUBORDINATE_RESOURCE_IDENTITY_MISMATCH")
            for key in ("claim_id", "owner_id"):
                _need(isinstance(current_claim.get(key), str)
                      and bool(current_claim[key])
                      and current_claim.get(key)
                      == authoritative_claim_observer.get(key)
                       == independently_observed.get(key),
                      "STALE_RESOURCE_OWNERSHIP")
            _need(current_claim.get("resource") == "android_ui"
                  and authoritative_claim_observer.get("resource") == "android_ui",
                  "SUBORDINATE_BINDING_INVALID")
            claim_id = current_claim["claim_id"]
            owner_id = current_claim["owner_id"]
        record = SubjobProvenance(
            parent_capability_job_id=job.job_id,
            top_backend_job_id=backend_job_id,
            subjob_id=subjob_id,
            subjob_role=subjob_role,
            claim_id=claim_id,
            owner_id=owner_id,
            mutation_expected=mutation_expected,
        )
        # The job-specific append log is the immutable provenance record.
        # Never silently change the exact resource_guard for a preexisting
        # subjob when a claim session has rotated.
        journal = job.path / "journal.jsonl"
        _need(hasattr(os, "O_NOFOLLOW"),
              "SUBJOB_JOURNAL_NOFOLLOW_UNAVAILABLE")
        try:
            fd = os.open(journal, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as exc:
            raise CapabilityStoreError("SUBJOB_JOURNAL_UNAVAILABLE") from exc
        try:
            before = os.fstat(fd)
            _need(stat.S_ISREG(before.st_mode)
                  and before.st_nlink == 1
                  and before.st_uid == os.geteuid()
                  and stat.S_IMODE(before.st_mode) == 0o600
                  and 0 <= before.st_size <= 4 * 1024 * 1024,
                  "SUBJOB_JOURNAL_UNTRUSTED")
            raw = bytearray()
            while len(raw) <= 4 * 1024 * 1024:
                part = os.read(fd, min(8192, 4 * 1024 * 1024 + 1 - len(raw)))
                if not part:
                    break
                raw.extend(part)
            after = os.fstat(fd)
            current = os.stat(journal, follow_symlinks=False)
            _need(len(raw) == before.st_size
                  and (before.st_dev, before.st_ino, before.st_size,
                       before.st_mtime_ns, before.st_ctime_ns)
                  == (after.st_dev, after.st_ino, after.st_size,
                      after.st_mtime_ns, after.st_ctime_ns)
                  == (current.st_dev, current.st_ino, current.st_size,
                      current.st_mtime_ns, current.st_ctime_ns),
                  "SUBJOB_JOURNAL_CHANGED_DURING_READ")
        finally:
            os.close(fd)
        try:
            lines = raw.decode("utf-8").splitlines()
        except UnicodeError as exc:
            raise CapabilityStoreError("SUBJOB_JOURNAL_CORRUPT") from exc
        for line in lines:
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError) as exc:
                raise CapabilityStoreError("SUBJOB_JOURNAL_CORRUPT") from exc
            _need(isinstance(row, dict), "SUBJOB_JOURNAL_CORRUPT")
            if row.get("event") == "SUBJOB_BOUND" and (
                    row.get("subjob_id") == subjob_id):
                _need(row.get("provenance") == record.to_record(),
                      "SUBORDINATE_STALE_CLAIM_REBIND_DENIED")
                return record
        _append(journal, {
            "event": "SUBJOB_BOUND",
            "timestamp": _utc(),
            "subjob_id": subjob_id,
            "provenance": record.to_record(),
        })
        return record


def check_subordinate_dispatch(
    provenance: SubjobProvenance,
    *,
    current_claim: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Check exact session equality; still does not authorize UI dispatch."""
    expected = provenance.to_record()
    if provenance.mutation_expected and (
        not isinstance(current_claim, Mapping)
        or expected["resource_guard"].get("claim_id") != current_claim.get("claim_id")
        or expected["resource_guard"].get("owner_id") != current_claim.get("owner_id")
        or current_claim.get("resource") != "android_ui"
    ):
        reason = "STALE_RESOURCE_OWNERSHIP"
    else:
        reason = "DRIVER_DISPATCH_NOT_ACTIVATED"
    return {
        "status": "BLOCKED",
        "reason_code": reason,
        "subjob_id": provenance.subjob_id,
        "resource_guard_exact_match": reason != "STALE_RESOURCE_OWNERSHIP",
        "ui_action_attempts": 0,
        "production_authorized": False,
    }
