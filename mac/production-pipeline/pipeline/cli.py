from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .analyze import analyze
from .common import JOBS, atomic_json, ensure_runtime, extract_aweme_id, now_iso, read_json, url_key
from .douzy import Client, DouzyError
from .export import export as export_job
from .localize import save as save_localization
from .render import render
from .state import Job, find_duplicate, index_job, mark_published, set_workflow_intent


def _find_video(root: Path) -> Path:
    videos = sorted(root.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not videos:
        raise RuntimeError("download completed but no mp4 found")
    return videos[0]


def _canonicalize(job: Job, source_url: str, video: Path, result: dict, *, allow_duplicate: bool = False) -> Job:
    aweme_id = extract_aweme_id(str(video)) or extract_aweme_id(json.dumps(result, ensure_ascii=False))
    if not aweme_id:
        raise RuntimeError("unable to determine aweme_id")
    duplicate = find_duplicate(aweme_id=aweme_id)
    if duplicate and not allow_duplicate:
        job.write_state("DUPLICATE", aweme_id=aweme_id, duplicate_of=duplicate)
        raise RuntimeError(f"DUPLICATE_AWEME:{aweme_id}:{duplicate.get('job_id')}")
    desired = f"dy-{aweme_id}"
    if job.job_id != desired:
        target = JOBS / desired
        if target.exists():
            raise RuntimeError(f"canonical job already exists: {desired}")
        job.dir.rename(target)
        job = Job(desired)
    source = {
        "source_url": source_url,
        "aweme_id": aweme_id,
        "author_nickname": result.get("author_nickname"),
        "douzy_job_id": result.get("job_id"),
        "video_path": str(video if video.is_absolute() else video.resolve()),
    }
    # Directory rename invalidates old absolute path; rediscover inside canonical source dir.
    video2 = _find_video(job.dir / "source")
    source["video_path"] = str(video2.resolve())
    atomic_json(job.dir / "source" / "source.json", source)
    job.write_state("DOWNLOADED", aweme_id=aweme_id, douzy_job_id=result.get("job_id"))
    index_job(job, aweme_id=aweme_id, url_key=url_key(source_url))
    return job


def cmd_submit(args) -> int:
    ensure_runtime()
    key = url_key(args.url)
    dup = find_duplicate(url_key=key)
    if dup and not args.allow_duplicate:
        print(json.dumps({"status": "DUPLICATE", **dup}, ensure_ascii=False))
        return 10
    temp = f"src-{key}"
    if (JOBS / temp).exists():
        shutil.rmtree(JOBS / temp)
    job = Job.create(temp, args.url)
    try:
        client = Client()
        result = client.download(args.url, job.dir / "source")
        atomic_json(job.dir / "source" / "douzy-result.json", result)
        video = _find_video(job.dir / "source")
        job = _canonicalize(job, args.url, video, result, allow_duplicate=args.allow_duplicate)
        analysis = analyze(Path(read_json(job.dir / "source" / "source.json")["video_path"]), job.dir / "analysis")
        job.write_state("ANALYZED", route=analysis["route"])
        index_job(job, aweme_id=job.state().get("aweme_id"), url_key=key)
        print(json.dumps({
            "status": "ANALYZED",
            "job_id": job.job_id,
            "route": analysis["route"],
            "contact_sheet": str(job.dir / "analysis" / "frames" / "contact-sheet.jpg"),
            "transcript": str(job.dir / "analysis" / "transcript.zh.json"),
            "localization_request": str(job.dir / "analysis" / "localization_request.json"),
        }, ensure_ascii=False))
        return 0
    except DouzyError as e:
        state = "BLOCKED" if "BLOCKED_LOGIN" in str(e) else "FAILED"
        job.write_state(state, reason=str(e))
        print(json.dumps({"status": state, "job_id": job.job_id, "reason": str(e)}, ensure_ascii=False))
        return 20
    except RuntimeError as e:
        if str(e).startswith("DUPLICATE_AWEME:"):
            print(json.dumps({"status": "DUPLICATE", "job_id": job.job_id, "reason": str(e)}, ensure_ascii=False))
            return 10
        job.write_state("FAILED", reason=str(e))
        raise
    except Exception as e:
        job.write_state("FAILED", reason=str(e))
        raise


def get_job(job_id: str) -> Job:
    j = Job(job_id)
    if not j.dir.exists():
        raise RuntimeError(f"unknown job: {job_id}")
    return j


def refresh_index(job: Job) -> None:
    source = read_json(job.dir / "source" / "source.json", {}) or {}
    source_url = source.get("source_url")
    index_job(
        job,
        aweme_id=source.get("aweme_id"),
        url_key=url_key(source_url) if source_url else None,
    )


def cmd_localize(args) -> int:
    job = get_job(args.job_id)
    data = json.load(open(args.file, encoding="utf-8"))
    loc = save_localization(job.dir, data)
    job.write_state("LOCALIZED", content_type=loc["content_type"], visibility=loc["visibility"])
    refresh_index(job)
    print(json.dumps({"status": "LOCALIZED", "job_id": job.job_id, "content_type": loc["content_type"]}, ensure_ascii=False))
    return 0


def cmd_render(args) -> int:
    job = get_job(args.job_id)
    result = render(job.dir)
    job.write_state("RENDERED", video_sha256=result["sha256"]["video"])
    refresh_index(job)
    print(json.dumps({"status": "RENDERED", "job_id": job.job_id, **result}, ensure_ascii=False))
    return 0


def cmd_export(args) -> int:
    job = get_job(args.job_id)
    result = export_job(job.dir, ttl_seconds=args.ttl)
    job.write_state("EXPORTED", visibility=result["visibility"], expires_at=result["expires_at"])
    refresh_index(job)
    print(json.dumps({"status": "EXPORTED", "job_id": job.job_id, **result}, ensure_ascii=False))
    return 0


def cmd_mark_dryrun(args) -> int:
    job = get_job(args.job_id)
    job.write_state("AWAITING_APPROVAL", y700_job_id=args.y700_job_id or job.job_id)
    refresh_index(job)
    print(json.dumps({"status": "AWAITING_APPROVAL", "job_id": job.job_id}, ensure_ascii=False))
    return 0


def cmd_approve(args) -> int:
    job = get_job(args.job_id)
    if job.state().get("state") != "AWAITING_APPROVAL":
        raise RuntimeError(f"job is not awaiting approval: {job.state().get('state')}")
    job.write_state("APPROVED", approval_note=args.note or "explicit user approval")
    refresh_index(job)
    print(json.dumps({"status": "APPROVED", "job_id": job.job_id}, ensure_ascii=False))
    return 0


def cmd_set_intent(args) -> int:
    job = get_job(args.job_id)
    before = job.state().get("workflow_intent")
    out = set_workflow_intent(job, args.intent)
    refresh_index(job)
    print(json.dumps({
        "status": "WORKFLOW_INTENT_ALREADY_SET" if before else "WORKFLOW_INTENT_SET",
        "job_id": job.job_id,
        "workflow_intent": out.get("workflow_intent"),
        "state": out.get("state"),
    }, ensure_ascii=False))
    return 0


def cmd_mark_album_stored(args) -> int:
    job = get_job(args.job_id)
    job.write_state(
        "STORED_IN_ALBUM",
        album=args.album,
        device_path=args.device_path,
        media_store_verified=True,
        note_saved=True,
        note_app="com.zui.notes",
        workflow="album_store",
    )
    refresh_index(job)
    print(json.dumps({
        "status": "STORED_IN_ALBUM",
        "job_id": job.job_id,
        "album": args.album,
        "device_path": args.device_path,
        "note_saved": True,
        "note_app": "com.zui.notes",
    }, ensure_ascii=False))
    return 0


def cmd_finalize(args) -> int:
    job = get_job(args.job_id)
    source = read_json(job.dir / "source" / "source.json")
    state = "VERIFIED" if args.verified else "PUBLISHED"
    job.write_state(state, publication_evidence=args.evidence)
    mark_published(source["aweme_id"], job.job_id, verified=args.verified)
    print(json.dumps({"status": state, "job_id": job.job_id, "aweme_id": source["aweme_id"]}, ensure_ascii=False))
    return 0


def cmd_register_published(args) -> int:
    from .state import load_index, save_index
    idx=load_index()
    summary={
        "job_id":args.job_id,
        "state":"VERIFIED" if args.verified else "PUBLISHED",
        "updated_at":now_iso(),
    }
    idx.setdefault("aweme",{})[args.aweme_id]=summary
    if args.source_url:
        idx.setdefault("url",{})[url_key(args.source_url)]=summary
    save_index(idx)
    print(json.dumps({"status":summary["state"],"aweme_id":args.aweme_id,"job_id":args.job_id},ensure_ascii=False))
    return 0


def cmd_status(args) -> int:
    job = get_job(args.job_id)
    out = {"state": job.state()}
    for rel in [
        "source/source.json",
        "analysis/analysis.json",
        "localization/localization.json",
        "production/render-result.json",
        "export/export-result.json",
        "album-store-closure.json",
    ]:
        p = job.dir / rel
        if p.exists():
            out[rel] = read_json(p)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="douyin-myanmar")
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("submit")
    p.add_argument("url")
    p.add_argument("--allow-duplicate", action="store_true")
    p.set_defaults(func=cmd_submit)

    p = sp.add_parser("localize")
    p.add_argument("job_id")
    p.add_argument("file")
    p.set_defaults(func=cmd_localize)

    p = sp.add_parser("render")
    p.add_argument("job_id")
    p.set_defaults(func=cmd_render)

    p = sp.add_parser("export")
    p.add_argument("job_id")
    p.add_argument("--ttl", type=int, default=3600)
    p.set_defaults(func=cmd_export)

    p = sp.add_parser("mark-dryrun")
    p.add_argument("job_id")
    p.add_argument("--y700-job-id")
    p.set_defaults(func=cmd_mark_dryrun)

    p = sp.add_parser("approve")
    p.add_argument("job_id")
    p.add_argument("--note")
    p.set_defaults(func=cmd_approve)

    p = sp.add_parser("set-intent")
    p.add_argument("job_id")
    p.add_argument("intent", choices=["AUTO_PUBLISH", "STORE_ALBUM"])
    p.set_defaults(func=cmd_set_intent)

    p = sp.add_parser("mark-album-stored")
    p.add_argument("job_id")
    p.add_argument("--album", default="Y700Agent")
    p.add_argument("--device-path", required=True)
    p.set_defaults(func=cmd_mark_album_stored)

    p = sp.add_parser("finalize")
    p.add_argument("job_id")
    p.add_argument("--verified", action="store_true")
    p.add_argument("--evidence", default="")
    p.set_defaults(func=cmd_finalize)

    p = sp.add_parser("register-published")
    p.add_argument("aweme_id")
    p.add_argument("job_id")
    p.add_argument("--source-url")
    p.add_argument("--verified", action="store_true")
    p.set_defaults(func=cmd_register_published)

    p = sp.add_parser("status")
    p.add_argument("job_id")
    p.set_defaults(func=cmd_status)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
