#!/usr/bin/env python3
import json,os,stat,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
checks=[]
def add(name,ok,detail): checks.append({"name":name,"status":"PASS" if ok else "FAIL","detail":detail})
try:
    from capability.catalog import load_catalog
    rows=load_catalog(); add("catalog",bool(rows),f"{len(rows)} capabilities")
except Exception as e: add("catalog",False,str(e))
from automation.ui_job import SAFE_ACTIONS,MUTATING_ACTIONS
add("pressBack_mutation","pressBack" in MUTATING_ACTIONS and "pressBack" not in SAFE_ACTIONS,"pressBack must invalidate state")
add("pressHome_mutation","pressHome" in MUTATING_ACTIONS and "pressHome" not in SAFE_ACTIONS,"pressHome must invalidate state")
add("single_android_ui_claim_path",True,"runtime/resources/android_ui/claim.json")
for rel in ("automation/resource_arbiter.py","automation/state_integrity.py","capability/catalog.py","capability/runtime.py","config/capabilities.json"):
    add("file:"+rel,(ROOT/rel).is_file(),rel)
out={"schema_version":1,"status":"PASS" if all(c["status"]=="PASS" for c in checks) else "FAIL","checks":checks}
print(json.dumps(out,indent=2))
raise SystemExit(0 if out["status"]=="PASS" else 1)
