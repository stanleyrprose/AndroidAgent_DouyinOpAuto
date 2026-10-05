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
    ap.add_argument("--video")
    ap.add_argument("--artifact",action="append",help="generic artifact as NAME=PATH; repeatable")
    ap.add_argument("--caption-file")
    ap.add_argument("--caption")
    ap.add_argument("--title",default="")
    ap.add_argument("--job-id")
    ap.add_argument("--source",default="douyin")
    ap.add_argument("--language",default="my")
    ap.add_argument("--publish-mode",choices=["DRY_RUN","COMMIT"],default="DRY_RUN")
    ap.add_argument("--visibility",choices=["PRIVATE","PUBLIC","FRIENDS"],default="PUBLIC")
    ap.add_argument("--ttl-seconds",type=int,default=3600)
    ap.add_argument("--root",default="exports")
    ap.add_argument("--base-url",default=os.environ.get("Y700_MEDIA_BASE_URL"))
    args=ap.parse_args()
    if not args.base_url:
        raise SystemExit("set --base-url or Y700_MEDIA_BASE_URL")

    generic=bool(args.artifact)
    if generic and args.video:
        raise SystemExit("use either --artifact or --video, not both")
    if not generic and not args.video:
        raise SystemExit("--video is required for media export")

    artifacts=[]
    if generic:
        seen=set()
        for spec in args.artifact:
            if "=" not in spec:
                raise SystemExit(f"invalid --artifact {spec!r}; expected NAME=PATH")
            name,raw=spec.split("=",1)
            if not name or name in {".",".."} or not all(c.isalnum() or c in "._-" for c in name):
                raise SystemExit(f"invalid artifact name: {name!r}")
            if name in seen:
                raise SystemExit(f"duplicate artifact name: {name}")
            source=Path(raw).expanduser().resolve()
            if not source.is_file():
                raise SystemExit(f"artifact not found: {source}")
            seen.add(name)
            artifacts.append((name,source))
        caption=""
    else:
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

    if generic:
        for name,source in artifacts:
            shutil.copy2(source,job/name)
    else:
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

    base=args.base_url.rstrip("/") + f"/cap/{cap}/{job_id}/"
    if generic:
        manifest={
            "schema_version":1,
            "job_id":job_id,
            "kind":"generic-artifact",
            "expires_at":expires_at,
            "artifacts":[{
                "name":name,
                "size":(job/name).stat().st_size,
                "sha256":sha256(job/name),
                "url":base+name,
            } for name,_ in artifacts],
        }
    else:
        files=[video_name,caption_name,metadata_name]
        sha={name:sha256(job/name) for name in files}
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
