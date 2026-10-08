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
    checks={"unwatched_optional_omitted":semantic_hash(projected)==V2_HASH,"watched_null_distinct":semantic_hash(nullv)!=V2_HASH,"watched_empty_distinct":semantic_hash(empty)!=V2_HASH,"null_vs_empty_distinct":semantic_hash(nullv)!=semantic_hash(empty),"unicode_nfc_equivalent":semantic_hash({"text":"\u00e9"})==semantic_hash({"text":"e\u0301"})}
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
    patterns=[
        ("direct_android_input",re.compile(r"\binput\s+(?:tap|swipe|text|keyevent)\b")),
        ("uiautomator_mutation",re.compile(r"\bdevice\.(?:click|swipe|pressBack|pressHome|longClick)\b")),
        ("legacy_ui_lease",re.compile(r"\bui_lease\s*\(")),
        ("instrumentation_dispatch",re.compile(r"\bam instrument\b")),
    ]
    found=inventory(patterns)
    tiktok=(REPO/"apps/tiktok/controller.py").read_text(encoding="utf-8")
    ui_job=(REPO/"automation/ui_job.py").read_text(encoding="utf-8")
    arbiter=(REPO/"automation/resource_arbiter.py").read_text(encoding="utf-8")
    publisher=(REPO/"publisher/controller.py").read_text(encoding="utf-8")
    publish_job=(REPO/"publisher/publish_job.py").read_text(encoding="utf-8")
    album=(REPO/"publisher/store_album_job.py").read_text(encoding="utf-8")
    checks={
        "canonical_lock_reused": 'RUNTIME / "android-ui.lock"' in arbiter,
        "canonical_claim_present": 'RUNTIME / "android-ui.claim.json"' in arbiter,
        "tiktok_uses_shared_arbiter": "resource_arbiter.acquire_android_ui" in tiktok,
        "tiktok_no_private_flock": "fcntl" not in tiktok and "UI_LEASE" not in tiktok,
        "tiktok_no_raw_android_input": not bool(re.search(r"\binput\s+(?:tap|swipe|text|keyevent)\b",tiktok)),
        "tiktok_mutation_uses_protocol_v2": '"protocol_version": 2 if mutating else 1' in tiktok,
        "tiktok_propagates_resource_guard": 'request["resource_guard"] = current_guard.as_dict()' in tiktok,
        "tiktok_propagates_state_guard": 'request["state_guard"] = {"mode": "AUTO"' in tiktok,
        "core_v1_mutation_blocked": "PROTOCOL_V2_REQUIRED_FOR_MUTATION" in ui_job,
        "legacy_publisher_mutation_boundary_disabled": "LEGACY_MUTATOR_DISABLED" in publisher and "OBSERVATION_ANDROIDCTL" in publisher,
        "publisher_unlock_uses_canonical_arbiter": "resource_arbiter.acquire_android_ui" in publish_job,
        "publisher_unlock_invalidates_state_tokens_before_raw_ui": ("state_integrity." + "bump_epoch") in publish_job and "SECURE_UNLOCK" in publish_job,
        "store_album_uses_canonical_arbiter": "resource_arbiter.acquire_android_ui" in album,
        "store_album_invalidates_state_tokens_before_legacy_ui": ("state_integrity." + "bump_epoch") in album,
    }
    ok=all(checks.values())
    reasons=[name for name,value in checks.items() if not value]
    return result("ui-mutation-inventory",ok,"SPRINT1_PRODUCTION",{
        "finding_count":sum(len(v) for v in found.values()),
        "production_boundary_checks":checks,
        "inventory":found,
        "classification":{
            "bridge_raw_input":"LOW_LEVEL_ADMIN_MAINTENANCE",
            "android_driver_mutation":"CORE_INTERNAL_EXPECTED",
            "publisher_secure_unlock_raw_ui":"LEGACY_PROTECTED_BY_CANONICAL_CLAIM_AND_EPOCH_INVALIDATION",
            "store_album_raw_ui":"LEGACY_PROTECTED_BY_CANONICAL_CLAIM_AND_EPOCH_INVALIDATION",
            "publisher_legacy_mutator":"RUNTIME_FAIL_CLOSED",
        },
    },reasons,phase="1")

def presshome_back():
    found=inventory([("pressHome",re.compile(r"\bpressHome\b")),("pressBack",re.compile(r"\bpressBack\b"))])
    ui_job=(REPO/"automation/ui_job.py").read_text(encoding="utf-8")
    core=(REPO/"automation/ui_core_v2.py").read_text(encoding="utf-8")
    tests=(REPO/"tests/test_rev36_ui_core_v2.py").read_text(encoding="utf-8")
    obs='OBSERVATION_ACTIONS = {"health", "observe", "screenshot", "find", "findAll", "assert", "waitFor", "waitStable"}'
    checks={
        "presshome_not_observation_safe": '"pressHome"' in ui_job and obs in ui_job,
        "pressback_not_observation_safe": '"pressBack"' in ui_job and obs in ui_job,
        "both_in_local_mutation_set": '"pressBack", "pressHome"' in ui_job,
        "core_requires_resource_guard": "resource_arbiter.assert_guard" in core,
        "core_prepares_before_dispatch": '"phase": "MUTATION_PREPARED"' in core,
        "core_commits_after_revision": "state_integrity.advance_revision()" in core and '"phase": "MUTATION_COMMITTED"' in core,
        "a31_regression_test_present": "test_a31_press_home_is_prepared_committed_and_increments_revision" in tests,
    }
    ok=all(checks.values()) and bool(found["pressHome"] and found["pressBack"])
    reasons=[name for name,value in checks.items() if not value]
    if not found["pressHome"] or not found["pressBack"]:
        reasons.append("CALLSITE_INVENTORY_INCOMPLETE")
    return result("presshome-back-migration",ok,"SPRINT1_PRODUCTION",{
        "required_contract":{"classification":"LOCAL_UI_MUTATION","protocol":"v2","resource_guard":"required","state_guard":"required"},
        "checks":checks,
        "call_sites":found,
    },reasons,phase="1")

def subjob_provenance():
    found=inventory([("ui_job",re.compile(r"(?:ui_job\.py|run_ui_job|run_workflow|_ui_job)")),("bridge",re.compile(r"(?:submit_root|root-exec\.sh|bridge_submit)"))]); total=sum(len(v) for v in found.values())
    return result("subjob-provenance",total>0,"SPRINT_GATED_FIXTURE",{"production_pass_expected_after":"Sprint 3 / TikTok migration","required_fields":["parent_capability_job_id","top_backend_job_id","resource_guard.claim_id"],"inventory":found},[] if total else ["NO_SUBJOB_BASELINE_FOUND"])

CHECKS={"semantic-vectors":semantic_vectors,"fingerprint-profiles":fingerprint_profiles,"catalog-overlay-policy":catalog_overlay_policy,"capability-readiness":readiness,"claim-session-reconcile":claim_session_reconcile,"ui-mutation-inventory":ui_mutation_inventory,"presshome-back-migration":presshome_back,"subjob-provenance":subjob_provenance}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("check",choices=sorted(CHECKS)); a=ap.parse_args()
    return emit(CHECKS[a.check]())
if __name__=="__main__": raise SystemExit(main())
