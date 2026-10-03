#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import secrets
import shutil
import time
from pathlib import Path

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--video",required=True)
    ap.add_argument("--caption-file")
    ap.add_argument("--caption")
    ap.add_argument("--title",default="")
    ap.add_argument("--job-id")
    ap.add_argument("--source",default="douyin")
    ap.add_argument("--language",default="my")
    ap.add_argument("--publish-mode",choices=["DRY_RUN","COMMIT"],default="DRY_RUN")
    ap.add_argument("--visibility",choices=["PRIVATE","PUBLIC","FRIENDS"],default="PRIVATE")
    ap.add_argument("--ttl-seconds",type=int,default=3600)
    ap.add_argument("--root",default="exports")
    ap.add_argument("--base-url",default=os.environ.get("Y700_MEDIA_BASE_URL"))
    args=ap.parse_args()
    if not args.base_url:
        raise SystemExit("set --base-url or Y700_MEDIA_BASE_URL")

    video=Path(args.video).expanduser().resolve()
    if not video.is_file():
        raise SystemExit(f"video not found: {video}")

    if args.caption_file:
        caption=Path(args.caption_file).expanduser().read_text(encoding="utf-8")
    elif args.caption is not None:
        caption=args.caption
    else:
        caption=""

    job_id=args.job_id or time.strftime("job-%Y%m%d-%H%M%S")
    if not all(c.isalnum() or c in "._-" for c in job_id):
        raise SystemExit("invalid job-id")

    root=Path(args.root).resolve()
    job=root/job_id
    if job.exists():
        raise SystemExit(f"job already exists: {job}")
    job.mkdir(parents=True)

    video_name="video.mp4"
    caption_name="caption.txt"
    metadata_name="metadata.json"

    shutil.copy2(video,job/video_name)
    (job/caption_name).write_text(caption,encoding="utf-8")
    (job/metadata_name).write_text(json.dumps({
        "title":args.title,
        "source":args.source,
        "language":args.language,
        "visibility":args.visibility,
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    cap=secrets.token_urlsafe(32)
    expires_at=int(time.time())+max(60,args.ttl_seconds)
    cap_path=job/".capability"
    cap_path.write_text(json.dumps({
        "token":cap,
        "expires_at":expires_at,
    })+"\n",encoding="utf-8")
    os.chmod(cap_path,0o600)

    files=[video_name,caption_name,metadata_name]
    sha={name:sha256(job/name) for name in files}
    base=args.base_url.rstrip("/") + f"/cap/{cap}/{job_id}/"
    manifest={
        "schema_version":1,
        "job_id":job_id,
        "source":args.source,
        "target":"tiktok",
        "language":args.language,
        "status":"READY",
        "video_file":video_name,
        "caption_file":caption_name,
        "metadata_file":metadata_name,
        "sha256":sha,
        "publish_mode":args.publish_mode,
        "visibility":args.visibility,
        "artifact_base_url":base,
    }
    (job/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "job_id":job_id,
        "manifest_url":base+"manifest.json",
        "path":str(job),
        "publish_mode":args.publish_mode,
        "visibility":args.visibility,
        "expires_at":expires_at,
    },ensure_ascii=False))

if __name__=="__main__":
    main()
