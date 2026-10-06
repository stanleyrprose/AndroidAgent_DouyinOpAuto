from __future__ import annotations
import fcntl, hashlib, json, os, re, secrets, time
from datetime import datetime, timezone
from pathlib import Path
from .catalog import resolve
ROOT=Path(os.environ.get("Y700_ROOT","/opt/y700"))
JOBS=Path(os.environ.get("Y700_CAPABILITY_JOBS",str(ROOT/"capability-jobs")))
RUNTIME=Path(os.environ.get("Y700_RUNTIME",str(ROOT/"runtime")))
SUBMISSIONS=RUNTIME/"submissions"
SUBMISSION_RE=re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
class CapabilityError(RuntimeError): pass
def canonical(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
def sha(value): return hashlib.sha256(canonical(value)).hexdigest()
def now_iso(): return datetime.now(timezone.utc).astimezone().isoformat()
def _fsync_dir(path):
    fd=os.open(path,os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp=path.with_name(path.name+".tmp-"+secrets.token_hex(4))
    with open(tmp,"wb") as f:
        f.write(canonical(value)+b"\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path); _fsync_dir(path.parent)
def immutable_request(req):
    forbidden={"policy_overrides","resources","approval","verification","replay"}
    if forbidden.intersection(req): raise CapabilityError("POLICY_WEAKENING_NOT_ALLOWED")
    sid=req.get("submission_id")
    if not isinstance(sid,str) or not SUBMISSION_RE.fullmatch(sid): raise CapabilityError("REQUEST_INVALID")
    requested_by=req.get("requested_by")
    if not isinstance(requested_by,dict) or not requested_by.get("type") or not requested_by.get("name"): raise CapabilityError("REQUEST_INVALID")
    return {k:req.get(k) for k in ("submission_id","capability","version","payload","expires_at","requested_by")}
def effective_policy(req,catalog):
    p=dict(catalog["minimum_policy"])
    p["resource"]=catalog.get("resource")
    expires=req.get("expires_at")
    if expires:
        try: exp=datetime.fromisoformat(expires)
        except ValueError as e: raise CapabilityError("REQUEST_INVALID") from e
        if exp.tzinfo is None: raise CapabilityError("REQUEST_INVALID")
        remain=(exp-datetime.now(timezone.utc)).total_seconds()
        if remain<=0: raise CapabilityError("EXPIRED")
        if remain>int(p.get("expires_in_max_sec",remain))+1: raise CapabilityError("TTL_EXCEEDS_CAPABILITY_MAX")
        p["expires_at"]=expires
    return p
def _binding_path(submission_sha): return SUBMISSIONS/(submission_sha+".json")
def _job_dir(job_id): return JOBS/"active"/job_id
def _activate(job_id,request,request_sha,submission_sha,policy):
    active=_job_dir(job_id)
    if active.exists(): return active
    stage=JOBS/".staging"/(job_id+"-"+secrets.token_hex(4))
    stage.mkdir(parents=True,mode=0o700)
    identity={"capability_job_id":job_id,"submission_sha256":submission_sha,"request_sha256":request_sha,"effective_policy_sha256":sha(policy),"created_at":now_iso()}
    atomic_json(stage/"request.json",request); atomic_json(stage/"effective_policy.json",policy); atomic_json(stage/"identity.json",identity)
    atomic_json(stage/"state.json",{"status":"ACTIVATED","updated_at":now_iso()})
    (stage/"journal.jsonl").write_text(json.dumps({"phase":"ACTIVATED","at":now_iso()},separators=(",",":"))+"\n",encoding="utf-8")
    with open(stage/"journal.jsonl","rb") as f: os.fsync(f.fileno())
    (JOBS/"active").mkdir(parents=True,exist_ok=True,mode=0o700)
    os.replace(stage,active); _fsync_dir(active.parent)
    return active
def admit(req,lock_timeout_ms=5000):
    request=immutable_request(req); catalog=resolve(request["capability"],request["version"]); policy=effective_policy(request,catalog)
    submission_sha=hashlib.sha256(request["submission_id"].encode()).hexdigest(); request_sha=sha(request); job_id="cap-s-"+submission_sha
    SUBMISSIONS.mkdir(parents=True,exist_ok=True,mode=0o700); lock_path=SUBMISSIONS/"admission.lock"; fd=os.open(lock_path,os.O_CREAT|os.O_RDWR,0o600)
    deadline=time.monotonic()+lock_timeout_ms/1000
    try:
        while True:
            try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB); break
            except BlockingIOError:
                if time.monotonic()>=deadline: raise CapabilityError("ADMISSION_LOCK_TIMEOUT")
                time.sleep(0.02)
        bp=_binding_path(submission_sha)
        existed = bp.exists()
        if existed:
            binding=json.loads(bp.read_text(encoding="utf-8"))
            if binding.get("request_sha256")!=request_sha: raise CapabilityError("SUBMISSION_ID_CONFLICT")
        else:
            binding={"submission_version":1,"submission_sha256":submission_sha,"request_sha256":request_sha,"capability_job_id":job_id,"capability":request["capability"],"created_at":now_iso()}
            atomic_json(bp,binding)
        _activate(job_id,request,request_sha,submission_sha,policy)
        return {"capability_job_id":job_id,"existing":existed,"state":"ACTIVATED"}
    finally:
        try: fcntl.flock(fd,fcntl.LOCK_UN)
        finally: os.close(fd)
def verify_contract(job_id):
    d=_job_dir(job_id)
    if not d.is_dir(): raise CapabilityError("JOB_NOT_FOUND")
    ident=json.loads((d/"identity.json").read_text(encoding="utf-8")); req=json.loads((d/"request.json").read_text(encoding="utf-8")); pol=json.loads((d/"effective_policy.json").read_text(encoding="utf-8"))
    if sha(req)!=ident.get("request_sha256") or sha(pol)!=ident.get("effective_policy_sha256"): raise CapabilityError("JOB_CONTRACT_VIOLATION")
    return True
