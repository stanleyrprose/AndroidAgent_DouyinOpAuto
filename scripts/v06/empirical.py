#!/usr/bin/env python3
from __future__ import annotations
import argparse, fcntl, json, os, re, shutil, stat, sys, threading, time
from pathlib import Path
from _common import *


def preflight(a):
    rc,rev,_=run(["git","rev-parse","HEAD"])
    rs,dirty,_=run(["git","status","--porcelain"])
    base=Path("/opt/y700") if Path("/opt/y700").exists() else REPO
    disk=shutil.disk_usage(base)
    jobs=Path("/opt/y700/jobs")
    active=len([p for p in (jobs/"active").glob("*") if p.is_dir()]) if (jobs/"active").exists() else 0
    reconcile=len([p for p in (jobs/"archive"/"reconcile_required").glob("*") if p.is_dir()]) if (jobs/"archive"/"reconcile_required").exists() else 0

    rboot,boot,_=android("getprop sys.boot_completed")
    ruid,uid,_=android("id -u")
    rround,roundtrip,_=android("printf phase0b-root-roundtrip")

    def apk_sha(package):
        rp,paths,_=android(f"pm path {package}")
        apk=None
        for line in paths.splitlines():
            if line.startswith("package:"):
                apk=line.split(":",1)[1].strip()
                break
        if rp!=0 or not apk:
            return {"package":package,"available":False,"path":None,"sha256":None}
        rh,raw,_=android(f"sha256sum {apk}")
        token=raw.split()[0].lower() if rh==0 and raw.split() else None
        if token is not None and not re.fullmatch(r"[0-9a-f]{64}",token):
            token=None
        return {"package":package,"available":True,"path":apk,"sha256":token}

    apks=[apk_sha("com.stanley.y700automation"),apk_sha("com.stanley.y700automation.test")]
    claims=[]
    current_claim=False
    for p in (
        Path("/opt/y700/runtime/resources/android_ui/claim.json"),
        Path("/opt/y700/runtime/android_ui/claim.json"),
        Path("/opt/y700/runtime/android-ui.lock"),
    ):
        row={"path":str(p),"exists":p.exists(),"is_symlink":p.is_symlink()}
        if p.exists():
            st=p.lstat()
            row.update({"uid":st.st_uid,"gid":st.st_gid,"mode":oct(stat.S_IMODE(st.st_mode)),"size":st.st_size})
            if p.name=="claim.json":
                current_claim=True
        claims.append(row)

    reasons=[]
    if rc!=0: reasons.append("GIT_BASELINE_UNAVAILABLE")
    if rs!=0 or bool(dirty.strip()): reasons.append("GIT_DIRTY")
    if disk.free<=256*1024*1024: reasons.append("LOW_SPACE")
    if rboot!=0 or boot.strip()!="1": reasons.append("DEVICE_NOT_BOOT_COMPLETED")
    if ruid!=0 or uid.strip()!="0": reasons.append("ROOT_BRIDGE_UNAVAILABLE")
    if rround!=0 or roundtrip.strip()!="phase0b-root-roundtrip": reasons.append("ROOT_ROUNDTRIP_FAILED")
    if not apks[0]["available"] or not apks[0]["sha256"]: reasons.append("AUTOMATION_APK_IDENTITY_UNAVAILABLE")
    if active>0: reasons.append("ACTIVE_BRIDGE_JOBS_PRESENT")
    if current_claim: reasons.append("CURRENT_UI_CLAIM_PRESENT")

    return result("preflight-baseline",not reasons,"P0B_PRE_IMPLEMENTATION",{
        "git_revision":rev if rc==0 else None,
        "git_dirty":bool(dirty.strip()) if rs==0 else None,
        "free_bytes":disk.free,
        "device_health":{
            "boot_completed":boot.strip() if rboot==0 else None,
            "android_root_uid":uid.strip() if ruid==0 else None,
            "root_roundtrip":roundtrip.strip() if rround==0 else None,
        },
        "installed_apks":apks,
        "claim_inventory":claims,
        "active_bridge_jobs":active,
        "reconcile_required_bridge_jobs":reconcile,
    },reasons)
