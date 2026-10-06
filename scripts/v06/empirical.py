#!/usr/bin/env python3
from __future__ import annotations
import argparse, fcntl, os, re, shutil, stat, sys, threading, time
from pathlib import Path
from _common import *

def preflight(a):
    rc,rev,_=run(["git","rev-parse","HEAD"]); rs,dirty,_=run(["git","status","--porcelain"])
    base=Path("/opt/y700") if Path("/opt/y700").exists() else REPO; disk=shutil.disk_usage(base)
    jobs=Path("/opt/y700/jobs"); active=len([p for p in (jobs/"active").glob("*") if p.is_dir()]) if (jobs/"active").exists() else 0
    reconcile=len([p for p in (jobs/"archive"/"reconcile_required").glob("*") if p.is_dir()]) if (jobs/"archive"/"reconcile_required").exists() else 0
    ok=rc==0 and disk.free>256*1024*1024; reasons=[]
    if rc!=0: reasons.append("GIT_BASELINE_UNAVAILABLE")
    if disk.free<=256*1024*1024: reasons.append("LOW_SPACE")
    return result("preflight-baseline",ok,"P0B_PRE_IMPLEMENTATION",{"git_revision":rev if rc==0 else None,"git_dirty":bool(dirty) if rs==0 else None,"free_bytes":disk.free,"active_bridge_jobs":active,"reconcile_required_bridge_jobs":reconcile},reasons)

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
    rp,pidtxt,_=android("pidof system_server 2>/dev/null | awk '{print $1}'")
    pid=int(pidtxt) if rp==0 and pidtxt.isdigit() else None; parsed=None
    if pid:
        try: parsed=parse_proc_stat(Path(f"/proc/{pid}/stat").read_text())
        except OSError: pass
    rb,hboot,_=android("cat /proc/sys/kernel/random/boot_id 2>/dev/null")
    ok=bool(pid and parsed and rb==0 and hboot.strip()==boot); why=[]
    if not pid: why.append("ANDROID_HOST_PID_UNAVAILABLE")
    if pid and not parsed: why.append("PROC_STAT_UNREADABLE")
    if rb!=0 or hboot.strip()!=boot: why.append("BOOT_ID_MISMATCH")
    return result("proc-visibility",ok,"P0B_PRE_IMPLEMENTATION",{"android_process":"system_server","pid":pid,"proc_state":parsed[0] if parsed else None,"proc_start_ticks":parsed[1] if parsed else None,"classifier_fixture":["MATCHING","DEAD","PID_REUSED","STOPPED","ZOMBIE","UNREADABLE"]},why)

def clock_source(a):
    boot=Path("/proc/sys/kernel/random/boot_id").read_text().strip(); rb,hboot,_=android("cat /proc/sys/kernel/random/boot_id")
    def local_up(): return float(Path("/proc/uptime").read_text().split()[0])
    r1,u1,_=android("cat /proc/uptime | awk '{print $1}'"); l1=local_up(); time.sleep(.5)
    r2,u2,_=android("cat /proc/uptime | awk '{print $1}'"); l2=local_up()
    try: deltas=[abs(l1-float(u1)),abs(l2-float(u2))]
    except Exception: deltas=[]
    same=rb==0 and hboot.strip()==boot and len(deltas)==2 and max(deltas)<=2.0
    suspend=bool(a.suspend_evidence); ok=same and suspend; why=[]
    if not same: why.append("HOST_CHROOT_BOOTTIME_EQUIVALENCE_UNPROVEN")
    if not suspend: why.append("SUSPEND_DELTA_EVIDENCE_REQUIRED")
    return result("clock-source",ok,"P0B_PRE_IMPLEMENTATION",{"boot_id_match":rb==0 and hboot.strip()==boot,"uptime_delta_sec":deltas,"suspend_delta_evidence":"SUPPLIED_EXTERNALLY" if suspend else "NOT_RUN","note":"--suspend-evidence is valid only after controlled screen-off/suspend/wake measurement."},why)

