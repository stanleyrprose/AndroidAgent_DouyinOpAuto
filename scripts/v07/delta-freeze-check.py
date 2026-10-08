#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.v07.delta_contracts import capability_axes,select_route,validate_frame,rollback_decision,stage_failure

def main():
    checks={}
    a=capability_axes(runtime_support=True,advertised=True,permission="APPROVAL_REQUIRED",readiness="READY")
    checks["D-G1"]=a["support_state"]=="SUPPORTED" and a["permission_state"]=="APPROVAL_REQUIRED" and a["readiness_state"]=="READY"
    drift=capability_axes(runtime_support=True,advertised=False,permission="DENIED",readiness="UNAVAILABLE")
    checks["D-G1"]=checks["D-G1"] and drift["support_state"]=="SUPPORTED_UNADVERTISED" and "CAPABILITY_CATALOG_DRIFT" in drift["reason_codes"]

    routes=[
      select_route(target_satisfied=True,semantic_available=False,visual_allowed=False,frame_fresh=False,host_primitive_allowed=False),
      select_route(target_satisfied=False,semantic_available=True,visual_allowed=True,frame_fresh=True,host_primitive_allowed=True),
      select_route(target_satisfied=False,semantic_available=False,visual_allowed=True,frame_fresh=True,host_primitive_allowed=False),
      select_route(target_satisfied=False,semantic_available=False,visual_allowed=True,frame_fresh=True,host_primitive_allowed=False,external_irreversible=True,visual_fallback_approved=False)
    ]
    checks["D-G2"]=routes==["VERIFIED_NOOP","SEMANTIC_UI","VISION_ASSISTED_UI","BLOCKED"]

    f={"frame_id":"frame-1","observed_boot_id":"b","captured_boottime_ms":1000,"state_epoch":"e","revision":7,"display_id":0,"rotation":0,"width":1600,"height":2560,"foreground":{"package":"p","activity":"a"},"max_age_ms":1200}
    cur={"observed_boot_id":"b","state_epoch":"e","revision":7,"display_id":0,"rotation":0,"width":1600,"height":2560,"foreground":{"package":"p","activity":"a"}}
    checks["D-G3"]=validate_frame(f,{"frame_id":"frame-1"},cur,1500)==(True,"PASS") and validate_frame(f,{"frame_id":"frame-1"},cur|{"revision":8},1500)==(False,"FRAME_REVISION_STALE") and validate_frame(f,{"frame_id":"frame-x"},cur,1500)==(False,"LOCATOR_FRAME_MISMATCH") and validate_frame(f,{"frame_id":"frame-1"},cur,2300)==(False,"FRAME_STALE")

    checks["D-G4"]=rollback_decision(patch_class="PATCH_SAFE",quiescent=True,postcheck_pass=False,candidate_mutation_seen=False,ambiguity=False)=="ROLLBACK_TO_LAST_KNOWN_GOOD" and rollback_decision(patch_class="PATCH_SAFE",quiescent=True,postcheck_pass=False,candidate_mutation_seen=True,ambiguity=False)=="ROLLBACK_NOT_SAFE"

    inj=[stage_failure("device_connectivity","DEVICE_DISCONNECTED"),stage_failure("frame_acquisition","FRAME_CAPTURE_UNAVAILABLE"),stage_failure("frame_freshness","FRAME_STALE"),stage_failure("target_localization","LOCATOR_AMBIGUOUS"),stage_failure("action_dispatch","ACTION_DISPATCH_FAILED"),stage_failure("postcondition","POSTCONDITION_FAILED"),stage_failure("business_verification","VERIFIER_INFRA_FAILURE")]
    checks["D-G5"]=len({(x["failure_stage"],x["reason_code"],x["last_success_stage"]) for x in inj})==len(inj)

    ok=all(checks.values())
    print(json.dumps({"status":"PASS" if ok else "FAIL","checks":checks},sort_keys=True))
    return 0 if ok else 1
if __name__=="__main__": raise SystemExit(main())
