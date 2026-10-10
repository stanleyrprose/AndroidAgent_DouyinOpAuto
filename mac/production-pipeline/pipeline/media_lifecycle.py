"""Fail-closed Y700 media handoff: verify remote bytes before local cleanup."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path

from .common import MEDIA_EXPORT, atomic_json, read_json

MEDIA_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".wav", ".mp3", ".m4a", ".aac", ".flac", ".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_DIRS = {"source", "analysis", "production", "export"}
STATES = {"TRANSFER_VERIFIED", "MAC_MEDIA_CLEANED"}


class TransferSafetyError(RuntimeError):
    pass


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _local_media(job_dir: Path) -> list[Path]:
    job_dir = job_dir.resolve(strict=True)
    candidates = []
    for directory in ALLOWED_DIRS:
        root = job_dir / directory
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_symlink():
                raise TransferSafetyError("symlink inside cleanup scope")
            if p.is_file() and p.suffix.lower() in MEDIA_SUFFIXES:
                if not p.resolve().is_relative_to(job_dir):
                    raise TransferSafetyError("media outside job directory")
                candidates.append(p)
    return sorted(candidates)


def _remote_hash(ssh_target: str, device_path: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.@-]+", ssh_target):
        raise TransferSafetyError("invalid SSH target")
    if not device_path.startswith("/") or any(c in device_path for c in "\\r\\n\\0"):
        raise TransferSafetyError("invalid absolute Y700 path")
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
           ssh_target, "sha256sum -- " + shlex.quote(device_path)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=False)
    if p.returncode:
        raise TransferSafetyError("Y700 remote hash verification failed")
    token = p.stdout.split(maxsplit=1)[0] if p.stdout.strip() else ""
    if not re.fullmatch(r"[0-9a-fA-F]{64}", token):
        raise TransferSafetyError("invalid remote SHA-256")
    return token.lower()


def verify_and_clean(job_dir: Path, *, ssh_target: str, device_path: str,
                     artifact: str = "production/video.my.mp4") -> dict:
    """Only one declared deliverable; no cleanup until independently checked on Y700."""
    job_dir = job_dir.resolve(strict=True)
    record = job_dir / "export" / "media-cleanup-receipt.json"
    if record.exists():
        existing = read_json(record)
        if existing.get("status") == "MAC_MEDIA_CLEANED":
            if existing.get("ssh_target") != ssh_target or existing.get("y700_path") != device_path or existing.get("artifact") != artifact:
                raise TransferSafetyError("idempotent receipt arguments differ")
            return existing
        raise TransferSafetyError("incomplete cleanup receipt: manual recovery required")
    artifact_path = (job_dir / artifact).resolve(strict=True)
    if not artifact_path.is_relative_to(job_dir) or artifact_path.is_symlink():
        raise TransferSafetyError("artifact path escapes job")
    if artifact_path.suffix.lower() not in MEDIA_SUFFIXES or not artifact_path.is_file():
        raise TransferSafetyError("artifact is not a media file")
    if artifact_path.relative_to(job_dir).parts[0] not in ALLOWED_DIRS:
        raise TransferSafetyError("artifact is outside media scope")
    local_sha = digest(artifact_path)
    remote_sha = _remote_hash(ssh_target, device_path)
    if remote_sha != local_sha:
        raise TransferSafetyError("Y700 SHA-256 mismatch: local media retained")
    media = _local_media(job_dir)
    # The export service keeps a separate copy; clean only this job's bundle.
    exports_root = (MEDIA_EXPORT / "exports").resolve()
    bundle = exports_root / job_dir.name
    if bundle.exists():
        if bundle.is_symlink() or not bundle.is_dir():
            raise TransferSafetyError("invalid export bundle")
        for item in bundle.rglob("*"):
            if item.is_symlink():
                raise TransferSafetyError("export bundle symlink")
            if item.is_file() and item.suffix.lower() in MEDIA_SUFFIXES:
                if not item.resolve().is_relative_to(bundle.resolve()):
                    raise TransferSafetyError("export media escaped bundle")
                media.append(item)
    media = sorted(media)
    # Freeze all media hashes before deletion; reject concurrent edits.
    snapshot = [(p, p.stat().st_size, digest(p)) for p in media]
    receipt = {
        "schema_version": 1, "status": "TRANSFER_VERIFIED",
        "job_id": job_dir.name, "ssh_target": ssh_target,
        "y700_path": device_path, "artifact": artifact,
        "artifact_sha256": local_sha, "remote_sha256": remote_sha,
        "media_count": len(snapshot), "deleted_count": 0,
    }
    atomic_json(record, receipt)
    for path, size, sha in snapshot:
        if not path.is_file() or path.is_symlink() or path.stat().st_size != size or digest(path) != sha:
            raise TransferSafetyError("media changed after verification: cleanup halted")
        path.unlink()
        receipt["deleted_count"] += 1
        atomic_json(record, receipt)
    receipt["status"] = "MAC_MEDIA_CLEANED"
    atomic_json(record, receipt)
    return receipt
