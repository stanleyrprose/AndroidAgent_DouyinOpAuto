"""Read-only Linux authority probe must not initialize/repair/mutate SOT."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import unittest

SRC = Path(__file__).resolve().parents[1] / "scripts/v07/probe-state-sot-readonly.py"
SPEC = importlib.util.spec_from_file_location("rev37_sot_probe", SRC)
assert SPEC and SPEC.loader
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)

STATE = {
    "state_version": 1,
    "state_epoch": "epoch-" + "a" * 32,
    "revision": 3,
    "fingerprint_version": "semantic-v1",
}
BOOT = "c6a09018-f3d5-432c-b07f-a415752e9c37"


class StateSotReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.sot = self.dir / "state.json"
        self.boot = self.dir / "boot.txt"
        self.boot.write_text(BOOT + "\n", encoding="ascii")
        self.set_state(STATE)

    def set_state(self, value, *, raw=None):
        self.sot.write_text(
            json.dumps(value) if raw is None else raw, encoding="utf-8")
        self.sot.chmod(0o600)

    def run_probe(self, path=None):
        return P.probe(path or self.sot, enforce_root_owner=False,
                       boot_path=self.boot, fixture_clock=time.monotonic_ns)

    def test_valid_sot_is_consistent_and_never_authorizes(self):
        before = self.sot.read_bytes()
        initial = self.sot.stat()
        verdict = self.run_probe()
        after = self.sot.stat()
        self.assertEqual(verdict["status"], "READ_ONLY_SOT_CONSISTENT")
        self.assertTrue(verdict["source_permissions_verified"])
        self.assertEqual(verdict["revision"], 3)
        self.assertIsInstance(verdict["observed_boottime_ms"], int)
        self.assertEqual(len(verdict["boot_digest_prefix"]), 12)
        self.assertEqual(verdict["dg3_status"], "OPEN")
        self.assertFalse(verdict["production_dispatch_authorized"])
        self.assertFalse(verdict["state_mutated"])
        self.assertEqual(verdict["action_attempts"], 0)
        self.assertNotIn(STATE["state_epoch"], json.dumps(verdict))
        self.assertNotIn(BOOT, json.dumps(verdict))
        self.assertEqual(before, self.sot.read_bytes())
        self.assertEqual(initial.st_mtime_ns, after.st_mtime_ns)
        self.assertEqual(initial.st_ino, after.st_ino)

    def test_nonexistent_file_is_not_created(self):
        gone = self.dir / "missing.json"
        self.assertEqual(self.run_probe(gone)["status"], "BLOCKED")
        self.assertFalse(gone.exists())

    def test_symlink_refused(self):
        alias = self.dir / "alias"
        alias.symlink_to(self.sot)
        self.assertEqual(self.run_probe(alias)["status"], "BLOCKED")

    def test_wrong_permissions_refused(self):
        self.sot.chmod(0o644)
        value = self.run_probe()
        self.assertEqual(value["status"], "BLOCKED")
        self.assertEqual(value["reason"], "SOT_PERMISSIONS_INVALID")

    def test_wrong_owner_is_refused_in_strict_mode(self):
        if os.geteuid() == 0:
            self.skipTest("unit runner is root; cannot synthesize nonroot ownership")
        self.assertEqual(P.probe(self.sot, boot_path=self.boot,
                                 fixture_clock=time.monotonic_ns)["status"],
                         "BLOCKED")

    def test_invalid_state_schema_or_fingerprint_refused(self):
        for patch in ({"revision": -1}, {"revision": True},
                      {"state_epoch": "epoch-invalid"},
                      {"fingerprint_version": "semantic-v0"},
                      {"state_version": 2}):
            with self.subTest(patch=patch):
                self.set_state({**STATE, **patch})
                self.assertEqual(self.run_probe()["status"], "BLOCKED")

    def test_malformed_json_refused_and_never_repaired(self):
        self.set_state(STATE, raw='{"state_version":1,invalid}')
        original = self.sot.read_bytes()
        self.assertEqual(self.run_probe()["status"], "BLOCKED")
        self.assertEqual(self.sot.read_bytes(), original)

    def test_duplicate_json_key_refused(self):
        value = '{"state_version":1,"state_version":1,"state_epoch":"epoch-' + 'a' * 32 + '","revision":3,"fingerprint_version":"semantic-v1"}'
        self.set_state(STATE, raw=value)
        self.assertEqual(self.run_probe()["reason"], "SOT_DUPLICATE_KEY")

    def test_nonregular_and_large_file_fail_closed(self):
        self.assertEqual(self.run_probe(self.dir)["status"], "BLOCKED")
        self.set_state(STATE, raw="0" * (P.MAX_SIZE + 1))
        self.assertEqual(self.run_probe()["status"], "BLOCKED")

    def test_invalid_boot_id_refused(self):
        self.boot.write_text("unknown\n", encoding="ascii")
        self.assertEqual(self.run_probe()["status"], "BLOCKED")

    def test_source_import_must_not_bootstrap(self):
        script = SRC.read_text(encoding="utf-8")
        self.assertNotIn("load_state(", script.split("def probe(")[1])
        self.assertNotIn("os.replace(", script)
        self.assertNotIn("mkdir(", script)
        self.assertNotIn("chmod(", script)
        self.assertNotIn("production_dispatch_authorized\": True", script)


if __name__ == "__main__":
    unittest.main()
