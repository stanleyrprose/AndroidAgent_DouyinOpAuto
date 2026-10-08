from __future__ import annotations
import unittest
from scripts.v07.delta_contracts import capability_axes, select_route, validate_frame, rollback_decision, stage_failure

class Rev37DeltaFreezeTests(unittest.TestCase):
    def test_a89_capability_is_not_permission(self):
        x=capability_axes(runtime_support=True,advertised=True,permission="APPROVAL_REQUIRED",readiness="READY")
        self.assertEqual((x["support_state"],x["permission_state"],x["readiness_state"]),("SUPPORTED","APPROVAL_REQUIRED","READY"))
        d=capability_axes(runtime_support=True,advertised=False,permission="DENIED",readiness="UNAVAILABLE")
        self.assertEqual(d["support_state"],"SUPPORTED_UNADVERTISED")
        self.assertIn("CAPABILITY_CATALOG_DRIFT",d["reason_codes"])

    def test_a90_conditional_dispatch(self):
        self.assertEqual(select_route(target_satisfied=True,semantic_available=False,visual_allowed=False,frame_fresh=False,host_primitive_allowed=False),"VERIFIED_NOOP")
        self.assertEqual(select_route(target_satisfied=False,semantic_available=True,visual_allowed=True,frame_fresh=True,host_primitive_allowed=True),"SEMANTIC_UI")
        self.assertEqual(select_route(target_satisfied=False,semantic_available=False,visual_allowed=True,frame_fresh=True,host_primitive_allowed=False),"VISION_ASSISTED_UI")
        self.assertEqual(select_route(target_satisfied=False,semantic_available=False,visual_allowed=True,frame_fresh=True,host_primitive_allowed=False,external_irreversible=True,visual_fallback_approved=False),"BLOCKED")

    def test_a91_stale_frame_zero_attempt_contract(self):
        f={"frame_id":"frame-1","observed_boot_id":"boot","captured_boottime_ms":1000,"state_epoch":"epoch","revision":2,"display_id":0,"rotation":0,"width":1600,"height":2560,"foreground":{"package":"p","activity":"a"},"max_age_ms":1200}
        c={"observed_boot_id":"boot","state_epoch":"epoch","revision":2,"display_id":0,"rotation":0,"width":1600,"height":2560,"foreground":{"package":"p","activity":"a"}}
        self.assertEqual(validate_frame(f,{"frame_id":"frame-1"},c,1500),(True,"PASS"))
        for mutated,code in [
          (c|{"revision":3},"FRAME_REVISION_STALE"),
          (c|{"rotation":1},"FRAME_ROTATION_CHANGED"),
          (c|{"width":1200},"FRAME_DISPLAY_CHANGED"),
          (c|{"foreground":{"package":"q","activity":"b"}},"FRAME_FOREGROUND_DRIFT")
        ]:
            self.assertEqual(validate_frame(f,{"frame_id":"frame-1"},mutated,1500),(False,code))
        self.assertEqual(validate_frame(f,{"frame_id":"other"},c,1500),(False,"LOCATOR_FRAME_MISMATCH"))
        self.assertEqual(validate_frame(f,{"frame_id":"frame-1"},c,2300),(False,"FRAME_STALE"))

    def test_a92_patch_rollback_contract(self):
        self.assertEqual(rollback_decision(patch_class="PATCH_SAFE",quiescent=True,postcheck_pass=False,candidate_mutation_seen=False,ambiguity=False),"ROLLBACK_TO_LAST_KNOWN_GOOD")
        self.assertEqual(rollback_decision(patch_class="PATCH_SAFE",quiescent=True,postcheck_pass=False,candidate_mutation_seen=True,ambiguity=False),"ROLLBACK_NOT_SAFE")
        self.assertEqual(rollback_decision(patch_class="QUIESCENT_MIGRATION",quiescent=True,postcheck_pass=True,candidate_mutation_seen=False,ambiguity=False),"MANUAL_ONLY")

    def test_a93_stage_health_attribution(self):
        cases=[("device_connectivity","DEVICE_DISCONNECTED"),("frame_acquisition","FRAME_CAPTURE_UNAVAILABLE"),("frame_freshness","FRAME_STALE"),("target_localization","LOCATOR_AMBIGUOUS"),("action_dispatch","ACTION_DISPATCH_FAILED"),("postcondition","POSTCONDITION_FAILED"),("business_verification","VERIFIER_INFRA_FAILURE")]
        rows=[stage_failure(a,b) for a,b in cases]
        self.assertEqual(len({(r["failure_stage"],r["reason_code"],r["last_success_stage"]) for r in rows}),len(rows))

if __name__=="__main__": unittest.main()
