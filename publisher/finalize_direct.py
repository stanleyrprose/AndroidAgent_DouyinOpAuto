#!/usr/bin/env python3
"""Durably validate a Y700 generic-artifact bundle before issuing transfer receipt."""
from __future__ import annotations
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path("/opt/y700/runtime/direct-download")

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def finalize(job_id: str) -> None:
    if not re.fullmatch(r"dd-[0-9]{5,32}", job_id):
        raise ValueError("invalid direct job id")
    folder = ROOT / job_id
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("missing direct bundle")
    manifest_path = folder / "manifest.json"
    complete = folder / ".complete"
    if not complete.is_file() or complete.is_symlink():
        raise ValueError("bundle not complete")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("job_id") != job_id or manifest.get("kind") != "generic-artifact":
        raise ValueError("manifest mismatch")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1 or artifacts[0].get("name") != "original.mp4":
        raise ValueError("unexpected artifact list")
    item = artifacts[0]
    video = folder / "original.mp4"
    if video.is_symlink() or not video.is_file() or video.stat().st_size != item.get("size"):
        raise ValueError("artifact missing or size mismatch")
    sha = digest(video)
    if sha != item.get("sha256"):
        raise ValueError("artifact SHA-256 mismatch")
    for path in (video, manifest_path, complete):
        with path.open("rb") as f:
            os.fsync(f.fileno())
    receipt = folder / "transfer-receipt.json"
    temp = folder / ".transfer-receipt.json.tmp"
    record = {"schema_version": 1, "status": "TRANSFER_VERIFIED", "job_id": job_id,
              "files": [{"name": "original.mp4", "size": item["size"], "sha256": sha}]}
    with temp.open("w") as f:
        json.dump(record, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, receipt)
    fd = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

if __name__ == "__main__":
    finalize(sys.argv[1])
    print("TRANSFER_VERIFIED")
