import importlib, json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

class CapabilityRuntimeTests(unittest.TestCase):
    def load(self,root):
        env={"Y700_ROOT":str(root),"Y700_RUNTIME":str(root/"runtime"),"Y700_CAPABILITY_JOBS":str(root/"capability-jobs")}
        with patch.dict(os.environ,env,clear=False):
            import capability.runtime as rt
            return importlib.reload(rt)
    def req(self,sid="submission-0001"):
        return {"submission_id":sid,"capability":"tiktok.publish","version":"1.0","payload":{"artifact_id":"a","caption":"x","visibility":"PUBLIC"},"expires_at":None,"requested_by":{"type":"agent","name":"test"}}
    def test_same_submission_converges_and_conflict_fails(self):
        with tempfile.TemporaryDirectory() as td:
            rt=self.load(Path(td)); a=rt.admit(self.req()); b=rt.admit(self.req())
            self.assertEqual(a["capability_job_id"],b["capability_job_id"]); self.assertFalse(a["existing"]); self.assertTrue(b["existing"])
            bad=self.req(); bad["payload"]={**bad["payload"],"caption":"changed"}
            with self.assertRaisesRegex(rt.CapabilityError,"SUBMISSION_ID_CONFLICT"): rt.admit(bad)
    def test_caller_cannot_weaken_policy(self):
        with tempfile.TemporaryDirectory() as td:
            rt=self.load(Path(td)); req=self.req(); req["replay"]="SAFE"
            with self.assertRaisesRegex(rt.CapabilityError,"POLICY_WEAKENING_NOT_ALLOWED"): rt.admit(req)
    def test_activated_contract_mutation_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            rt=self.load(Path(td)); out=rt.admit(self.req()); d=rt._job_dir(out["capability_job_id"])
            req=json.loads((d/"request.json").read_text()); req["payload"]["caption"]="tampered"; (d/"request.json").write_text(json.dumps(req))
            with self.assertRaisesRegex(rt.CapabilityError,"JOB_CONTRACT_VIOLATION"): rt.verify_contract(out["capability_job_id"])

if __name__=="__main__": unittest.main()
