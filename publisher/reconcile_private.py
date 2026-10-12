#!/usr/bin/env python3
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from job_contract import load_manifest, write_json_atomic
import controller
from publish_job import load_metadata, read_text, update, verify_private_post

READY=Path("/opt/y700/media/ready")
PUBLISHED=Path("/opt/y700/media/published")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("job_id")
    args=ap.parse_args()

    published=PUBLISHED/args.job_id
    if published.is_dir():
        print(json.dumps({"status":"ALREADY_PUBLISHED","job_id":args.job_id},ensure_ascii=False))
        return

    job=READY/args.job_id
    if not job.is_dir():
        raise SystemExit(f"ready job not found: {args.job_id}")

    manifest=load_manifest(job/"manifest.json")
    metadata=load_metadata(job,manifest)
    visibility=str(metadata.get("visibility",manifest.get("visibility","PRIVATE"))).upper()
    if visibility!="PRIVATE":
        raise SystemExit("reconcile_private only supports PRIVATE jobs")
    caption=read_text(job/manifest["caption_file"])

    verification=verify_private_post(job,caption,timeout=75)

    PUBLISHED.mkdir(parents=True,exist_ok=True)
    dest=PUBLISHED/args.job_id
    if dest.exists():
        shutil.rmtree(dest)
    job.replace(dest)
    result={
        "status":"PUBLISHED",
        "job_id":args.job_id,
        "visibility":"PRIVATE",
        "verification":verification,
        "reconciled":True,
        "timestamp":time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    write_json_atomic(dest/"publish-result.json",result)
    update("PUBLISHED",args.job_id,
           visibility="PRIVATE",
           verification=verification,
           reconciled=True)
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":
    main()
