#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

SAFE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")

def safe_name(value):
    return bool(value) and value not in {".", ".."} and all(c in SAFE_CHARS for c in value)

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def validate_manifest(data):
    if data.get("schema_version") != 1:
        raise ValueError("unsupported artifact manifest schema")
    job_id = data.get("job_id")
    if not safe_name(job_id):
        raise ValueError("unsafe manifest job_id")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("manifest artifacts must be a non-empty list")
    names = set()
    normalized = []
    for item in artifacts:
        if not isinstance(item, dict):
            raise ValueError("manifest artifact entry must be an object")
        name = item.get("name")
        digest = item.get("sha256")
        size = item.get("size")
        url = item.get("url")
        if not safe_name(name) or name in names:
            raise ValueError("unsafe or duplicate artifact name")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"invalid sha256 for {name}")
        int(digest, 16)
        if not isinstance(size, int) or size < 0:
            raise ValueError(f"invalid size for {name}")
        parsed = urlparse(str(url))
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"artifact URL must be https for {name}")
        names.add(name)
        normalized.append({"name": name, "sha256": digest.lower(), "size": size, "url": url})
    return job_id, normalized

def fetch_manifest(url, timeout):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("manifest URL must be https")
    req = urllib.request.Request(url, headers={"User-Agent": "Y700ArtifactPull/1"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def curl_download(url, destination, timeout):
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "curl", "-fL", "--retry", "5", "--retry-delay", "2",
        "--connect-timeout", "15", "--max-time", str(timeout),
        "--continue-at", "-", "--output", str(destination), url,
    ], check=True)

def main():
    ap = argparse.ArgumentParser(description="Pull and verify a capability-scoped artifact bundle.")
    ap.add_argument("--manifest-url", required=True)
    ap.add_argument("--target-root", required=True)
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    manifest = fetch_manifest(args.manifest_url, min(args.timeout, 60))
    job_id, artifacts = validate_manifest(manifest)
    root = Path(args.target_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    final_dir = root / job_id
    if final_dir.exists():
        raise RuntimeError("verified job already exists; refusing overwrite")

    # Stable staging survives interrupted transfers; never reuse bytes from a different manifest.
    staging = root / ("." + job_id + ".partial")
    identity = hashlib.sha256(json.dumps(artifacts, sort_keys=True).encode()).hexdigest()
    marker = staging / ".identity"
    if staging.exists() and (staging.is_symlink() or not staging.is_dir()):
        raise RuntimeError("unsafe partial directory")
    if staging.exists() and (not marker.is_file() or marker.read_text() != identity):
        shutil.rmtree(staging)
    staging.mkdir(exist_ok=True)
    marker.write_text(identity)
    try:
        for item in artifacts:
            partial = staging / (item["name"] + ".part")
            if partial.is_symlink():
                raise RuntimeError("unsafe partial file")
            if partial.exists() and partial.stat().st_size > item["size"]:
                partial.unlink()
            if not partial.exists() or partial.stat().st_size < item["size"]:
                curl_download(item["url"], partial, args.timeout)
            if partial.stat().st_size != item["size"] or sha256_file(partial) != item["sha256"]:
                # A mismatched partial must never be reused on the next attempt.
                partial.unlink(missing_ok=True)
                raise RuntimeError(f"size/sha256 mismatch for {item['name']}")
            os.replace(partial, staging / item["name"])
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (staging / ".complete").write_text("verified\n", encoding="utf-8")
        marker.unlink(missing_ok=True)
        os.replace(staging, final_dir)
        staging = None
        print(json.dumps({"status": "PASS", "job_id": job_id, "path": str(final_dir)}))
    finally:
        # Intentionally retain .part files after interruption for next attempt.
        pass

if __name__ == "__main__":
    main()
