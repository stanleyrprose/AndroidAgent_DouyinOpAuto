#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, secrets
from pathlib import Path
RUNTIME = Path(os.environ.get("Y700_RUNTIME", "/opt/y700/runtime"))
STATE_DIR = Path(os.environ.get("Y700_STATE_INTEGRITY_DIR", str(RUNTIME / "state-integrity")))
STATE_PATH = STATE_DIR / "state.json"
JOURNAL_PATH = STATE_DIR / "mutation-journal.jsonl"
class StateIntegrityError(RuntimeError): pass
def _fsync_dir(path):
    fd=os.open(path,os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
def _atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp=path.with_name(path.name+".tmp-"+secrets.token_hex(4))
    with open(tmp,"w",encoding="utf-8") as f:
        json.dump(value,f,ensure_ascii=False,sort_keys=True,separators=(",",":")); f.write("\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path); _fsync_dir(path.parent)
def _append(value):
    STATE_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(JOURNAL_PATH,"a",encoding="utf-8") as f:
        f.write(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n"); f.flush(); os.fsync(f.fileno())
def canonical_semantic_v1(observation):
    elements=[]
    for row in observation.get("elements") or []:
        elements.append({
            "resource_id":row.get("resource_id"),"text":row.get("text"),"content_desc":row.get("content_desc"),
            "class":row.get("class"),"package":row.get("package"),"clickable":bool(row.get("clickable",False)),
            "enabled":bool(row.get("enabled",False)),"selected":bool(row.get("selected",False)),"checked":bool(row.get("checked",False)),
        })
    return {"schema":"semantic-v1","foreground":{"package":observation.get("package"),"activity":observation.get("activity")},
            "blocking_overlay_present":bool(observation.get("blocking_overlay_present",False)),"elements":elements,
            "properties":observation.get("properties") or {}}
def semantic_hash(observation):
    payload=json.dumps(canonical_semantic_v1(observation),ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    return "sha256:"+hashlib.sha256(payload).hexdigest()
def load_state():
    try:
        with open(STATE_PATH,encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError:
        state={"schema_version":1,"state_epoch":1,"revision":0}; _atomic_json(STATE_PATH,state); return state
def issue_token(observation,*,boot_id):
    state=load_state()
    return {"schema":"state-token-v1","state_epoch":state["state_epoch"],"revision":state["revision"],"state_hash":semantic_hash(observation),"boot_id":boot_id}
def assert_token(token,observation,*,boot_id):
    state=load_state()
    if token.get("boot_id")!=boot_id or token.get("state_epoch")!=state.get("state_epoch"): raise StateIntegrityError("STALE_STATE_EPOCH")
    if token.get("revision")!=state.get("revision"): raise StateIntegrityError("STALE_STATE_REVISION")
    if token.get("state_hash")!=semantic_hash(observation): raise StateIntegrityError("STALE_STATE_HASH")
def prepare_mutation(*,mutation_id,action,claim_id):
    _append({"phase":"MUTATION_PREPARED","mutation_id":mutation_id,"action":action,"claim_id":claim_id})
def commit_mutation(*,mutation_id,action,claim_id,post_hash):
    state=load_state()
    new={"schema_version":1,"state_epoch":int(state["state_epoch"]),"revision":int(state["revision"])+1,"state_hash":post_hash}
    _atomic_json(STATE_PATH,new)
    _append({"phase":"MUTATION_COMMITTED","mutation_id":mutation_id,"action":action,"claim_id":claim_id,"revision":new["revision"],"state_hash":post_hash})
    return new
def bump_epoch(reason):
    state=load_state()
    new={"schema_version":1,"state_epoch":int(state["state_epoch"])+1,"revision":0,"invalidation_reason":reason}
    _atomic_json(STATE_PATH,new); _append({"phase":"STATE_EPOCH_BUMPED","state_epoch":new["state_epoch"],"reason":reason}); return new