def permissions(a):
    rows=[]; bad=[]
    for p in map(Path,("/opt/y700/runtime","/opt/y700/jobs","/opt/y700/runtime/state","/opt/y700/ui-jobs")):
        if not p.exists():
            rows.append({"path":str(p),"exists":False})
            if p.name in {"runtime","jobs"}: bad.append("MISSING:"+str(p))
            continue
        st=p.lstat(); mode=stat.S_IMODE(st.st_mode)
        rows.append({"path":str(p),"exists":True,"uid":st.st_uid,"gid":st.st_gid,"mode":oct(mode),"is_symlink":p.is_symlink(),"readable":os.access(p,os.R_OK),"writable":os.access(p,os.W_OK)})
        if p.is_symlink(): bad.append("SYMLINK:"+str(p))
        if mode&0o002: bad.append("WORLD_WRITABLE:"+str(p))
        if st.st_uid!=0: bad.append("NON_ROOT_OWNER:"+str(p))
        if not os.access(p,os.R_OK): bad.append("UNREADABLE:"+str(p))
    return result("runtime-permissions",not bad,"P0B_PRE_IMPLEMENTATION",{"paths":rows},bad)

def parse_proc_stat(s):
    m=re.match(r"^\d+\s+\(.+\)\s+([A-Z])\s+(?:\S+\s+){18}(\d+)",s.strip())
    return (m.group(1),int(m.group(2))) if m else None


def proc_visibility(a):
    boot=Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    rp,pidtxt,_=android("pidof system_server")
    pid=int(pidtxt.split()[0]) if rp==0 and pidtxt.split() and pidtxt.split()[0].isdigit() else None
    parsed=None
    if pid:
        try: parsed=parse_proc_stat(Path(f"/proc/{pid}/stat").read_text())
        except OSError: pass
    rb,hboot,_=android("cat /proc/sys/kernel/random/boot_id")

    def classify(expected_start, observation):
        if observation=="UNREADABLE": return "UNREADABLE"
        if observation is None: return "DEAD"
        state,start=observation
        if start!=expected_start: return "PID_REUSED"
        if state in {"T","t"}: return "STOPPED"
        if state=="Z": return "ZOMBIE"
        return "MATCHING"

    fixture={
        "MATCHING":classify(10,("S",10))=="MATCHING",
        "DEAD":classify(10,None)=="DEAD",
        "PID_REUSED":classify(10,("S",11))=="PID_REUSED",
        "STOPPED":classify(10,("T",10))=="STOPPED",
        "ZOMBIE":classify(10,("Z",10))=="ZOMBIE",
        "UNREADABLE":classify(10,"UNREADABLE")=="UNREADABLE",
    }
    ok=bool(pid and parsed and rb==0 and hboot.strip()==boot and all(fixture.values()))
    why=[]
    if not pid: why.append("ANDROID_HOST_PID_UNAVAILABLE")
    if pid and not parsed: why.append("PROC_STAT_UNREADABLE")
    if rb!=0 or hboot.strip()!=boot: why.append("BOOT_ID_MISMATCH")
    if not all(fixture.values()): why.append("PROC_CLASSIFIER_FIXTURE_FAILED")
    return result("proc-visibility",ok,"P0B_PRE_IMPLEMENTATION",{
        "android_process":"system_server",
        "pid":pid,
        "proc_state":parsed[0] if parsed else None,
        "proc_start_ticks":parsed[1] if parsed else None,
        "classifier_fixture":fixture,
    },why)
