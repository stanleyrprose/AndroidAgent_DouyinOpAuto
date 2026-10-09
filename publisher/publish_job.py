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
from automation import resource_arbiter, state_integrity

READY=Path("/opt/y700/media/ready")
PUBLISHED=Path("/opt/y700/media/published")
FAILED=Path("/opt/y700/media/failed")
STATE=Path("/opt/y700/runtime/state/publisher.json")
PREFLIGHT=ROOT/"scripts"/"publish-preflight.sh"
STAGER=ROOT/"publisher"/"stage_job.py"
SECURE_UNLOCK=ROOT/"bridge"/"secure-unlock.sh"
ANDROIDCTL=ROOT/"bridge"/"androidctl.sh"

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

def _normalize_initial_power_state(raw):
    text=str(raw or "")
    if "mWakefulness=Asleep" in text:
        return "ASLEEP"
    if "mWakefulness=Awake" in text:
        return "AWAKE"
    return "UNKNOWN"


def capture_initial_power_state(job, job_id):
    marker=Path(job)/"initial-power-state.json"
    if marker.is_file():
        try:
            with open(marker,encoding="utf-8") as f:
                existing=json.load(f)
            if existing.get("job_id")==job_id:
                return existing
        except Exception:
            pass

    raw=""
    error=None
    try:
        p=run([str(ANDROIDCTL),"screen-state"],check=False,timeout=15)
        raw=p.stdout.strip() if isinstance(getattr(p,"stdout",None),str) else ""
        rc=getattr(p,"returncode",0)
        rc=rc if isinstance(rc,int) else 0
        if rc!=0:
            error=f"screen-state rc={rc}"
    except PublishError as exc:
        error=str(exc)

    initial=_normalize_initial_power_state(raw)
    data={
        "schema_version":1,
        "job_id":job_id,
        "initial_power_state":initial,
        "restore_required":initial=="ASLEEP",
        "captured_at":time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "raw_screen_state":raw[:400],
    }
    if error:
        data["capture_error"]=error[:400]
    write_json_atomic(marker,data)
    try:
        marker.chmod(0o600)
    except OSError:
        pass
    return data


def ensure_device_unlocked(job_id):
    update("UNLOCKING", job_id)
    try:
        with resource_arbiter.acquire_android_ui(
            owner_kind="LEGACY",
            owner_id=f"legacy:publisher-unlock:{job_id}",
            backend_type="publisher-secure-unlock",
            backend_job_id=f"{job_id}--secure-unlock",
            request_sha256=resource_arbiter.request_identity(
                {"intent": "SECURE_UNLOCK", "job_id": job_id}
            ),
            timeout_sec=30.0,
        ):
            # secure-unlock.sh performs raw wake/swipe/keyevent UI mutations.
            # Invalidate pre-existing state tokens before the first such action
            # while holding the same canonical android_ui ownership as Core v2.
            state_integrity.bump_epoch(f"LEGACY_PUBLISHER_UNLOCK:{job_id}")
            return run(["bash", str(SECURE_UNLOCK)], timeout=45)
    except resource_arbiter.ResourceError as exc:
        raise PublishError(f"secure unlock resource unavailable: {exc}") from exc
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

    # Capture the caller-visible power state exactly once before any wake/unlock.
    # DRY_RUN and COMMIT share the same durable marker so COMMIT does not
    # overwrite an original ASLEEP state after DRY_RUN has already woken Y700.
    capture_initial_power_state(job,args.job_id)

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
        # Generic Core does not switch the system default IME.

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
            # Generic Core does not switch the system default IME.
            pass
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
