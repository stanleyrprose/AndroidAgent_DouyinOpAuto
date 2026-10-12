#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
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
    ap.add_argument("--gateway-bound", action="store_true")
    args=ap.parse_args()
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", args.job_id) is None:
        raise SystemExit("PUBLISHER_JOB_ID_INVALID")
    job=READY/args.job_id
    if not job.is_dir() or job.is_symlink():
        raise SystemExit("PUBLISHER_READY_JOB_UNTRUSTED")
    manifest=load_manifest(job/"manifest.json")
    if manifest["job_id"]!=args.job_id:
        raise SystemExit("job_id mismatch")
    video=manifest["video_file"]
    src=f"{HOST_READY}/{args.job_id}/{video}"
    dst=f"{ALBUM}/{args.job_id}.mp4"

    write_json_atomic(STATE,{"status":"STAGING","job_id":args.job_id})
    if args.gateway_bound:
        # The exact Gateway Claim is acquired once by ForegroundCoordinator.
        # A subprocess cannot inherit Controller ContextVar; it independently
        # re-asserts the root-owned canonical owner before any MediaStore I/O.
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from automation.resource_arbiter import assert_guard, ResourceError
        from automation.publisher_boundary_guard import read_gateway_binding
        binding = read_gateway_binding(job, manifest)
        if not isinstance(binding, dict):
            raise SystemExit("GATEWAY_BINDING_REQUIRED")
        guard = {
            "resource": "android_ui",
            "claim_id": binding.get("claim_id"),
            "owner_id": binding.get("owner_id"),
        }
        try:
            owned = assert_guard(guard)
        except ResourceError as exc:
            raise SystemExit("GATEWAY_RESOURCE_STALE") from exc
        if not (
            owned.get("owner_kind") == "CAPABILITY"
            and owned.get("capability_job_id")
                == binding.get("capability_job_id")
            and owned.get("backend_job_id")
                == binding.get("backend_job_id")
            and owned.get("request_sha256")
                == binding.get("request_sha256")
        ):
            raise SystemExit("GATEWAY_RESOURCE_IDENTITY_MISMATCH")
        source_file = job / video
        if source_file.is_symlink() or not source_file.is_file():
            raise SystemExit("GATEWAY_SOURCE_VIDEO_UNAVAILABLE")
        digest = hashlib.sha256()
        with source_file.open("rb") as source_stream:
            for chunk in iter(
                    lambda: source_stream.read(1024 * 1024), b""):
                digest.update(chunk)
        expected = str(manifest.get("sha256", {}).get(video, "")).lower()
        if digest.hexdigest() != expected or (
                binding.get("content_sha256") != expected):
            raise SystemExit("GATEWAY_VIDEO_IDENTITY_CHANGED")
        # Never delete ANY existing Y700Agent video for a new Gateway job.
        # No-clobber rename of this job's unique .part file; any collision
        # or crash remnant blocks and requires explicit reconciliation.
        final = shlex.quote(dst)
        stage = shlex.quote(dst + ".rev37-part")
        album = shlex.quote(ALBUM)
        original = shlex.quote(src)
        stage_command = (
            "set -e; mkdir -p " + album + "; "
            + "test ! -e " + final + "; "
            + "test ! -e " + stage + "; "
            + "cp " + original + " " + stage + "; "
            + "chmod 644 " + stage + "; "
            + "mv -n " + stage + " " + final
        )
        root_exec(stage_command)
        actual = root_exec("sha256sum " + final).stdout.split()
        if not actual or actual[0].lower() != expected:
            raise SystemExit("GATEWAY_STAGED_VIDEO_HASH_MISMATCH")
        # Re-assert after Android file-system modification; an overwritten
        # Claim cannot be silently adopted by the staging subprocess.
        assert_guard(guard)
    else:
        # Unmodified Legacy behavior; source migration is separate.
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
    if args.gateway_bound:
        # The MediaStore poll may take 30+ seconds. Re-observe the same
        # canonical Owner before claiming a staged asset as safe to use.
        try:
            latest = assert_guard(guard)
        except ResourceError as exc:
            raise SystemExit("GATEWAY_RESOURCE_DRIFT_AFTER_MEDIASTORE") from exc
        if (latest.get("backend_job_id") != binding["backend_job_id"]
                or latest.get("capability_job_id")
                    != binding["capability_job_id"]
                or latest.get("request_sha256")
                    != binding["request_sha256"]):
            raise SystemExit("GATEWAY_RESOURCE_IDENTITY_DRIFT")

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