def clock_source(a):
    boot=Path("/proc/sys/kernel/random/boot_id").read_text().strip(); rb,hboot,_=android("cat /proc/sys/kernel/random/boot_id")
    def local_up(): return float(Path("/proc/uptime").read_text().split()[0])
    r1,u1,_=android("cat /proc/uptime | awk '{print $1}'"); l1=local_up(); time.sleep(.5)
    r2,u2,_=android("cat /proc/uptime | awk '{print $1}'"); l2=local_up()
    try: deltas=[abs(l1-float(u1)),abs(l2-float(u2))]
    except Exception: deltas=[]
    same=rb==0 and hboot.strip()==boot and len(deltas)==2 and max(deltas)<=2.0
    evidence=None; evidence_error=None; suspend_ok=False
    if a.suspend_evidence_file:
        try:
            evidence=json.loads(Path(a.suspend_evidence_file).read_text(encoding="utf-8"))
            before=evidence["before"]; after=evidence["after"]
            host_elapsed=float(after["host_uptime_s"])-float(before["host_uptime_s"])
            chroot_elapsed=float(after["chroot_uptime_s"])-float(before["chroot_uptime_s"])
            suspend_ok=(
                evidence.get("kind")=="controlled_suspend_wake"
                and evidence.get("boot_id")==boot
                and evidence.get("screen_off_or_suspend_observed") is True
                and host_elapsed>0 and chroot_elapsed>0
                and abs(float(before["host_uptime_s"])-float(before["chroot_uptime_s"]))<=2.0
                and abs(float(after["host_uptime_s"])-float(after["chroot_uptime_s"]))<=2.0
                and abs(host_elapsed-chroot_elapsed)<=2.0
            )
        except Exception as exc:
            evidence_error=type(exc).__name__+":"+str(exc)
    ok=same and suspend_ok; why=[]
    if not same: why.append("HOST_CHROOT_BOOTTIME_EQUIVALENCE_UNPROVEN")
    if not suspend_ok: why.append("SUSPEND_DELTA_EVIDENCE_REQUIRED")
    return result("clock-source",ok,"P0B_PRE_IMPLEMENTATION",{"boot_id_match":rb==0 and hboot.strip()==boot,"uptime_delta_sec":deltas,"suspend_evidence_file":a.suspend_evidence_file,"suspend_evidence_valid":suspend_ok,"evidence_error":evidence_error},why)


