"""Rev3.7 immutable candidate integrity: offline signature + tree digests.

No automatic downloading, fetching, building, package installation or symlink
mutation. Candidate validation must use a root-owned pinned public key, a
detached signature over a stable digest record, exact safe relative paths,
root ownership/modes, and SHA256 for every signed critical file.

The pinned private signing key is NEVER stored on Y700. All verification
functions are read-only; all release activation remains independently CLOSED.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from typing import Any, Mapping

RELEASES = Path("/opt/y700/workspaces")
TRUST_ANCHOR = Path("/etc/y700/release-signing.pub.pem")
DIGESTS = "release-file-digests.json"
SIGNATURE = "release-file-digests.sig"
OPENSSL = "/usr/bin/openssl"
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_CRITICAL = (
    "release-manifest.json",
    "automation/release_lifecycle.py",
    "automation/gateway_coordinator.py",
    "automation/capability_job_store.py",
    "automation/resource_arbiter.py",
    "automation/state_integrity.py",
    "automation/ui_job.py",
    "bridge/bridge_client.py",
    "publisher/publish_job.py",
    "publisher/gateway_execution.py",
    "config/capabilities.json",
)


class ReleaseIntegrityUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise ReleaseIntegrityUnavailable(code)


def _regular(path: Path, *, owner: int = 0, maximum: int) -> bytes:
    _need(hasattr(os, "O_NOFOLLOW"),
          "RELEASE_INTEGRITY_NOFOLLOW_UNAVAILABLE")
    fd = -1
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        before = os.fstat(fd)
        _need(stat.S_ISREG(before.st_mode)
              and before.st_nlink == 1
              and before.st_uid == owner
              and (before.st_mode & 0o022) == 0
              and 0 < before.st_size <= maximum,
              "RELEASE_INTEGRITY_FILE_UNTRUSTED")
        raw = bytearray()
        while len(raw) <= maximum:
            part = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        after = os.fstat(fd)
        current = os.stat(path, follow_symlinks=False)
        _need(len(raw) == before.st_size
              and (before.st_dev, before.st_ino, before.st_size,
                   before.st_mtime_ns, before.st_ctime_ns)
              == (after.st_dev, after.st_ino, after.st_size,
                  after.st_mtime_ns, after.st_ctime_ns)
              == (current.st_dev, current.st_ino, current.st_size,
                  current.st_mtime_ns, current.st_ctime_ns),
              "RELEASE_INTEGRITY_READ_RACE")
        return bytes(raw)
    except OSError as exc:
        raise ReleaseIntegrityUnavailable(
            "RELEASE_INTEGRITY_FILE_UNAVAILABLE") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def _path(candidate: Path, name: str) -> Path:
    _need(isinstance(name, str) and 1 <= len(name) < 220,
          "RELEASE_INTEGRITY_PATH_INVALID")
    path = PurePosixPath(name)
    _need(not path.is_absolute() and bool(path.parts)
          and all(component not in {".", "..", ""} for component in path.parts)
          and "\\" not in name
          and name not in {DIGESTS, SIGNATURE},
          "RELEASE_INTEGRITY_PATH_INVALID")
    target = candidate
    for part in path.parts:
        target = target / part
        _need(not target.is_symlink(),
              "RELEASE_INTEGRITY_SYMLINK_FORBIDDEN")
    _need(target.parent.is_relative_to(candidate),
          "RELEASE_INTEGRITY_PATH_ESCAPE")
    return target


def verify_signed_candidate_readonly(
    candidate: Path, *,
    pinned_public_key: Path = TRUST_ANCHOR,
    maximum_file_bytes: int = 24 * 1024 * 1024,
) -> dict[str, Any]:
    """Return evidence only after positive signature and full digest match."""
    _need(candidate.parent == RELEASES
          and candidate.name.startswith("y700-agent-release-")
          and candidate.is_dir() and not candidate.is_symlink(),
          "RELEASE_PATH_UNTRUSTED")
    cstat = candidate.stat()
    _need(cstat.st_uid == 0 and (stat.S_IMODE(cstat.st_mode) & 0o022) == 0,
          "RELEASE_OWNER_OR_MODE_INVALID")
    _regular(pinned_public_key, maximum=8192)
    contents = _regular(candidate / DIGESTS, maximum=2 * 1024 * 1024)
    signature = _regular(candidate / SIGNATURE, maximum=4096)
    _need(len(signature) >= 32, "RELEASE_SIGNATURE_INVALID")
    # openssl CLI is an explicitly fixed offline binary; command arguments
    # cannot be supplied from request fields or the digest document.
    try:
        verify = subprocess.run(
            [OPENSSL, "dgst", "-sha256", "-verify",
             str(pinned_public_key), "-signature",
             str(candidate / SIGNATURE), str(candidate / DIGESTS)],
            capture_output=True, check=False, text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseIntegrityUnavailable(
            "RELEASE_SIGNATURE_VERIFIER_UNAVAILABLE") from exc
    _need(verify.returncode == 0
          and "verified ok" in verify.stdout.lower(),
          "RELEASE_SIGNATURE_INVALID")
    # The verifier opens paths separately; ensure bytes it could observe
    # have not changed from our initial no-follow reads.
    _need(_regular(candidate / DIGESTS, maximum=2 * 1024 * 1024) == contents
          and _regular(candidate / SIGNATURE, maximum=4096) == signature,
          "RELEASE_SIGNATURE_INPUT_CHANGED")
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, value in pairs:
            _need(key not in obj, "RELEASE_DIGEST_DUPLICATE_KEY")
            obj[key] = value
        return obj

    try:
        manifest = json.loads(contents, object_pairs_hook=unique_pairs)
    except (UnicodeError, ValueError) as exc:
        raise ReleaseIntegrityUnavailable(
            "RELEASE_DIGEST_CATALOG_INVALID") from exc
    _need(isinstance(manifest, dict)
          and manifest.get("release_files_version") == 1
          and isinstance(manifest.get("files"), dict),
          "RELEASE_DIGEST_CATALOG_INVALID")
    hashes: Mapping[str, Any] = manifest["files"]
    _need(set(_CRITICAL).issubset(hashes)
          and len(hashes) <= 8192,
          "RELEASE_DIGEST_SET_INCOMPLETE")
    # A signed subset cannot authorize unlisted executable source or
    # workflows. Compare the complete deployable candidate file inventory
    # (excluding only the digest index/signature themselves).
    actual_names: set[str] = set()
    for parent, dirs, filenames in os.walk(candidate, followlinks=False):
        rel_parent = Path(parent).relative_to(candidate)
        _need(len(actual_names) <= 8192,
              "RELEASE_INTEGRITY_TREE_OVERSIZE")
        for dirname in dirs:
            directory = Path(parent) / dirname
            metadata = directory.lstat()
            _need(stat.S_ISDIR(metadata.st_mode)
                  and metadata.st_uid == 0
                  and (stat.S_IMODE(metadata.st_mode) & 0o022) == 0,
                  "RELEASE_INTEGRITY_DIRECTORY_UNTRUSTED")
        for filename in filenames:
            item = Path(parent) / filename
            metadata = item.lstat()
            _need(stat.S_ISREG(metadata.st_mode)
                  and metadata.st_nlink == 1
                  and metadata.st_uid == 0
                  and (stat.S_IMODE(metadata.st_mode) & 0o022) == 0,
                  "RELEASE_INTEGRITY_FILE_UNTRUSTED")
            relative = (rel_parent / filename).as_posix()
            if relative not in {DIGESTS, SIGNATURE}:
                actual_names.add(relative)
    _need(len(actual_names) <= 8192
          and actual_names == set(hashes),
          "RELEASE_DIGEST_INVENTORY_MISMATCH")
    total = 0
    for name, wanted in hashes.items():
        _need(isinstance(wanted, str)
              and _SHA256.fullmatch(wanted) is not None,
              "RELEASE_DIGEST_CATALOG_INVALID")
        target = _path(candidate, name)
        raw = _regular(target, maximum=maximum_file_bytes)
        total += len(raw)
        _need(hashlib.sha256(raw).hexdigest() == wanted,
              "RELEASE_FILE_HASH_MISMATCH")
    return {
        "status": "CANDIDATE_SIGNED_INTEGRITY_VERIFIED_READ_ONLY",
        "candidate_release": candidate.name,
        "digest_file_count": len(hashes),
        "digest_total_bytes": total,
        "signature_verified": True,
        "all_listed_files_match": True,
        "release_switch_authorized": False,
    }
