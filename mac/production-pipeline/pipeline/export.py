from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .common import MEDIA_EXPORT, atomic_json, run


def export(job_dir: Path, *, ttl_seconds: int = 3600) -> dict:
    source = json.load(open(job_dir / "source" / "source.json", encoding="utf-8"))
    loc = json.load(open(job_dir / "localization" / "localization.json", encoding="utf-8"))
    prod = job_dir / "production"
    export_dir = job_dir / "export"
    job_id = job_dir.name

    tool = MEDIA_EXPORT / "export_job.py"
    if not tool.exists():
        raise RuntimeError(f"media-export missing: {tool}")

    p = run([
        "python3", str(tool),
        "--video", str(prod / "video.my.mp4"),
        "--caption-file", str(prod / "caption.my.txt"),
        "--title", loc["title_my"] or f"Douyin {source['aweme_id']}",
        "--source", f"douyin:{source['aweme_id']}",
        "--language", "my",
        "--job-id", job_id,
        "--publish-mode", "DRY_RUN",
        "--visibility", loc["visibility"],
        "--ttl-seconds", str(ttl_seconds),
        "--root", str(MEDIA_EXPORT / "exports"),
    ])
    info = json.loads(p.stdout.strip().splitlines()[-1])
    # Capability URL is stored locally but is not emitted into normal logs.
    atomic_json(export_dir / "handoff.json", info)
    safe = {
        "job_id": info["job_id"],
        "publish_mode": info["publish_mode"],
        "visibility": info["visibility"],
        "expires_at": info["expires_at"],
        "manifest_url_file": "export/handoff.json",
    }
    atomic_json(export_dir / "export-result.json", safe)
    return safe