def admission(a):
    root=Path(a.bench_dir or "/opt/y700/runtime/v06-phase0b-bench")
    root.mkdir(parents=True,exist_ok=True)
    os.chmod(root,0o700)
    payload=b"x"*(a.payload_kib*1024)
    values=[]
    same_values=[]
    different_values=[]
    errors=[]
    coverage={
        "tiktok_cold_start_runs":0,
        "media_decode_runs":0,
        "media_io_bytes":0,
        "fsync_heavy_journal":False,
        "same_submission_samples":0,
        "different_submission_samples":0,
    }
    guard=threading.Lock()
    media=root/"representative.mp4"
    rg,_,eg=run([
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-f","lavfi","-i","testsrc2=size=1280x720:rate=30",
        "-t","3","-c:v","mpeg4","-q:v","5",str(media)
    ],60)
    if rg!=0 or not media.exists():
        errors.append("MEDIA_FIXTURE_GENERATION_FAILED:"+eg[-200:])

    def fsync_iteration(worker_id,index,same_submission):
        start=time.clock_gettime(time.CLOCK_BOOTTIME)
        with open(root/"admission.lock","a+b") as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
            stem="same-submission" if same_submission else f"different-{worker_id}-{index}"
            tmp=root/f"{stem}-{worker_id}-{index}.tmp"
            dst=root/f"{stem}.json"
            with open(tmp,"wb") as out:
                out.write(payload); out.flush(); os.fsync(out.fileno())
            with open(root/"admission-journal.log","ab") as journal:
                journal.write((stem+"\\n").encode()); journal.flush(); os.fsync(journal.fileno())
            os.replace(tmp,dst)
            dfd=os.open(root,os.O_DIRECTORY)
            try: os.fsync(dfd)
            finally: os.close(dfd)
            fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
        return (time.clock_gettime(time.CLOCK_BOOTTIME)-start)*1000

    def admission_worker(worker_id):
        local=[]; same_local=[]; different_local=[]
        try:
            same_submission=(worker_id%2)==0
            for index in range(a.iterations):
                value=fsync_iteration(worker_id,index,same_submission)
                local.append(value)
                (same_local if same_submission else different_local).append(value)
        except Exception as exc:
            errors.append(type(exc).__name__+":"+str(exc))
        with guard:
            values.extend(local); same_values.extend(same_local); different_values.extend(different_local)

    def media_worker():
        if not media.exists(): return
        try:
            for _ in range(3):
                rc,_,err=run(["ffmpeg","-hide_banner","-loglevel","error","-threads","1","-i",str(media),"-f","null","-"],60)
                if rc!=0:
                    errors.append("MEDIA_DECODE_FAILED:"+err[-200:]); return
                with guard: coverage["media_decode_runs"]+=1
                total=0
                with open(media,"rb") as handle:
                    while True:
                        chunk=handle.read(1024*1024)
                        if not chunk: break
                        total+=len(chunk)
                with guard: coverage["media_io_bytes"]+=total
        except Exception as exc:
            errors.append("MEDIA_WORKLOAD:"+type(exc).__name__+":"+str(exc))

    def tiktok_worker():
        try:
            for _ in range(2):
                rc,_,err=android("am force-stop com.zhiliaoapp.musically; monkey -p com.zhiliaoapp.musically -c android.intent.category.LAUNCHER 1; sleep 2")
                if rc!=0:
                    errors.append("TIKTOK_COLD_START_FAILED:"+err[-200:]); return
                with guard: coverage["tiktok_cold_start_runs"]+=1
                android("am force-stop com.zhiliaoapp.musically")
        except Exception as exc:
            errors.append("TIKTOK_WORKLOAD:"+type(exc).__name__+":"+str(exc))

    pressure=[threading.Thread(target=media_worker),threading.Thread(target=tiktok_worker)]
    workers=[threading.Thread(target=admission_worker,args=(worker,)) for worker in range(a.workers)]
    for thread in pressure+workers: thread.start()
    for thread in pressure+workers: thread.join()
    android("input keyevent KEYCODE_HOME")

    values.sort()
    pct=lambda vals,q: vals[min(len(vals)-1,max(0,int(round((len(vals)-1)*q))))] if vals else 0.0
    p95=pct(values,.95); p99=pct(values,.99)
    candidate=next((x for x in (5000,10000,15000) if p99<.5*x),None)
    coverage["fsync_heavy_journal"]=bool(values)
    coverage["same_submission_samples"]=len(same_values)
    coverage["different_submission_samples"]=len(different_values)
    coverage_ok=(
        coverage["tiktok_cold_start_runs"]>=1
        and coverage["media_decode_runs"]>=1
        and coverage["media_io_bytes"]>0
        and coverage["fsync_heavy_journal"]
        and coverage["same_submission_samples"]>0
        and coverage["different_submission_samples"]>0
    )
    ok=bool(values) and not errors and candidate is not None and coverage_ok
    if not coverage_ok: errors.append("REPRESENTATIVE_WORKLOAD_COVERAGE_INCOMPLETE")
    return result("admission-lock-load",ok,"P0B_PRE_IMPLEMENTATION",{
        "synthetic_representative_only":True,
        "samples":len(values),
        "p95_ms":round(p95,3),
        "p99_ms":round(p99,3),
        "same_submission_p99_ms":round(pct(sorted(same_values),.99),3),
        "different_submission_p99_ms":round(pct(sorted(different_values),.99),3),
        "initial_timeout_candidate_ms":candidate,
        "workers":a.workers,
        "iterations_per_worker":a.iterations,
        "payload_kib":a.payload_kib,
        "workload_coverage":coverage,
        "threshold_rule":"synthetic representative p99 < candidate * 0.5",
    },errors+([] if candidate else ["NO_TIMEOUT_CANDIDATE"]))