def admission(a):
    root=Path(a.bench_dir or "/opt/y700/runtime/v06-phase0b-bench"); root.mkdir(parents=True,exist_ok=True)
    payload=b"x"*(a.payload_kib*1024); vals=[]; errors=[]; guard=threading.Lock()
    def one(w,i):
        start=time.clock_gettime(time.CLOCK_BOOTTIME)
        with open(root/"admission.lock","a+b") as f:
            fcntl.flock(f.fileno(),fcntl.LOCK_EX); tmp=root/f"sample-{w}-{i}.tmp"; dst=root/f"sample-{w}-{i}.json"
            with open(tmp,"wb") as out: out.write(payload); out.flush(); os.fsync(out.fileno())
            os.replace(tmp,dst); dfd=os.open(root,os.O_DIRECTORY); os.fsync(dfd); os.close(dfd); fcntl.flock(f.fileno(),fcntl.LOCK_UN)
        return (time.clock_gettime(time.CLOCK_BOOTTIME)-start)*1000
    def worker(w):
        local=[]
        try:
            for i in range(a.iterations): local.append(one(w,i))
        except Exception as e: errors.append(type(e).__name__+":"+str(e))
        with guard: vals.extend(local)
    ts=[threading.Thread(target=worker,args=(w,)) for w in range(a.workers)]
    [t.start() for t in ts]; [t.join() for t in ts]
    vals.sort()
    pct=lambda q: vals[min(len(vals)-1,max(0,int(round((len(vals)-1)*q))))] if vals else 0.0
    p99=pct(.99); cand=next((x for x in (5000,10000,15000) if p99<.5*x),None); ok=bool(vals) and not errors and cand is not None
    return result("admission-lock-load",ok,"P0B_PRE_IMPLEMENTATION",{"synthetic_representative_only":True,"samples":len(vals),"p95_ms":round(pct(.95),3),"p99_ms":round(p99,3),"initial_timeout_candidate_ms":cand,"workers":a.workers,"iterations_per_worker":a.iterations,"payload_kib":a.payload_kib},errors+([] if cand else ["NO_TIMEOUT_CANDIDATE"]))

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
    ok=rc==0 and bool(rows)
    return result("zui-overlay-inventory",ok,"P0B_PRE_IMPLEMENTATION_EVIDENCE",{"snapshot_captured":ok,"window_lines":rows[:200],"proposed_exact_allowlist":[],"policy":"no wildcard allowlist; unknown input-intercepting overlay fails closed","coverage_note":"Activate optional ZUI/game/sidebar/PiP/accessibility overlays during empirical acceptance."},[] if ok else ["WINDOW_INVENTORY_UNAVAILABLE"])

def wakelock(a):
    found=inventory([("wake_lock",re.compile(r"(?:WAKE_LOCK|WakeLock|newWakeLock)")),("keep_screen_on",re.compile(r"(?:FLAG_KEEP_SCREEN_ON|keepScreenOn)"))]); has=any(found.values())
    return result("suspend-wakelock-policy",True,"P0B_PRE_IMPLEMENTATION_EVIDENCE",{"current_runtime_mechanism_found":has,"source_findings":found,"intended_policy":"bounded ownership-scoped wake-lock" if has else "no wake-lock assumed; suspend expiry -> fresh AUTO preflight","token_semantics":"CLOCK_BOOTTIME includes suspend"})

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
    if ns.check=="clock-source": p.add_argument("--suspend-evidence",action="store_true")
    if ns.check=="admission-lock-load":
        p.add_argument("--bench-dir"); p.add_argument("--workers",type=int,default=4); p.add_argument("--iterations",type=int,default=12); p.add_argument("--payload-kib",type=int,default=128)
    return emit(CHECKS[ns.check](p.parse_args(rest)))
if __name__=="__main__": raise SystemExit(main())
