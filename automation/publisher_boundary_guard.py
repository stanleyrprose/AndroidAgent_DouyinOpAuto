"""Existing TikTok Publisher capability-bound COMMIT preflight.

No new publisher; this is an optional migration guard consumed by the
existing publisher BEFORE it writes COMMITTING. Legacy jobs remain
compatible during the staged migration, but Gateway-bound jobs cannot
proceed unless the exact durable capability effect boundary already exists.
Production BUSINESS migration remains disabled pending final acceptance.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

_CAPABILITY_JOBS = Path("/opt/y700/capability-jobs/active")
_CAP_ID = re.compile(r"^cap-[a-f0-9]{48}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
# Set only by reviewed source migration after all gates pass.
_REQUIRE_GATEWAY_FOR_COMMIT = False
_GATEWAY_COMMIT_ACTIVATION_ENABLED = False


class PublisherBoundaryError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise PublisherBoundaryError(code)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        _need(key not in out, "GATEWAY_BOUNDARY_DUPLICATE_KEY")
        out[key] = value
    return out


def _strict_json(path: Path, max_bytes: int = 8192) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise PublisherBoundaryError("GATEWAY_BOUNDARY_UNAVAILABLE") from exc
    try:
        st = os.fstat(fd)
        _need(stat.S_ISREG(st.st_mode)
              and st.st_uid == 0
              and 0 < st.st_size <= max_bytes
              and stat.S_IMODE(st.st_mode) == 0o600,
              "GATEWAY_BOUNDARY_FILE_UNTRUSTED")
        with os.fdopen(os.dup(fd), "rb") as file:
            raw = file.read(max_bytes + 1)
        after = os.fstat(fd)
        _need(len(raw) == st.st_size
              and (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
              == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
              "GATEWAY_BOUNDARY_FILE_CHANGED")
        try:
            obj = json.loads(raw, object_pairs_hook=_unique_pairs)
        except (ValueError, UnicodeError) as exc:
            raise PublisherBoundaryError("GATEWAY_BOUNDARY_CORRUPT") from exc
        _need(isinstance(obj, dict), "GATEWAY_BOUNDARY_CORRUPT")
        return obj
    finally:
        os.close(fd)


def _hash_file(path: Path) -> str:
    """Hash one stable non-symlink regular inode, not a changing path."""
    fd = -1
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        before = os.fstat(fd)
        _need(stat.S_ISREG(before.st_mode)
              and (stat.S_IMODE(before.st_mode) & 0o022) == 0,
              "PUBLISHER_MEDIA_IDENTITY_UNAVAILABLE")
        digest = hashlib.sha256()
        consumed = 0
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            consumed += len(block)
        after = os.fstat(fd)
        _need(consumed == before.st_size
              and (before.st_dev, before.st_ino,
                   before.st_size, before.st_mtime_ns)
              == (after.st_dev, after.st_ino,
                  after.st_size, after.st_mtime_ns),
              "PUBLISHER_MEDIA_CHANGED_DURING_HASH")
        return digest.hexdigest()
    except OSError as exc:
        raise PublisherBoundaryError(
            "PUBLISHER_MEDIA_IDENTITY_UNAVAILABLE") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def read_gateway_binding(
    job: Path, manifest: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Absent migration binding remains legacy until source rollout gate."""
    path = job / "gateway-binding.json"
    if not path.exists() and not path.is_symlink():
        _need(not _REQUIRE_GATEWAY_FOR_COMMIT,
              "LEGACY_COMMIT_MIGRATION_BLOCKED")
        return None
    data = _strict_json(path)
    cap = data.get("capability_job_id")
    _need(isinstance(cap, str) and _CAP_ID.fullmatch(cap) is not None,
          "GATEWAY_CAPABILITY_BINDING_INVALID")
    _need(data.get("publisher_job_id") == manifest.get("job_id")
          and data.get("publish_mode") == manifest.get("publish_mode")
          and data.get("visibility") == "PUBLIC"
          and data.get("binding_version") == 1,
          "GATEWAY_CAPABILITY_BINDING_INVALID")
    for key in ("request_sha256", "effective_policy_sha256",
                "content_sha256", "caption_sha256", "manifest_sha256"):
        val = data.get(key)
        _need(isinstance(val, str) and _SHA.fullmatch(val) is not None,
              "GATEWAY_CAPABILITY_BINDING_INVALID")
    _need(_hash_file(job / "manifest.json")
          == data["manifest_sha256"],
          "PUBLISHER_MANIFEST_CHANGED")
    return data


