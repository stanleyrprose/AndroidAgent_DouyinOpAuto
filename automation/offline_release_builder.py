"""Rev3.7 offline Mac signing-side release digest builder (not executed).

Only a reviewed immutable candidate release directory may be signed. All
candidate files, including source and workflow configuration, are covered.
The private key is Mac-side and is NEVER copied to the portable Y700.
The Y700 verifies only with the pinned public key before atomic switch.

Signing is explicit, never called from Gateway, a background timer, Git push
or the migration hook. No signing command has been run in development.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
from typing import Any

RELEASE_DIGEST = "release-file-digests.json"
RELEASE_SIGNATURE = "release-file-digests.sig"
_OFFLINE_SIGNER_ACCEPTED = False


class ReleaseSigningUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise ReleaseSigningUnavailable(code)


def build_release_file_index_readonly(candidate: Path) -> dict[str, Any]:
    _need(isinstance(candidate, Path)
          and candidate.is_dir() and not candidate.is_symlink(),
          "RELEASE_CANDIDATE_UNAVAILABLE")
    files: dict[str, str] = {}
    seen = 0
    for parent, dirs, names in os.walk(candidate, followlinks=False):
        base = Path(parent)
        for name in dirs:
            _need(not (base / name).is_symlink(),
                  "RELEASE_SYMLINK_FORBIDDEN")
        for name in names:
            path = base / name
            relative = path.relative_to(candidate).as_posix()
            if relative in {RELEASE_DIGEST, RELEASE_SIGNATURE}:
                continue
            # Mirror the Y700 verifier's path and per-file limits BEFORE
            # signing, so Mac cannot sign an artifact that Y700 necessarily
            # rejects as too large or a noncanonical release entry.
            _need(0 < len(relative) < 220
                  and "\\" not in relative
                  and all(part not in {"", ".", ".."}
                          for part in Path(relative).parts),
                  "RELEASE_DIGEST_PATH_INVALID")
            _need(not path.is_symlink() and path.is_file(),
                  "RELEASE_SYMLINK_FORBIDDEN")
            metadata = path.stat()
            _need(stat.S_ISREG(metadata.st_mode)
                  and (stat.S_IMODE(metadata.st_mode) & 0o022) == 0
                  and 0 < metadata.st_size <= 24 * 1024 * 1024,
                  "RELEASE_FILE_UNTRUSTED_OR_TOO_LARGE")
            h = hashlib.sha256()
            try:
                with path.open("rb") as source:
                    for block in iter(
                            lambda: source.read(128 * 1024), b""):
                        h.update(block)
            except OSError as exc:
                raise ReleaseSigningUnavailable(
                    "RELEASE_FILE_UNREADABLE") from exc
            files[relative] = h.hexdigest()
            seen += 1
            _need(seen <= 8192,
                  "RELEASE_DIGEST_INVENTORY_TOO_LARGE")
    _need("release-manifest.json" in files
          and "config/capabilities.json" in files,
          "RELEASE_SIGNING_REQUIRED_FILES_MISSING")
    return {
        "release_files_version": 1,
        "files": dict(sorted(files.items())),
    }


def sign_candidate_offline(
    candidate: Path, *, private_key_on_mac: Path,
) -> dict[str, Any]:
    """Explicit approved Mac operation only; never triggered by Git/CI."""
    if not _OFFLINE_SIGNER_ACCEPTED:
        raise ReleaseSigningUnavailable(
            "OFFLINE_SIGNER_RELEASE_GATE_CLOSED")
    _need(platform.system() == "Darwin",
          "PRIVATE_SIGNING_KEY_NOT_ALLOWED_ON_Y700")
    _need(isinstance(private_key_on_mac, Path)
          and private_key_on_mac.is_file()
          and not private_key_on_mac.is_symlink()
          and stat.S_IMODE(private_key_on_mac.stat().st_mode) == 0o600,
          "SIGNING_KEY_UNTRUSTED")
    index = build_release_file_index_readonly(candidate)
    catalogue = candidate / RELEASE_DIGEST
    signature = candidate / RELEASE_SIGNATURE
    _need(not catalogue.exists() and not catalogue.is_symlink()
          and not signature.exists() and not signature.is_symlink(),
          "RELEASE_ALREADY_SIGNED")
    blob = (json.dumps(
        index, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ) + "\n").encode("utf-8")
    try:
        with catalogue.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
        result = subprocess.run(
            ["/usr/bin/openssl", "dgst", "-sha256",
             "-sign", str(private_key_on_mac),
             "-out", str(signature), str(catalogue)],
            capture_output=True, check=False, timeout=30,
        )
        _need(result.returncode == 0 and signature.is_file(),
              "RELEASE_SIGNING_FAILED")
        os.chmod(signature, 0o600)
        fd = os.open(candidate, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseSigningUnavailable(
            "RELEASE_SIGNING_UNAVAILABLE") from exc
    return {
        "status": "SIGNED_FOR_OFFLINE_STAGING",
        "file_count": len(index["files"]),
        "public_key_material_exported": False,
        "private_key_material_exported": False,
        "release_switched": False,
    }
