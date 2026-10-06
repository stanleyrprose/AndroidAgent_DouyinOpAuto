#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re
from _common import *

def semantic_vectors():
    h1,h2=semantic_hash(V1),semantic_hash(V2)
    ok=h1==V1_HASH and h2==V2_HASH
    return result("semantic-vectors",ok,"P0B_PRE_IMPLEMENTATION",{"vector1":{"actual":h1,"expected":V1_HASH},"vector2":{"actual":h2,"expected":V2_HASH}},[] if ok else ["SEMANTIC_VECTOR_MISMATCH"])

def fingerprint_profiles():
    raw=json.loads(json.dumps(V2)); raw["element"]["text"]="noise"; raw["element"]["content_desc"]="noise"
    projected=json.loads(json.dumps(raw)); projected["element"].pop("text"); projected["element"].pop("content_desc")
    nullv=json.loads(json.dumps(V2)); nullv["element"]["text"]=None
    empty=json.loads(json.dumps(V2)); empty["element"]["text"]=""
    checks={"unwatched_optional_omitted":semantic_hash(projected)==V2_HASH,"watched_null_distinct":semantic_hash(nullv)!=V2_HASH,"watched_empty_distinct":semantic_hash(empty)!=V2_HASH,"null_vs_empty_distinct":semantic_hash(nullv)!=semantic_hash(empty)}
    for key,obj in (("arrays_rejected",{"x":[]}),("floats_rejected",{"x":1.5})):
        try: semantic_hash(obj); checks[key]=False
        except ValueError: checks[key]=True
    ok=all(checks.values())
    return result("fingerprint-profiles",ok,"P0B_PRE_IMPLEMENTATION_REFERENCE",checks,[] if ok else ["PROFILE_REFERENCE_FAILED"])

def catalog_overlay_policy():
    fixture=[{"name":"settings.toggle","mutating":True,"overlay_policy":{"top_level_guard":"REQUIRED","in_app_modal":"NONE_KNOWN","blocking_selectors":[]}},{"name":"tiktok.publish","mutating":True,"overlay_policy":{"top_level_guard":"REQUIRED","in_app_modal":"POSSIBLE","blocking_selectors":[{"text":"Confirm"}]}}]
    errors=[]
    for cap in fixture:
        op=cap["overlay_policy"]
        if cap["mutating"] and op.get("top_level_guard")!="REQUIRED": errors.append(cap["name"]+":TOP_LEVEL_GUARD")
        if op.get("in_app_modal")=="POSSIBLE" and not op.get("blocking_selectors"): errors.append(cap["name"]+":BLOCKING_SELECTORS")
    return result("catalog-overlay-policy",not errors,"SPRINT_GATED_FIXTURE",{"production_pass_expected_after":"Sprint 2","fixture":fixture},errors)

def readiness():
    fx=[{"reachable":True,"compatible":False,"readiness":"UNAVAILABLE"},{"reachable":True,"compatible":True,"readiness":"READY"},{"reachable":False,"compatible":True,"readiness":"UNAVAILABLE"}]
    ok=fx[0]["readiness"]!="READY" and fx[1]["readiness"]=="READY" and fx[2]["readiness"]!="READY"
    return result("capability-readiness",ok,"SPRINT_GATED_FIXTURE",{"invariant":"alive/reachable != READY != safe-to-mutate","fixture":fx},[] if ok else ["ALIVE_READY_INVARIANT_FAILED"])

def claim_session_reconcile():
    matrix=[("STOPPED","UNKNOWN",False),("MATCHING","LIVE",False),("UNREADABLE","UNKNOWN",False),("ZOMBIE","ABSENT_PROVEN",True),("DEAD","ABSENT_PROVEN",True)]
    ok=all(not release for p,b,release in matrix if p in {"STOPPED","MATCHING","UNREADABLE"})
    return result("claim-session-reconcile",ok,"SPRINT_GATED_FIXTURE",{"new_session_requires_new_claim_id":True,"stale_subjob_rejected":True,"proof_matrix":[{"process":p,"backend":b,"release":r} for p,b,r in matrix]},[] if ok else ["PROOF_MATRIX_INVALID"])

def ui_mutation_inventory():
    patterns=[("direct_android_input",re.compile(r"\binput\s+(?:tap|swipe|text|keyevent)\b")),("uiautomator_mutation",re.compile(r"\bdevice\.(?:click|swipe|pressBack|pressHome|longClick)\b")),("legacy_ui_lease",re.compile(r"\bui_lease\s*\(")),("instrumentation_dispatch",re.compile(r"\bam instrument\b"))]
    found=inventory(patterns); paths={x["path"] for rows in found.values() for x in rows}; missing=sorted({"apps/tiktok/controller.py","publisher/controller.py"}-paths); total=sum(len(v) for v in found.values())
    return result("ui-mutation-inventory",total>0 and not missing,"P0B_PRE_IMPLEMENTATION",{"finding_count":total,"legacy_bypass_elimination_required_in_sprint1":True,"findings":found},["MISSING_EXPECTED_MUTATOR:"+x for x in missing])

def presshome_back():
    found=inventory([("pressHome",re.compile(r"\bpressHome\b")),("pressBack",re.compile(r"\bpressBack\b"))]); ok=bool(found["pressHome"] and found["pressBack"])
    return result("presshome-back-migration",ok,"SPRINT_GATED_FIXTURE",{"production_pass_expected_after":"Sprint 1","required_contract":{"classification":"LOCAL_UI_MUTATION","protocol":"v2","resource_guard":"required"},"call_sites":found},[] if ok else ["CALLSITE_INVENTORY_INCOMPLETE"])

def subjob_provenance():
    found=inventory([("ui_job",re.compile(r"(?:ui_job\.py|run_ui_job|run_workflow|_ui_job)")),("bridge",re.compile(r"(?:submit_root|root-exec\.sh|bridge_submit)"))]); total=sum(len(v) for v in found.values())
    return result("subjob-provenance",total>0,"SPRINT_GATED_FIXTURE",{"production_pass_expected_after":"Sprint 3 / TikTok migration","required_fields":["parent_capability_job_id","top_backend_job_id","resource_guard.claim_id"],"inventory":found},[] if total else ["NO_SUBJOB_BASELINE_FOUND"])

CHECKS={"semantic-vectors":semantic_vectors,"fingerprint-profiles":fingerprint_profiles,"catalog-overlay-policy":catalog_overlay_policy,"capability-readiness":readiness,"claim-session-reconcile":claim_session_reconcile,"ui-mutation-inventory":ui_mutation_inventory,"presshome-back-migration":presshome_back,"subjob-provenance":subjob_provenance}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("check",choices=sorted(CHECKS)); a=ap.parse_args()
    return emit(CHECKS[a.check]())
if __name__=="__main__": raise SystemExit(main())
