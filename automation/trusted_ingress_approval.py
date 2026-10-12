"""Rev3.7 trusted one-URL ingress authorization -> exact approval witness.

Not an identity provider or new transport. An EXISTING authenticated
control plane must provide a root-owned, single-purpose, immutable
authorization record for ONE final Capability request. requested_by,
arbitrary workflow JSON or an externally passed approved=True boolean
cannot create this record or satisfy this reader.

The record originates OUTSIDE this module. It must be installed by the
separately authenticated first-party ChatGPT/Telegram/local controller
path under the privileged runtime root; this module only verifies it
and constructs an exact single-use approval. No approval is consumed or
UI effect attempted by reading it. No fallback to weak transport metadata.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from automation.capability_job_store import (
    AdmittedJob, CapabilityStoreError, _read_json, _sha, _need,
)

TRUSTED_INGRESS = Path("/opt/y700/runtime/trusted-ingress")
_ALLOWED = {
    "CHATGPT_AUTHORIZATION_CONTEXT",
    "TELEGRAM_ALLOWLIST_INGRESS",
    "TRUSTED_LOCAL_CONTROLLER",
}
_ORIGIN = "douyin-tiktok-publish"
_HEX = re.compile(r"^[0-9a-f]{64}$")
_URL = re.compile(r"^https://(?:www\.)?(?:douyin\.com|v\.douyin\.com)/[^\s]{5,1800}$")


class IngressAuthorizationUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise IngressAuthorizationUnavailable(code)


def _utc(value: Any) -> datetime:
    _require(isinstance(value, str), "INGRESS_AUTH_TIME_INVALID")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IngressAuthorizationUnavailable(
            "INGRESS_AUTH_TIME_INVALID") from exc
    _require(timestamp.tzinfo is not None,
             "INGRESS_AUTH_TIME_INVALID")
    return timestamp.astimezone(timezone.utc)


def _root_owned_record(path: Path) -> Mapping[str, Any]:
    """Bounded nofollow read, root owns both parent and the exact record."""
    parent = path.parent
    try:
        pd = parent.stat()
        _require(not parent.is_symlink()
                 and stat.S_ISDIR(pd.st_mode)
                 and pd.st_uid == 0
                 and stat.S_IMODE(pd.st_mode) == 0o700,
                 "INGRESS_AUTH_DIRECTORY_UNTRUSTED")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise IngressAuthorizationUnavailable(
            "INGRESS_AUTH_UNAVAILABLE") from exc
    try:
        before = os.fstat(fd)
        _require(stat.S_ISREG(before.st_mode)
                 and before.st_uid == 0
                 and stat.S_IMODE(before.st_mode) == 0o600
                 and 0 < before.st_size <= 8192,
                 "INGRESS_AUTH_FILE_UNTRUSTED")
        raw = bytearray()
        while len(raw) <= 8192:
            piece = os.read(fd, min(8193 - len(raw), 4096))
            if not piece:
                break
            raw.extend(piece)
        after = os.fstat(fd)
        _require(len(raw) == before.st_size
                 and (before.st_dev, before.st_ino, before.st_size,
                      before.st_mtime_ns)
                 == (after.st_dev, after.st_ino, after.st_size,
                     after.st_mtime_ns),
                 "INGRESS_AUTH_RECORD_RACED")
        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            value: dict[str, Any] = {}
            for key, entry in pairs:
                _require(key not in value,
                         "INGRESS_AUTH_DUPLICATE_KEY")
                value[key] = entry
            return value
        try:
            record = json.loads(raw, object_pairs_hook=unique)
        except (ValueError, UnicodeError) as exc:
            raise IngressAuthorizationUnavailable(
                "INGRESS_AUTH_MALFORMED") from exc
        _require(isinstance(record, dict),
                 "INGRESS_AUTH_MALFORMED")
        return record
    finally:
        os.close(fd)



def inspect_before_admission(
    *, request: Mapping[str, Any],
    effective_policy: Mapping[str, Any],
    current_clock_health: str,
) -> dict[str, Any]:
    """Validate exact existing ingress record BEFORE job admission.

    The control plane supplies the source record, never an approved=true
    JSON field. After admission, inspect_trusted_one_url_authorization()
    must verify the same record against the job's durable request and
    policy identities; neither stage silently grants a second attempt.
    """
    from automation.capability_job_store import _job_id, _sha
    _require(current_clock_health == "HEALTHY",
             "INGRESS_AUTH_CLOCK_SUSPECT")
    _require(isinstance(request, Mapping)
             and isinstance(effective_policy, Mapping),
             "INGRESS_AUTH_REQUEST_INVALID")
    submission_id = request.get("submission_id")
    _require(isinstance(submission_id, str),
             "INGRESS_AUTH_SUBMISSION_INVALID")
    try:
        expected_job = _job_id(submission_id)
        wanted_request_sha = _sha(request)
        wanted_policy_sha = _sha(effective_policy)
    except CapabilityStoreError as exc:
        raise IngressAuthorizationUnavailable(exc.code) from exc
    payload = request.get("payload")
    _require(request.get("capability") == "tiktok.publish"
             and request.get("version") == "1.0"
             and isinstance(payload, Mapping)
             and payload.get("visibility") == "PUBLIC"
             and payload.get("publish_mode") == "COMMIT",
             "INGRESS_AUTH_CAPABILITY_MISMATCH")
    key = hashlib.sha256(submission_id.encode()).hexdigest()
    proof = _root_owned_record(TRUSTED_INGRESS / (key + ".json"))
    principal = proof.get("approved_by")
    _require(proof.get("ingress_authorization_version") == 1
             and proof.get("authorization_type") == "EXPLICIT_ONE_URL"
             and proof.get("workflow") == _ORIGIN
             and proof.get("submission_id_sha256") == key
             and proof.get("capability_job_id") == expected_job
             and proof.get("request_sha256") == wanted_request_sha
             and proof.get("effective_policy_sha256") == wanted_policy_sha
             and proof.get("content_sha256")
                 == payload.get("content_sha256")
             and proof.get("caption_sha256")
                 == payload.get("caption_sha256")
             and proof.get("visibility") == "PUBLIC"
             and isinstance(principal, dict)
             and principal.get("principal_type") in _ALLOWED
             and isinstance(principal.get("principal_id"), str)
             and bool(principal["principal_id"])
             and proof.get("single_use") is True,
             "INGRESS_AUTH_IDENTITY_MISMATCH")
    url = proof.get("source_url")
    _require(isinstance(url, str) and _URL.fullmatch(url) is not None
             and payload.get("source_url") == url,
             "INGRESS_AUTH_SOURCE_MISMATCH")
    approved = _utc(proof.get("approved_at"))
    expires = _utc(proof.get("expires_at"))
    now = datetime.now(timezone.utc)
    _require(approved <= now < expires
             and (expires - approved).total_seconds() <= 7200
             and isinstance(proof.get("nonce"), str)
             and len(proof["nonce"]) >= 16,
             "INGRESS_AUTH_EXPIRED")
    return {
        "status": "EXACT_PRE_ADMISSION_AUTH_VERIFIED_READ_ONLY",
        "capability_job_id": expected_job,
        "request_sha256": wanted_request_sha,
        "effective_policy_sha256": wanted_policy_sha,
        "principal_type": principal["principal_type"],
        "authenticated_control_plane_fact": True,
        "effect_approval_consumed": False,
        "external_effect_attempts": 0,
    }

def inspect_trusted_one_url_authorization(
    job: AdmittedJob, *,
    current_clock_health: str,
) -> dict[str, Any]:
    """Read an existing exact trusted receipt; never create a grant."""
    _require(current_clock_health == "HEALTHY",
             "INGRESS_AUTH_CLOCK_SUSPECT")
    current_request = _read_json(job.path / "request.json")
    _require(_sha(current_request) == job.request_sha256,
             "IMMUTABLE_REQUEST_CHANGED")
    _require(current_request.get("capability") == "tiktok.publish"
             and current_request.get("version") == "1.0",
             "INGRESS_AUTH_CAPABILITY_MISMATCH")
    payload = current_request.get("payload")
    _require(isinstance(payload, dict)
             and payload.get("publish_mode") == "COMMIT"
             and payload.get("visibility") == "PUBLIC",
             "INGRESS_AUTH_NOT_PUBLIC_COMMIT")
    submission = current_request.get("submission_id")
    _require(isinstance(submission, str) and len(submission) <= 128,
             "INGRESS_AUTH_SUBMISSION_INVALID")
    key = hashlib.sha256(submission.encode("utf-8")).hexdigest()
    evidence = _root_owned_record(TRUSTED_INGRESS / (key + ".json"))
    principal = evidence.get("approved_by")
    _require(evidence.get("ingress_authorization_version") == 1
             and evidence.get("authorization_type") == "EXPLICIT_ONE_URL"
             and evidence.get("workflow") == _ORIGIN
             and evidence.get("submission_id_sha256") == key
             and evidence.get("capability_job_id") == job.job_id
             and evidence.get("request_sha256") == job.request_sha256
             and evidence.get("effective_policy_sha256")
                 == job.effective_policy_sha256
             and evidence.get("content_sha256")
                 == payload.get("content_sha256")
             and evidence.get("caption_sha256")
                 == payload.get("caption_sha256")
             and evidence.get("visibility") == "PUBLIC"
             and isinstance(principal, dict)
             and principal.get("principal_type") in _ALLOWED
             and isinstance(principal.get("principal_id"), str)
             and 0 < len(principal["principal_id"]) <= 160,
             "INGRESS_AUTH_IDENTITY_MISMATCH")
    url = evidence.get("source_url")
    _require(isinstance(url, str) and _URL.fullmatch(url) is not None
             and payload.get("source_url") == url,
             "INGRESS_AUTH_SOURCE_MISMATCH")
    _require(evidence.get("single_use") is True
             and isinstance(evidence.get("nonce"), str)
             and len(evidence["nonce"]) >= 16
             and isinstance(evidence.get("approval_id"), str)
             and 0 < len(evidence["approval_id"]) <= 160,
             "INGRESS_AUTH_NOT_SINGLE_USE")
    signed_at = _utc(evidence.get("approved_at"))
    expires = _utc(evidence.get("expires_at"))
    now = datetime.now(timezone.utc)
    _require(signed_at <= now < expires
             and (expires - signed_at).total_seconds() <= 7200,
             "INGRESS_AUTH_EXPIRED")
    return {
        "status": "EXACT_TRUSTED_INGRESS_AUTH_READ_ONLY",
        "approval_version": 1,
        "approved": True,
        "approval_id": evidence["approval_id"],
        "job_id": job.job_id,
        "capability": "tiktok.publish",
        "capability_version": "1.0",
        "request_sha256": job.request_sha256,
        "effective_policy_sha256": job.effective_policy_sha256,
        "content_sha256": evidence["content_sha256"],
        "caption_sha256": evidence["caption_sha256"],
        "visibility": "PUBLIC",
        "approved_by": dict(principal),
        "approved_at": signed_at.isoformat(),
        "expires_at": expires.isoformat(),
        "single_use": True,
        "nonce": evidence["nonce"],
        "approval_nonce": evidence["nonce"],
        "source_url_sha256": hashlib.sha256(url.encode()).hexdigest(),
        "ingress_record_source": "ROOT_OWNED_TRUSTED_CONTROL_PLANE",
        "effect_boundary_crossed": False,
        "external_effect_attempts": 0,
    }


def prepare_approval_for_recording(
    job: AdmittedJob, *, current_clock_health: str,
) -> dict[str, Any]:
    """Return validated immutable fields, not an activation authority.

    Existing effect_boundary.record_approval() may use these under its
    write-once transition lock after independently confirming the ingress
    reader is called inside an authenticated control-plane session.
    """
    return inspect_trusted_one_url_authorization(
        job, current_clock_health=current_clock_health)
