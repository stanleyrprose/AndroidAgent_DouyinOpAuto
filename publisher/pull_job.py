#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import shutil
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
INTAKE=Path(__file__).resolve().parents[1]/"scripts"/"disk-guard.sh"

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def fetch(url,dest):
    req=urllib.request.Request(url,headers={"User-Agent":"Y700Agent/0.3"})
    with urllib.request.urlopen(req,timeout=60) as r, open(dest,"wb") as f:
        shutil.copyfileobj(r,f,1024*1024)

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
    fetch(args.manifest_url,manifest_tmp)

    try:
        manifest=load_manifest(manifest_tmp)
    except Exception as e:
        raise SystemExit(f"invalid manifest: {e}")

    job_id=manifest["job_id"]
    work=INCOMING/job_id
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
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
            fetch(urllib.parse.urljoin(base,name),part)
            actual=sha256(part)
            expected=manifest["sha256"][name].lower()
            if actual.lower()!=expected:
                raise ContractError(f"sha256 mismatch {name}: expected={expected} actual={actual}")
            part.replace(final)

        write_json_atomic(work/"state.json",{"status":"VALIDATED","files":files})
        dest=READY/job_id
        if dest.exists():
            shutil.rmtree(dest)
        work.replace(dest)
        write_json_atomic(dest/"state.json",{"status":"READY","files":files})
        print(json.dumps({"job_id":job_id,"status":"READY","path":str(dest)},ensure_ascii=False))
    except Exception as e:
        fail_dir(work,str(e))
        raise

if __name__=="__main__":
    main()