def package_ev(pkg):
    rc,out,err=android(f"dumpsys package {pkg} 2>/dev/null")
    if rc!=0 or not out: return {"package":pkg,"available":False,"error":err or f"rc={rc}"}
    vn=vc=sig=None
    for line in out.splitlines():
        s=line.strip()
        if s.startswith("versionName=") and vn is None: vn=s.split("=",1)[1]
        if s.startswith("versionCode=") and vc is None: vc=s.split("=",1)[1].split()[0]
        if ("signatures=" in s or "Signing" in s) and sig is None: sig=s[:500]
    return {"package":pkg,"available":True,"version_name":vn,"version_code":vc,"signing_identity_evidence":sig}

def app_contract(a):
    rows=[package_ev("com.android.settings"),package_ev("com.zhiliaoapp.musically")]; bad=[]
    for x in rows:
        if not x["available"]: bad.append("PACKAGE_UNAVAILABLE:"+x["package"])
        elif not x["version_code"]: bad.append("VERSION_UNAVAILABLE:"+x["package"])
        elif not x["signing_identity_evidence"]: bad.append("SIGNING_IDENTITY_UNAVAILABLE:"+x["package"])
    return result("app-ui-contract",not bad,"P0B_PRE_IMPLEMENTATION_EVIDENCE",{"installed_app_evidence":rows,"production_exact_compare_expected_after":"Catalog app_ui_contract implementation"},bad)

def overlay(a):
    rc,out,_=android("dumpsys window windows 2>/dev/null")
    rows=[s.strip()[:500] for s in out.splitlines() if ("Window #" in s or "mCurrentFocus=" in s or "mFocusedApp=" in s or "mAttrs=" in s)] if out else []
    snapshot_ok=rc==0 and bool(rows)
    required={"IME","TOAST_OR_TRANSIENT","ZUI_GAME_OR_PERFORMANCE","FLOATING_SIDEBAR_OR_SPLIT","PIP","ACCESSIBILITY_OVERLAY"}
    evidence=None; evidence_error=None; coverage_ok=False; proposed=[]
    if a.coverage_evidence_file:
        try:
            evidence=json.loads(Path(a.coverage_evidence_file).read_text(encoding="utf-8"))
            scenarios={x["name"]:x for x in evidence.get("scenarios",[]) if isinstance(x,dict) and "name" in x}
            declared=required.issubset(scenarios)
            captured=declared and all((x.get("present") is False) or (x.get("present") is True and x.get("captured") is True) for x in (scenarios[n] for n in required))
            proposed=evidence.get("proposed_exact_allowlist",[])
            coverage_ok=declared and captured and isinstance(proposed,list)
        except Exception as exc:
            evidence_error=type(exc).__name__+":"+str(exc)
    ok=snapshot_ok and coverage_ok; why=[]
    if not snapshot_ok: why.append("WINDOW_INVENTORY_UNAVAILABLE")
    if not coverage_ok: why.append("OVERLAY_SCENARIO_COVERAGE_INCOMPLETE")
    return result("zui-overlay-inventory",ok,"P0B_PRE_IMPLEMENTATION_EVIDENCE",{"snapshot_captured":snapshot_ok,"window_lines":rows[:200],"coverage_evidence_file":a.coverage_evidence_file,"coverage_complete":coverage_ok,"proposed_exact_allowlist":proposed,"policy":"no wildcard allowlist; unknown input-intercepting overlay fails closed","evidence_error":evidence_error},why)


