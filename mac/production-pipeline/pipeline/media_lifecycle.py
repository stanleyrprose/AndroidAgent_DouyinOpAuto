"""Fail-closed Y700 media handoff: verify remote bytes before local cleanup."""
from __future__ import annotations

import hashlib
import fcntl
import contextlib
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


@contextlib.contextmanager
def _job_lock(job_dir: Path):
    lock = job_dir / "export" / ".media-cleanup.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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


def _remote_receipt(ssh_target: str, device_path: str, expected_sha: str) -> None:
    """Require a Y700-issued persisted receipt, not merely a remote file hash."""
    if not device_path.startswith("/opt/y700/media/ready/"):
        raise TransferSafetyError("Y700 media must be in the ready directory")
    receipt_path = str(Path(device_path).parent / "transfer-receipt.json")
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                        ssh_target, "cat -- " + shlex.quote(receipt_path)],
                       capture_output=True, text=True, timeout=45, check=False)
    if p.returncode:
        raise TransferSafetyError("Y700 persisted receipt unavailable")
    try:
        receipt = json.loads(p.stdout)
    except (ValueError, TypeError) as exc:
        raise TransferSafetyError("invalid Y700 persisted receipt") from exc
    if receipt.get("status") != "TRANSFER_VERIFIED":
        raise TransferSafetyError("Y700 receipt not verified")
    matches = [f for f in receipt.get("files", [])
               if isinstance(f, dict) and f.get("name") == Path(device_path).name
               and f.get("sha256") == expected_sha]
    if len(matches) != 1:
        raise TransferSafetyError("Y700 receipt does not match media")


def verify_and_clean(job_dir: Path, *, ssh_target: str, device_path: str,
                     artifact: str = "production/video.my.mp4") -> dict:
    """Only one declared deliverable; no cleanup until independently checked on Y700."""
    with _job_lock(job_dir.resolve(strict=True)):
        return _verify_and_clean_locked(job_dir, ssh_target=ssh_target, device_path=device_path, artifact=artifact)


def _verify_and_clean_locked(job_dir: Path, *, ssh_target: str, device_path: str, artifact: str) -> dict:
    job_dir = job_dir.resolve(strict=True)
    record = job_dir / "export" / "media-cleanup-receipt.json"
    existing = read_json(record) if record.exists() else None
    if existing:
        if existing.get("ssh_target") != ssh_target or existing.get("y700_path") != device_path or existing.get("artifact") != artifact:
            raise TransferSafetyError("receipt arguments differ")
        if existing.get("status") == "MAC_MEDIA_CLEANED":
            return existing
        if existing.get("status") != "TRANSFER_VERIFIED" or not isinstance(existing.get("snapshot"), list):
            raise TransferSafetyError("invalid or legacy receipt: manual recovery required")
        remote_sha = _remote_hash(ssh_target, device_path)
        if remote_sha != existing.get("artifact_sha256"):
            raise TransferSafetyError("Y700 SHA-256 mismatch during recovery")
        _remote_receipt(ssh_target, device_path, remote_sha)
        return _finish_cleanup(job_dir, record, existing)
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
    _remote_receipt(ssh_target, device_path, local_sha)
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
    # Freeze the exact deletion set in a durable journal before deleting any file.
    snapshot = [{"path": str(p), "size": p.stat().st_size, "sha256": digest(p)} for p in media]
    receipt = {
        "schema_version": 2, "status": "TRANSFER_VERIFIED",
        "job_id": job_dir.name, "ssh_target": ssh_target,
        "y700_path": device_path, "artifact": artifact,
        "artifact_sha256": local_sha, "remote_sha256": remote_sha,
        "media_count": len(snapshot), "deleted_count": 0, "snapshot": snapshot,
    }
    atomic_json(record, receipt)
    return _finish_cleanup(job_dir, record, receipt)


def _finish_cleanup(job_dir: Path, record: Path, receipt: dict) -> dict:
    # Resume only the previously frozen paths; never sweep newly created files.
    allowed_roots = [(job_dir / d).resolve() for d in ALLOWED_DIRS]
    allowed_roots.append((MEDIA_EXPORT / "exports" / job_dir.name).resolve())
    snapshot = receipt["snapshot"]
    for entry in snapshot:
        p = Path(entry["path"])
        if not p.is_absolute() or p.suffix.lower() not in MEDIA_SUFFIXES:
            raise TransferSafetyError("unsafe snapshot entry")
        if not any(p.is_relative_to(root) for root in allowed_roots):
            raise TransferSafetyError("snapshot path escapes allowed roots")
        if p.is_symlink():
            raise TransferSafetyError("symlink appeared during cleanup")
        if p.exists():
            if not p.is_file() or p.stat().st_size != entry["size"] or digest(p) != entry["sha256"]:
                raise TransferSafetyError("media changed: cleanup halted")
            p.unlink()
        # Missing snapshot file means a previous cleanup attempt removed it.
        receipt["deleted_count"] = snapshot.index(entry) + 1
        atomic_json(record, receipt)
    receipt["status"] = "MAC_MEDIA_CLEANED"
    atomic_json(record, receipt)
    return receipt


def pull_verify_clean(job_dir: Path, *, ssh_target: str, manifest_url: str,
                      remote_puller: str = "/opt/y700/deployments/media-cleanup-874f344/publisher/pull_job.py") -> dict:
    """Invoke Y700 pull, then independently verify persistence before cleanup."""
    from urllib.parse import urlparse
    u = urlparse(manifest_url)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise TransferSafetyError("manifest URL must be HTTPS")
    if not re.fullmatch(r"[A-Za-z0-9_.@-]+", ssh_target):
        raise TransferSafetyError("invalid SSH target")
    if not remote_puller.startswith("/opt/y700/"):
        raise TransferSafetyError("remote puller must be within Y700 app")
    job_dir = job_dir.resolve(strict=True)
    cmd = "python3 " + shlex.quote(remote_puller) + " " + shlex.quote(manifest_url)
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                        ssh_target, cmd], capture_output=True, text=True, timeout=600, check=False)
    if p.returncode:
        raise TransferSafetyError("Y700 pull failed; Mac media retained")
    try:
        result = json.loads(p.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError) as exc:
        raise TransferSafetyError("invalid Y700 pull result") from exc
    if result.get("status") != "READY" or result.get("job_id") != job_dir.name:
        raise TransferSafetyError("Y700 pull job mismatch")
    return verify_and_clean(job_dir, ssh_target=ssh_target,
                            device_path=f"/opt/y700/media/ready/{job_dir.name}/video.mp4")