def verify_before_publisher_committing(
    *, job: Path, manifest: Mapping[str, Any],
    gateway_binding: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """No click/input/commit; exact durable proof or blocked.

    This is invoked immediately before the existing publisher writes
    COMMITTING. It is not a replacement for its own resource and Android
    Driver action-time JIT checks.
    """
    if gateway_binding is not None:
        _need(_GATEWAY_COMMIT_ACTIVATION_ENABLED,
              "GATEWAY_COMMIT_RELEASE_GATE_CLOSED")
    if gateway_binding is None:
        _need(not _REQUIRE_GATEWAY_FOR_COMMIT,
              "LEGACY_COMMIT_MIGRATION_BLOCKED")
        return {"status": "LEGACY_MIGRATION_NOT_ENFORCED"}
    _need(manifest.get("publish_mode") == "COMMIT"
          and gateway_binding.get("publish_mode") == "COMMIT"
          and _hash_file(job / "manifest.json")
              == gateway_binding.get("manifest_sha256"),
          "PUBLISHER_IMMUTABLE_MODE_OR_MANIFEST_CHANGED")
    cap_id = gateway_binding["capability_job_id"]
    _need(bool(_CAP_ID.fullmatch(cap_id)), "CAPABILITY_JOB_ID_INVALID")
    cap_path = _CAPABILITY_JOBS / cap_id
    _need(cap_path.parent == _CAPABILITY_JOBS
          and not cap_path.is_symlink() and cap_path.is_dir(),
          "CAPABILITY_JOB_UNAVAILABLE")
    identity = _strict_json(cap_path / "identity.json")
    effective = _strict_json(cap_path / "effective_policy.json")
    approval = _strict_json(cap_path / "approval.json")
    boundary = _strict_json(cap_path / "effect-boundary.json")
    backend = _strict_json(cap_path / "backend.json")
    _need(identity.get("request_sha256")
          == gateway_binding["request_sha256"]
          and boundary.get("request_sha256")
              == gateway_binding["request_sha256"],
          "REQUEST_IDENTITY_MISMATCH")
    effective_hash = hashlib.sha256(json.dumps(
        effective, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    _need(effective_hash == gateway_binding["effective_policy_sha256"]
          and boundary.get("effective_policy_sha256") == effective_hash,
          "POLICY_IDENTITY_MISMATCH")
    approval_hash = hashlib.sha256(json.dumps(
        approval, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    _need(approval.get("approval_id") == boundary.get("approval_id")
          and approval_hash == boundary.get("approval_sha256"),
          "APPROVAL_NOT_CONSUMED")
    _need(boundary.get("phase") == "EFFECT_BOUNDARY_CROSSED"
          and boundary.get("capability_job_id") == cap_id
          and boundary.get("visibility") == "PUBLIC"
          and boundary.get("content_sha256")
              == gateway_binding["content_sha256"],
          "EFFECT_BOUNDARY_NOT_CROSSED")
    _need(backend.get("backend_type") == "publisher"
          and backend.get("backend_job_id") == boundary.get("backend_job_id"),
          "BACKEND_IDENTITY_MISMATCH")
    # The source Publisher already requires the manifest's video SHA256;
    # independently hash actual bytes at this irreversible boundary to
    # prevent stale/mutated material from reusing old approval.
    name = manifest.get("video_file")
    _need(isinstance(name, str) and Path(name).name == name,
          "PUBLISHER_MEDIA_IDENTITY_UNAVAILABLE")
    media = job / name
    manifest_sha = manifest.get("sha256", {}).get(name, "")
    actual_sha = _hash_file(media)
    _need(actual_sha == manifest_sha.lower()
          and actual_sha == gateway_binding["content_sha256"],
          "PUBLISHER_MEDIA_CHANGED")
    caption_name = manifest.get("caption_file")
    _need(isinstance(caption_name, str)
          and caption_name not in {".", "..", ""}
          and Path(caption_name).name == caption_name,
          "PUBLISHER_CAPTION_IDENTITY_UNAVAILABLE")
    caption_sha = _hash_file(job / caption_name)
    expected_caption_sha = manifest.get("sha256", {}).get(caption_name)
    _need(isinstance(expected_caption_sha, str)
          and caption_sha == expected_caption_sha.lower()
          and caption_sha == gateway_binding["caption_sha256"],
          "PUBLISHER_CAPTION_CHANGED")
    return {
        "status": "EXACT_GATEWAY_EFFECT_BOUNDARY_VERIFIED_READ_ONLY",
        "capability_job_id": cap_id,
        "production_dispatch_authorized": False,
        "external_effect_attempts": 0,
    }