def wakelock(a):
    found=inventory([
        ("wake_lock",re.compile(r"(?:WAKE_LOCK|WakeLock|newWakeLock)")),
        ("keep_screen_on",re.compile(r"(?:FLAG_KEEP_SCREEN_ON|keepScreenOn)")),
    ])
    has=any(found.values())
    evidence_ok=False
    evidence_error=None
    suspend_delta=None
    if a.suspend_evidence_file:
        try:
            evidence=json.loads(Path(a.suspend_evidence_file).read_text(encoding="utf-8"))
            suspend_delta=int(evidence.get("suspend_success_delta",0))
            evidence_ok=(
                evidence.get("kind")=="controlled_suspend_wake"
                and evidence.get("screen_off_or_suspend_observed") is True
                and suspend_delta>0
            )
        except Exception as exc:
            evidence_error=type(exc).__name__+":"+str(exc)
    reasons=[]
    if not evidence_ok: reasons.append("CONTROLLED_SUSPEND_EVIDENCE_REQUIRED")
    intended=(
        "bounded ownership-scoped wake-lock; release immediately when ownership ends or blocks"
        if has else
        "current runtime has no dedicated deep-sleep prevention; accept suspend, require fresh AUTO observe/preflight, and never relax CLOCK_BOOTTIME token age"
    )
    return result("suspend-wakelock-policy",evidence_ok,"P0B_PRE_IMPLEMENTATION_EVIDENCE",{
        "current_runtime_mechanism_found":has,
        "active_workflow_deep_sleep_prevention_available":has,
        "controlled_suspend_observed":evidence_ok,
        "suspend_success_delta":suspend_delta,
        "suspend_evidence_file":a.suspend_evidence_file,
        "evidence_error":evidence_error,
        "source_findings":found,
        "intended_policy":intended,
        "token_semantics":"CLOCK_BOOTTIME includes suspend; wake-lock never extends token correctness lifetime",
    },reasons)
def upgrade(a):
    blockers=[]
    for r in (Path("/opt/y700/jobs/active"),Path("/opt/y700/ui-jobs")):
        if r.exists():
            for p in r.iterdir():
                if p.is_dir(): blockers.append({"kind":"ACTIVE_JOB_OR_UI_SESSION","path":str(p)})
    return result("upgrade-gate",True,"SPRINT_GATED_FIXTURE",{"dry_run_complete":True,"would_block_upgrade":bool(blockers),"blockers":blockers[:100],"rule":"block unresolved legacy mutation/COMMITTING/reconcile state"})

def fault(a):
    rc,out,err=run([sys.executable,"-m","unittest","discover","-s","tests/fault_injection","-v"],120)
    return result("fault-injection-harness",rc==0,"P0B_PRE_IMPLEMENTATION",{"returncode":rc,"stdout":out[-4000:],"stderr":err[-4000:]},[] if rc==0 else ["FAULT_HARNESS_SELF_TEST_FAILED"])

CHECKS={"preflight-baseline":preflight,"runtime-permissions":permissions,"proc-visibility":proc_visibility,"clock-source":clock_source,"admission-lock-load":admission,"app-ui-contract":app_contract,"zui-overlay-inventory":overlay,"suspend-wakelock-policy":wakelock,"upgrade-gate":upgrade,"fault-injection-harness":fault}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("check",choices=sorted(CHECKS)); ns,rest=ap.parse_known_args()
    p=argparse.ArgumentParser()
    if ns.check in {"clock-source","suspend-wakelock-policy"}: p.add_argument("--suspend-evidence-file")
    if ns.check=="zui-overlay-inventory": p.add_argument("--coverage-evidence-file")
    if ns.check=="admission-lock-load":
        p.add_argument("--bench-dir"); p.add_argument("--workers",type=int,default=4); p.add_argument("--iterations",type=int,default=12); p.add_argument("--payload-kib",type=int,default=128)
    return emit(CHECKS[ns.check](p.parse_args(rest)))
if __name__=="__main__": raise SystemExit(main())
