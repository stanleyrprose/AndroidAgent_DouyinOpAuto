#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from job_contract import load_manifest, write_json_atomic

ROOT=Path(__file__).resolve().parents[1]
ROOT_EXEC=ROOT/"bridge"/"root-exec.sh"
READY=Path("/opt/y700/media/ready")
STATE=Path("/opt/y700/runtime/state/publisher.json")
HOST_READY="/data/local/y700-agent/media/ready"
ALBUM="/sdcard/Movies/Y700Agent"

def root_exec(command, check=True, timeout_ms=30000):
    env=os.environ.copy()
    env["Y700_BRIDGE_TIMEOUT_MS"]=str(int(timeout_ms))
    try:
        p=subprocess.run(
            [str(ROOT_EXEC),command],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=max(5.0, timeout_ms/1000 + 5.0),
        )
    except subprocess.TimeoutExpired as exc:
        if check:
            raise RuntimeError(f"root_exec local timeout after {timeout_ms}ms") from exc
        return subprocess.CompletedProcess([str(ROOT_EXEC),command],124,"","root_exec local timeout")
    if check and p.returncode!=0:
        raise RuntimeError(f"root_exec failed rc={p.returncode}: {p.stderr}")
    return p

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("job_id")
    args=ap.parse_args()
    job=READY/args.job_id
    manifest=load_manifest(job/"manifest.json")
    if manifest["job_id"]!=args.job_id:
        raise SystemExit("job_id mismatch")
    video=manifest["video_file"]
    src=f"{HOST_READY}/{args.job_id}/{video}"
    dst=f"{ALBUM}/{args.job_id}.mp4"

    write_json_atomic(STATE,{"status":"STAGING","job_id":args.job_id})
    root_exec(f"mkdir -p {ALBUM}; find {ALBUM} -maxdepth 1 -type f -delete; cp '{src}' '{dst}'; chmod 644 '{dst}'")
    root_exec(f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{dst} >/dev/null")
    found=False
    display_name=f"{args.job_id}.mp4"
    query=(
        "content query --uri content://media/external/video/media "
        "--projection _id:_display_name:relative_path "
        f"--where \"_display_name='{display_name}' AND relative_path='Movies/Y700Agent/'\""
    )
    for _ in range(30):
        q=root_exec(query,check=False,timeout_ms=5000)
        if display_name in (q.stdout or "") and "Movies/Y700Agent/" in (q.stdout or ""):
            found=True
            break
        time.sleep(1)
    if not found:
        write_json_atomic(STATE,{"status":"FAILED","job_id":args.job_id,"reason":"MediaStore scan timeout"})
        raise SystemExit("MediaStore scan timeout")

    write_json_atomic(STATE,{
        "status":"STAGED",
        "job_id":args.job_id,
        "album":"Y700Agent",
        "device_path":dst,
        "publish_mode":manifest["publish_mode"],
    })
    print(json.dumps({"job_id":args.job_id,"status":"STAGED","device_path":dst},ensure_ascii=False))

if __name__=="__main__":
    main()
