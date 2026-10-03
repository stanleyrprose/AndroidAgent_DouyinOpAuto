#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from job_contract import load_manifest, write_json_atomic
import controller

ROOT=Path(__file__).resolve().parents[1]
READY=Path("/opt/y700/media/ready")
PUBLISHED=Path("/opt/y700/media/published")
FAILED=Path("/opt/y700/media/failed")
STATE=Path("/opt/y700/runtime/state/publisher.json")
PREFLIGHT=ROOT/"scripts"/"publish-preflight.sh"
STAGER=ROOT/"publisher"/"stage_job.py"

class PublishError(RuntimeError):
    pass

def update(status,job_id,**extra):
    data={"status":status,"job_id":job_id,"timestamp":time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    data.update(extra)
    write_json_atomic(STATE,data)
    return data

def run(cmd,check=True):
    p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if check and p.returncode!=0:
        raise PublishError(f"command failed rc={p.returncode}: {' '.join(map(str,cmd))}\n{p.stderr}")
    return p

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

def verify_private_post(job,caption,timeout=60):
    controller.androidctl("wake",check=False)
    controller.androidctl("unlock",check=False)
    deadline=time.monotonic()+timeout

    # Reach Profile. If already there, the private-video tab will be visible.
    while time.monotonic()<deadline:
        try:
            xml=controller.dump_ui()
            _,private_attrs=controller.find_node(xml,desc="私密视频",clickable=True)
            if private_attrs:
                break
            c,_=controller.find_node(xml,rid="o76",clickable=True)
            if c:
                controller.androidctl("tap",str(c[0]),str(c[1]))
                time.sleep(3)
                continue
        except Exception:
            pass

        try:
            if not controller.tiktok_foreground():
                controller.androidctl("launch",controller.TIKTOK,check=False)
        except Exception:
            pass
        time.sleep(2)
    else:
        raise PublishError("profile verification: could not reach Profile")

    # Open private-video tab.
    xml=controller.dump_ui()
    c,_=controller.find_node(xml,desc="私密视频",clickable=True)
    if not c:
        raise PublishError("profile verification: private-video tab not found")
    controller.androidctl("tap",str(c[0]),str(c[1]))
    time.sleep(4)

    # Select newest visible private video tile.
    xml=controller.dump_ui()
    root=ET.parse(xml).getroot()
    candidates=[]
    for node in root.iter("node"):
        rid=(node.attrib.get("resource-id") or "")
        if not rid.endswith("/ev2") or node.attrib.get("clickable")!="true":
            continue
        b=controller._bounds(node.attrib.get("bounds",""))
        if not b:
            continue
        x1,y1,x2,y2=b
        if y1 >= 900 and (x2-x1) > 200 and (y2-y1) > 200:
            candidates.append((y1,x1,b))
    if not candidates:
        raise PublishError("profile verification: no private video tile found")
    _,_,b=sorted(candidates)[0]
    c=((b[0]+b[2])//2,(b[1]+b[3])//2)
    controller.androidctl("tap",str(c[0]),str(c[1]))
    time.sleep(4)

    # Exact caption + private label is the final success gate.
    xml=controller.dump_ui()
    root=ET.parse(xml).getroot()
    exact=False
    private=False
    for node in root.iter("node"):
        text=(node.attrib.get("text") or "").strip()
        rid=(node.attrib.get("resource-id") or "")
        if rid.endswith("/desc") and text==caption:
            exact=True
        if rid.endswith("/tv_label") and text=="私密":
            private=True
    evidence=capture_evidence(job,"profile-private-verified")
    if not (exact and private):
        raise PublishError(
            f"profile verification failed: exact_caption={exact} private_label={private}; evidence={evidence}"
        )
    return {
        "verified":True,
        "method":"profile_private_exact_caption",
        "caption":caption,
        "evidence":evidence,
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
    visibility=str(metadata.get("visibility",manifest.get("visibility","PRIVATE"))).upper()
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

    update("PREFLIGHT",args.job_id,publish_mode=mode,visibility=visibility)
    run([str(PREFLIGHT)])

    try:
        update("STAGING",args.job_id)
        run([sys.executable,str(STAGER),args.job_id])

        update("NAVIGATING",args.job_id)
        controller.go_to_post_config(reset=True)

        if title:
            title_result=controller.set_title(title)
        else:
            title_result={"status":"SKIPPED","reason":"empty_title"}

        controller.set_caption(caption)
        visibility_result=controller.set_visibility(visibility)
        st=verify_post_config()

        update("READY_TO_COMMIT",args.job_id,
               title=title_result,
               caption_verified=True,
               visibility=visibility_result,
               ui_state=st)

        if mode=="DRY_RUN":
            controller.restore_input_method()
            controller.root_exec(f"am force-stop {controller.TIKTOK}",check=False)
            print(json.dumps({"job_id":args.job_id,"status":"DRY_RUN_PASS"},ensure_ascii=False))
            return

        if mode!="COMMIT":
            raise PublishError(f"unsupported publish_mode={mode}")
        if not args.commit:
            raise PublishError("manifest requests COMMIT but --commit was not supplied")

        update("COMMITTING",args.job_id)
        submission=commit_publish(job,args.job_id)

        if visibility=="PRIVATE":
            verification=verify_private_post(job,caption)
        else:
            verification={
                "verified":True,
                "method":"submission_confirmation_only",
                "note":"profile exact-caption verification is currently implemented for PRIVATE posts",
            }

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
        controller.restore_input_method()
        update("FAILED",args.job_id,reason=str(e))
        raise

if __name__=="__main__":
    main()
