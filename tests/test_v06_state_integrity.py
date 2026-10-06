import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

class StateIntegrityTests(unittest.TestCase):
    def load_si(self, root):
        with patch.dict(os.environ, {"Y700_RUNTIME": str(root)}, clear=False):
            os.environ.pop("Y700_STATE_INTEGRITY_DIR", None)
            import automation.state_integrity as si
            return importlib.reload(si)

    def test_semantic_hash_ignores_dynamic_noise(self):
        with tempfile.TemporaryDirectory() as td:
            si=self.load_si(Path(td))
            base={"package":"p","activity":"A","elements":[{"resource_id":"x","text":"ok","checked":False}]}
            noisy={**base,"clock":"12:01","battery":42,"elements":[{**base["elements"][0],"bounds":"[1,2][3,4]"}]}
            self.assertEqual(si.semantic_hash(base),si.semantic_hash(noisy))
            changed={**base,"elements":[{**base["elements"][0],"checked":True}]}
            self.assertNotEqual(si.semantic_hash(base),si.semantic_hash(changed))

    def test_revision_hash_epoch_and_boot_staleness(self):
        with tempfile.TemporaryDirectory() as td:
            si=self.load_si(Path(td)); obs={"package":"p","activity":"A","elements":[]}
            token=si.issue_token(obs,boot_id="boot-1")
            si.prepare_mutation(mutation_id="m1",action="pressBack",claim_id="c1")
            si.commit_mutation(mutation_id="m1",action="pressBack",claim_id="c1",post_hash=si.semantic_hash(obs))
            with self.assertRaisesRegex(si.StateIntegrityError,"STALE_STATE_REVISION"): si.assert_token(token,obs,boot_id="boot-1")
            fresh=si.issue_token(obs,boot_id="boot-1")
            with self.assertRaisesRegex(si.StateIntegrityError,"STALE_STATE_HASH"): si.assert_token(fresh,{**obs,"activity":"B"},boot_id="boot-1")
            si.bump_epoch("ADMIN_MUTATION")
            with self.assertRaisesRegex(si.StateIntegrityError,"STALE_STATE_EPOCH"): si.assert_token(fresh,obs,boot_id="boot-1")
            latest=si.issue_token(obs,boot_id="boot-1")
            with self.assertRaisesRegex(si.StateIntegrityError,"STALE_STATE_EPOCH"): si.assert_token(latest,obs,boot_id="boot-2")

if __name__=="__main__": unittest.main()
