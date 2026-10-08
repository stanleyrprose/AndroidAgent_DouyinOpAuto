"""Best-effort reduction of verified Y700 work copies.

Only a completed job may invoke this after its durable success receipt exists.
Never prune ambiguous, failed, in-progress, or unverified publication jobs.
"""
from __future__ import annotations

import hashlib
import re
import shlex
from pathlib import Path


def prune_verified_video(job_dir: Path, video_name: str, gallery_path: str, root_exec) -> dict:
    """Remove a job MP4 only if Android gallery SHA-256 matches its source.

    Return a receipt; all errors fail closed without modifying publication truth.
    """
    try:
        if (not video_name or Path(video_name).name != video_name
                or video_name in {".", ".."} or not video_name.lower().endswith(".mp4")):
            return {"status": "SKIPPED", "reason": "invalid_source_name"}
        if not gallery_path.startswith("/sdcard/Movies/") or not gallery_path.endswith(".mp4"):
            return {"status": "SKIPPED", "reason": "invalid_gallery_path"}
        video = Path(job_dir) / video_name
        if video.is_symlink():
            return {"status": "SKIPPED", "reason": "source_symlink"}
        if not video.is_file():
            return {"status": "ALREADY_ABSENT"}
        source_sha = hashlib.sha256()
        with video.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                source_sha.update(block)
        result = root_exec(
            f"sha256sum {shlex.quote(gallery_path)}", check=False, timeout_ms=120000,
        )
        if result.returncode != 0:
            return {"status": "SKIPPED", "reason": "gallery_unreadable"}
        observed = (result.stdout or "").split()
        if not observed or not re.fullmatch(r"[a-fA-F0-9]{64}", observed[0]):
            return {"status": "SKIPPED", "reason": "gallery_hash_unavailable"}
        if observed[0].lower() != source_sha.hexdigest():
            return {"status": "SKIPPED", "reason": "gallery_checksum_mismatch"}
        video.unlink()
        return {"status": "PRUNED"}
    except Exception:
        # Disk pressure must never convert a successful TikTok COMMIT into failure.
        return {"status": "SKIPPED", "reason": "cleanup_error"}
