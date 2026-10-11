#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from job_contract import ContractError, load_manifest, validate_manifest, write_json_atomic

MEDIA=Path("/opt/y700/media")
INCOMING=MEDIA/"incoming"
READY=MEDIA/"ready"
FAILED=MEDIA/"failed"
RUNTIME=Path("/opt/y700/runtime")
INTAKE=Path("/opt/y700/workspaces/y700-agent/scripts/disk-guard.sh")

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def fetch_manifest(url,dest):
    req=urllib.request.Request(url,headers={"User-Agent":"Y700Agent/0.3"})
    with urllib.request.urlopen(req,timeout=60) as response, open(dest,"wb") as out:
        shutil.copyfileobj(response,out,1024*1024)

def fetch(url,dest):
    # curl -C - negotiates HTTP Range; an interrupted .part remains reusable.
    subprocess.run(["curl", "-fL", "--retry", "3", "--connect-timeout", "15",
                    "--max-time", "600", "-C", "-", "-o", str(dest), url], check=True)

def persist_media(directory: Path, files: list[str]) -> None:
    """Flush validated media and directory entries before announcing READY."""
    for name in [*files, "manifest.json"]:
        with (directory / name).open("rb") as handle:
            os.fsync(handle.fileno())
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fail_dir(work,reason):
    if not work.exists():
        return
    write_json_atomic(work/"state.json",{"status":"FAILED","reason":reason})
    dest=FAILED/work.name
    if dest.exists():
        shutil.rmtree(dest)
    work.replace(dest)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("manifest_url")
    args=ap.parse_args()

    if os.system(f"{INTAKE} >/dev/null") != 0:
        raise SystemExit("media intake blocked by disk guard")

    INCOMING.mkdir(parents=True,exist_ok=True)
    READY.mkdir(parents=True,exist_ok=True)
    FAILED.mkdir(parents=True,exist_ok=True)

    manifest_tmp=RUNTIME/"tmp"/"pull-manifest.json"
    manifest_tmp.parent.mkdir(parents=True,exist_ok=True)
    fetch_manifest(args.manifest_url,manifest_tmp)

    try:
        manifest=load_manifest(manifest_tmp)
    except Exception as e:
        raise SystemExit(f"invalid manifest: {e}")

    job_id=manifest["job_id"]
    work=INCOMING/job_id
    if (READY/job_id).exists():
        raise SystemExit("job already present on Y700; refusing overwrite")
    # Refreshing the capability URL must not invalidate verified partial bytes.
    stable = {key: manifest[key] for key in ("job_id", "sha256", "video_file", "caption_file")}
    for key in ("title_file", "metadata_file"):
        if manifest.get(key):
            stable[key] = manifest[key]
    identity = hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()
    marker = work / ".manifest-sha256"
    if work.exists() and (work.is_symlink() or not work.is_dir()):
        raise SystemExit("unsafe incoming job directory")
    if work.exists() and (not marker.is_file() or marker.read_text() != identity):
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    marker.write_text(identity)
    shutil.copy2(manifest_tmp,work/"manifest.json")
    write_json_atomic(work/"state.json",{"status":"PULLING"})

    base=manifest.get("artifact_base_url") or urllib.parse.urljoin(args.manifest_url,".")
    files=[manifest["video_file"],manifest["caption_file"]]
    if manifest.get("title_file"):
        files.append(manifest["title_file"])
    if manifest.get("metadata_file"):
        files.append(manifest["metadata_file"])

    try:
        for name in files:
            part=work/(name+".part")
            final=work/name
            if part.is_symlink() or final.is_symlink():
                raise ContractError("unsafe media file")
            if final.exists() and sha256(final) == manifest["sha256"][name].lower():
                continue
            if final.exists():
                final.unlink()
            expected=manifest["sha256"][name].lower()
            if not part.exists() or sha256(part) != expected:
                artifact_url = urllib.parse.urljoin(base,name)
                if part.exists() and part.stat().st_size:
                    headers = subprocess.check_output(["curl", "-fsSI", "--connect-timeout", "15", artifact_url], timeout=30).decode("utf-8")
                    etags = [line.split(":", 1)[1].strip().strip('"').lower() for line in headers.splitlines() if line.lower().startswith("etag:")]
                    if not etags or etags[-1] != expected:
                        part.unlink()
                fetch(artifact_url,part)
            actual=sha256(part)
            if actual.lower()!=expected:
                part.unlink(missing_ok=True)
                raise ContractError(f"sha256 mismatch {name}: expected={expected} actual={actual}")
            part.replace(final)

        persist_media(work, files)
        write_json_atomic(work/"state.json",{"status":"VALIDATED","files":files})
        dest=READY/job_id
        if dest.exists():
            raise ContractError("ready job appeared during pull; refusing overwrite")
        work.replace(dest)
        write_json_atomic(dest/"state.json",{"status":"READY","files":files})
        # A verified receipt is published only after files and state reach stable storage.
        write_json_atomic(dest/"transfer-receipt.json", {
            "schema_version": 1, "status": "TRANSFER_VERIFIED",
            "job_id": job_id, "files": [
                {"name": name, "size": (dest / name).stat().st_size,
                 "sha256": sha256(dest / name)} for name in files
            ],
        })
        persist_media(dest, files)
        for name in ["state.json", "transfer-receipt.json"]:
            with (dest / name).open("rb") as handle:
                os.fsync(handle.fileno())
        dir_fd = os.open(dest, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        print(json.dumps({"job_id":job_id,"status":"READY","path":str(dest)},ensure_ascii=False))
    except Exception:
        # Keep incoming .part files for a retry with the same manifest.
        raise

if __name__=="__main__":
    main()
