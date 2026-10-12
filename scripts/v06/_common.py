#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, re, subprocess, unicodedata
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
ROOT_EXEC = REPO / "bridge" / "root-exec.sh"
MUTATIONS = ("click","longClick","input","clear","swipe","scroll","pressBack","pressHome")
V1={"fingerprint_version":"semantic-v1","foreground":{"activity":"com.android.settings.Settings","package":"com.android.settings"},"scope":"FOREGROUND","screen":{"blocking_overlay_class":None,"blocking_overlay_owner_package":None,"blocking_overlay_present":False,"interactive":True,"keyguard_locked":False}}
V1_HASH="sha256:074e74b0f725954b789fea7d905715c7e096c4ab159029a1c6c8ef8a6b610b66"
V2={"cardinality":1,"element":{"checked":True,"clickable":True,"enabled":True,"selected":False},"fingerprint_version":"semantic-v1","foreground":{"activity":"com.android.settings.Settings","package":"com.android.settings"},"scope":"ELEMENT","screen":{"blocking_overlay_class":None,"blocking_overlay_owner_package":None,"blocking_overlay_present":False,"interactive":True,"keyguard_locked":False},"selector":{"resource_id":"android:id/switch_widget"}}
V2_HASH="sha256:6bab7e2cd22bb7e2804f75638edfda2546f73802003c57fde3ecbdd322f32fd4"

def result(name:str, ok:bool, gate:str, details:dict[str,Any], reasons:list[str]|None=None, phase:str="0B"):
    return {"schema_version":1,"phase":phase,"check":name,"status":"PASS" if ok else "FAIL","gate":gate,"reasons":reasons or [],"details":details}

def emit(obj:dict[str,Any]):
    print(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True))
    return 0 if obj["status"]=="PASS" else 1

def run(args:list[str], timeout:float=30):
    p=subprocess.run(args,cwd=REPO,capture_output=True,text=True,timeout=timeout)
    return p.returncode,p.stdout.strip(),p.stderr.strip()

def android(command:str, timeout:float=30):
    if not ROOT_EXEC.exists(): return 127,"",f"missing {ROOT_EXEC}"
    return run([str(ROOT_EXEC),command],timeout)

def semantic_hash(obj:dict[str,Any]):
    def canonicalize(v):
        if isinstance(v,float): raise ValueError("floats_forbidden")
        if isinstance(v,list): raise ValueError("arrays_forbidden")
        if isinstance(v,str): return unicodedata.normalize("NFC",v)
        if isinstance(v,dict):
            out={}
            for k,x in v.items():
                nk=unicodedata.normalize("NFC",k)
                if nk in out: raise ValueError("duplicate_key_after_nfc")
                out[nk]=canonicalize(x)
            return out
        return v
    canonical=canonicalize(obj)
    raw=json.dumps(canonical,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
    return "sha256:"+hashlib.sha256(raw).hexdigest()

def source_files():
    out=[]
    for root in ("apps","automation","bridge","publisher","mac/android-automation"):
        base=REPO/root
        if not base.exists(): continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix in {".py",".sh",".java",".kt",".json"}: out.append(p)
    return sorted(out)

def inventory(patterns):
    found={name:[] for name,_ in patterns}
    for p in source_files():
        rel=str(p.relative_to(REPO))
        try: lines=p.read_text(encoding="utf-8",errors="replace").splitlines()
        except OSError: continue
        for n,line in enumerate(lines,1):
            for name,rx in patterns:
                if rx.search(line): found[name].append({"path":rel,"line":n,"text":line.strip()[:240]})
    return found
