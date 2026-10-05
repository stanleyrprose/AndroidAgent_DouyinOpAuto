#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    from .job_contract import load_manifest, write_json_atomic
    from . import controller
except ImportError:
    # Preserve direct execution: python3 publisher/publish_job.py ...
    from job_contract import load_manifest, write_json_atomic
    import controller

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.tiktok import controller as generic_tiktok

READY=Path("/opt/y700/media/ready")
PUBLISHED=Path("/opt/y700/media/published")
FAILED=Path("/opt/y700/media/failed")
STATE=Path("/opt/y700/runtime/state/publisher.json")
PREFLIGHT=ROOT/"scripts"/"publish-preflight.sh"
STAGER=ROOT/"publisher"/"stage_job.py"
SECURE_UNLOCK=ROOT/"bridge"/"secure-unlock.sh"

class PublishError(RuntimeError):
    pass

def update(status,job_id,**extra):
    data={"status":status,"job_id":job_id,"timestamp":time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    data.update(extra)
    write_json_atomic(STATE,data)
    return data

def run(cmd,check=True,timeout=None):
    try:
        p=subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise PublishError(
            f"command timed out after {timeout}s: {' '.join(map(str,cmd))}"
        ) from exc
    if check and p.returncode!=0:
        raise PublishError(f"command failed rc={p.returncode}: {' '.join(map(str,cmd))}\n{p.stderr}")
    return p

def ensure_device_unlocked(job_id):
    update("UNLOCKING", job_id)
    try:
        return run(["bash", str(SECURE_UNLOCK)], timeout=45)
    except PublishError as exc:
        raise PublishError(f"secure unlock failed before preflight/staging: {exc}") from exc


def read_text(path):
    return path.read_text(encoding="utf-8").strip()

def load_metadata(job,manifest):
    name=manifest.get("metadata_file")
    if not name:
        return {}
    with open(job/name,encoding="utf-8") as f:
        data=json.load(f)
    if not isinstance(data,dict):
        raise PublishError("metadata must be an object")
    return data

def source_aweme_id(metadata,manifest=None):
    import re
    direct=str(metadata.get("source_aweme_id","")).strip()
    if direct:
        return direct
    for value in (
        metadata.get("source"),
        (manifest or {}).get("source") if isinstance(manifest,dict) else None,
    ):
        if not value:
            continue
        m=re.search(r"(?<!\d)(\d{18,20})(?!\d)",str(value))
        if m:
            return m.group(1)
    return ""

def find_published_duplicate(job_id,metadata,manifest=None):
    aweme_id=source_aweme_id(metadata,manifest)
    if not aweme_id or not PUBLISHED.exists():
        return None
    for other in PUBLISHED.iterdir():
        if not other.is_dir() or other.name==job_id:
            continue
        manifest_path=other/"manifest.json"
        if not manifest_path.exists():
            continue
        try:
            other_manifest=load_manifest(manifest_path)
            other_meta=load_metadata(other,other_manifest)
        except Exception:
            continue
        if source_aweme_id(other_meta,other_manifest)==aweme_id:
            return {"job_id":other.name,"source_aweme_id":aweme_id}
    return None

def verify_post_config():
    st=controller.current_state()
    if st["state"]!="POST_CONFIG":
        raise PublishError(f"expected POST_CONFIG, got {st}")
    return st

def store_generic_evidence(job, generic_result, filename="v05-ready-to-commit.png"):
    evidence=(generic_result or {}).get("evidence") or {}
    source=Path(str(evidence.get("source_path","")))
    if not source.is_file():
        raise PublishError(f"generic evidence missing: {source}")
    ev=job/"evidence"
    ev.mkdir(exist_ok=True)
    dest=ev/filename
    shutil.copy2(source,dest)
    return {
        "screenshot":str(Path("evidence")/dest.name),
        "workflow_job_id":generic_result.get("workflow_job_id"),
        "size":dest.stat().st_size,
    }

def capture_evidence(job,label):
    ev=job/"evidence"
    ev.mkdir(exist_ok=True)
    stamp=time.strftime("%Y%m%d-%H%M%S")
    shot=f"{label}-{stamp}.png"
    xml=f"{label}-{stamp}.xml"
    result={"screenshot":None,"ui":None}
    try:
        controller.androidctl("screenshot",shot)
        src=Path("/opt/y700/runtime")/shot
        if src.exists():
            shutil.copy2(src,ev/shot)
            result["screenshot"]=shot
    except Exception as e:
        result["screenshot_error"]=str(e)
    try:
        controller.androidctl("dump-ui",xml)
        src=Path("/opt/y700/runtime")/xml
        if src.exists():
            shutil.copy2(src,ev/xml)
            result["ui"]=xml
    except Exception as e:
        result["ui_error"]=str(e)
    return result

def safe_state():
    try:
        return controller.current_state()
    except Exception as e:
        visible=False
        try:
            visible=controller.tiktok_foreground()
        except Exception:
            pass
        return {"state":"UI_UNAVAILABLE","error":str(e),"tiktok_visible":visible}

def safe_ui_text():
    try:
        p=controller.dump_ui()
        return Path(p).read_text(encoding="utf-8",errors="ignore")
    except Exception:
        return ""

def commit_publish(job,job_id,timeout=75):
    before=capture_evidence(job,"before-commit")
    controller.tap_publish()
    deadline=time.monotonic()+timeout
    observations=[]
    failure_terms=("发布失败","上传失败","网络错误","重试")
    success_terms=("发布成功","已发布")
    last=None
    while time.monotonic()<deadline:
        time.sleep(2)
        last=safe_state()
        observations.append(last)
        if last["state"]=="KEYGUARD":
            controller.androidctl("unlock",check=False)
            continue

        ui_text=safe_ui_text()
        if any(term in ui_text for term in failure_terms):
            after=capture_evidence(job,"after-failure")
            raise PublishError(f"TikTok reported publish failure; evidence={after}")

        if any(term in ui_text for term in success_terms):
            after=capture_evidence(job,"after-success")
            return {
                "accepted":True,
                "confirmation":"success_text",
                "before":before,
                "after":after,
                "last_state":last,
                "observations":observations[-8:],
            }

        # TikTok may make uiautomator temporarily unavailable immediately after
        # the final publish tap. Do not convert that transient into FAILED.
        if last["state"]=="UI_UNAVAILABLE":
            continue

        if last["state"]!="POST_CONFIG" and last.get("tiktok_visible",False):
            time.sleep(5)
            stable=safe_state()
            observations.append(stable)
            if stable["state"] not in {"POST_CONFIG","UI_UNAVAILABLE"}:
                after=capture_evidence(job,"after-submit")
                return {
                    "accepted":True,
                    "confirmation":"stable_departure_from_post_config",
                    "before":before,
                    "after":after,
                    "last_state":stable,
                    "observations":observations[-8:],
                }

    after=capture_evidence(job,"after-timeout")
    raise PublishError(f"publish did not confirm within {timeout}s; last={last}; evidence={after}")

def verify_public_post(job,caption,timeout=60):
    try:
        verification=generic_tiktok.verify_public_post(
            caption,
            timeout_sec=timeout,
        )
    except generic_tiktok.TikTokCoreError as exc:
        raise PublishError(f"profile verification failed: {exc}") from exc
    stored=store_generic_evidence(
        job,
        verification,
        filename="profile-public-verified.png",
    )
    return {
        **verification,
        "evidence":stored,
    }


def verify_private_post(job,caption,timeout=60):
    """Historical PRIVATE reconciliation path retained for already-published jobs."""
    try:
        verification=generic_tiktok.verify_private_post(
            caption,
            timeout_sec=timeout,
        )
    except generic_tiktok.TikTokCoreError as exc:
        raise PublishError(f"profile verification failed: {exc}") from exc
    stored=store_generic_evidence(
        job,
        verification,
        filename="profile-private-verified.png",
    )
    return {
        **verification,
        "evidence":stored,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("job_id")
    ap.add_argument("--commit",action="store_true",
        help="required in addition to manifest publish_mode=COMMIT")
    args=ap.parse_args()

    job=READY/args.job_id
    manifest=load_manifest(job/"manifest.json")
    if manifest["job_id"]!=args.job_id:
        raise SystemExit("job_id mismatch")
    metadata=load_metadata(job,manifest)
    mode=manifest["publish_mode"]
    visibility=str(metadata.get("visibility",manifest.get("visibility","PUBLIC"))).upper()
    title=str(metadata.get("title",manifest.get("title",""))).strip()
    caption=read_text(job/manifest["caption_file"])

    duplicate=find_published_duplicate(args.job_id,metadata,manifest)
    if mode=="COMMIT" and duplicate:
        update("FAILED",args.job_id,
               reason="DUPLICATE_AWEME",
               duplicate_of=duplicate)
        raise PublishError(
            f"duplicate source_aweme_id already published: {duplicate['source_aweme_id']} "
            f"as {duplicate['job_id']}"
        )

    # Locked/sleeping Android can stall package/content-provider operations
    # before TikTok is launched. Wake/unlock before *any* Android-side
    # preflight or MediaStore staging; the TikTok controller still re-checks
    # keyguard state again at cold launch and after KEYGUARD_BLOCKING.
    ensure_device_unlocked(args.job_id)
    update("PREFLIGHT",args.job_id,publish_mode=mode,visibility=visibility)
    run([str(PREFLIGHT)])

    commit_entered=False
    try:
        update("STAGING",args.job_id)
        run([sys.executable,str(STAGER),args.job_id])

        # DRY_RUN remains frozen at POST_CONFIG and never clicks Publish.
        # COMMIT below uses the same generic preparation path, but crosses a
        # durable COMMITTING boundary immediately before its one irreversible click.
        if mode=="DRY_RUN":
            update("NAVIGATING",args.job_id,ui_engine="androidx-uiautomator-2.4")
            try:
                generic_result=generic_tiktok.prepare_dry_run(
                    caption,
                    title=title,
                    visibility=visibility,
                    album="Y700Agent",
                )
                evidence=store_generic_evidence(job,generic_result)
                update("READY_TO_COMMIT",args.job_id,
                       ui_engine=generic_result["engine"],
                       title=generic_result["title"],
                       caption_verified=generic_result["caption_verified"],
                       visibility=generic_result["visibility"],
                       ui_state=generic_result["ui_state"],
                       evidence=evidence,
                       workflow_job_id=generic_result["workflow_job_id"])
                print(json.dumps({
                    "job_id":args.job_id,
                    "status":"DRY_RUN_PASS",
                    "ui_engine":generic_result["engine"],
                    "evidence":evidence,
                },ensure_ascii=False))
                return
            finally:
                # Never leave an unattended DRY_RUN sitting on the final
                # publish screen.
                generic_tiktok.force_stop()

        if mode!="COMMIT":
            raise PublishError(f"unsupported publish_mode={mode}")
        if not args.commit:
            raise PublishError("manifest requests COMMIT but --commit was not supplied")

        if visibility!="PUBLIC":
            raise PublishError("generic COMMIT currently requires PUBLIC visibility")

        update("NAVIGATING",args.job_id,ui_engine="androidx-uiautomator-2.4")

        def before_irreversible():
            nonlocal commit_entered
            update("READY_TO_COMMIT",args.job_id,
                   ui_engine="androidx-uiautomator-2.4",
                   caption_verified=True,
                   visibility="PUBLIC")
            update("COMMITTING",args.job_id,
                   ui_engine="androidx-uiautomator-2.4",
                   visibility="PUBLIC")
            commit_entered=True

        generic_result=generic_tiktok.commit_public(
            caption,
            title=title,
            visibility=visibility,
            album="Y700Agent",
            before_irreversible=before_irreversible,
        )
        evidence=store_generic_evidence(job,generic_result)
        submission={
            "accepted":True,
            "confirmation":"generic_commit_dispatched",
            "engine":generic_result["engine"],
            "ready_workflow_job_id":generic_result["workflow_job_id"],
            "commit_preflight_workflow_job_id":generic_result["commit_preflight_workflow_job_id"],
            "commit_workflow_job_id":generic_result["commit_workflow_job_id"],
            "evidence":evidence,
        }

        verification=verify_public_post(job,caption)
        controller.restore_input_method()

        PUBLISHED.mkdir(parents=True,exist_ok=True)
        dest=PUBLISHED/args.job_id
        if dest.exists():
            shutil.rmtree(dest)
        job.replace(dest)
        write_json_atomic(dest/"publish-result.json",{
            "status":"PUBLISHED",
            "job_id":args.job_id,
            "visibility":visibility,
            "submission":submission,
            "verification":verification,
        })
        update("PUBLISHED",args.job_id,
               visibility=visibility,
               submission=submission,
               verification=verification)
        print(json.dumps({"job_id":args.job_id,"status":"PUBLISHED","path":str(dest)},ensure_ascii=False))
    except Exception as e:
        if mode=="DRY_RUN":
            generic_tiktok.force_stop()
        else:
            controller.restore_input_method()
        if mode=="COMMIT" and commit_entered:
            update("AMBIGUOUS_COMMIT_NEEDS_RECONCILE",args.job_id,
                   reason=str(e),
                   ui_engine="androidx-uiautomator-2.4",
                   retry_allowed=False)
        else:
            update("FAILED",args.job_id,reason=str(e))
        raise

if __name__=="__main__":
    main()
