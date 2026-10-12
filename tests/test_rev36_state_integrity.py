import importlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


V1 = {
    "fingerprint_version": "semantic-v1",
    "foreground": {
        "activity": "com.android.settings.Settings",
        "package": "com.android.settings",
    },
    "scope": "FOREGROUND",
    "screen": {
        "blocking_overlay_class": None,
        "blocking_overlay_owner_package": None,
        "blocking_overlay_present": False,
        "interactive": True,
        "keyguard_locked": False,
    },
}
V1_HASH = "sha256:074e74b0f725954b789fea7d905715c7e096c4ab159029a1c6c8ef8a6b610b66"

V2 = {
    "cardinality": 1,
    "element": {
        "checked": True,
        "clickable": True,
        "enabled": True,
        "selected": False,
    },
    "fingerprint_version": "semantic-v1",
    "foreground": {
        "activity": "com.android.settings.Settings",
        "package": "com.android.settings",
    },
    "scope": "ELEMENT",
    "screen": {
        "blocking_overlay_class": None,
        "blocking_overlay_owner_package": None,
        "blocking_overlay_present": False,
        "interactive": True,
        "keyguard_locked": False,
    },
    "selector": {"resource_id": "android:id/switch_widget"},
}
V2_HASH = "sha256:6bab7e2cd22bb7e2804f75638edfda2546f73802003c57fde3ecbdd322f32fd4"


class StateIntegritySprint1Tests(unittest.TestCase):
    def load(self, root: Path):
        env = {
            "Y700_RUNTIME": str(root),
            "Y700_UI_STATE_DIR": str(root / "ui-state"),
        }
        with patch.dict(os.environ, env, clear=False):
            import automation.state_integrity as si
            return importlib.reload(si)

    def test_frozen_semantic_vectors(self):
        with tempfile.TemporaryDirectory() as td:
            si = self.load(Path(td))
            self.assertEqual(si.semantic_hash(V1), V1_HASH)
            self.assertEqual(si.semantic_hash(V2), V2_HASH)
            self.assertEqual(
                si.semantic_hash({"text": "\u00e9"}),
                si.semantic_hash({"text": "e\u0301"}),
            )
            with self.assertRaises(ValueError):
                si.semantic_hash({"bad": []})
            with self.assertRaises(ValueError):
                si.semantic_hash({"bad": 1.5})
            self.assertEqual(
                si.semantic_hash({"\u00e9": "value"}),
                si.semantic_hash({"e\u0301": "value"}),
            )
            with self.assertRaisesRegex(ValueError, "duplicate key after NFC"):
                si.semantic_hash({"\u00e9": 1, "e\u0301": 2})

    def test_device_state_path_permissions_and_revision(self):
        with tempfile.TemporaryDirectory() as td:
            si = self.load(Path(td))
            s0 = si.load_state()
            self.assertEqual(s0["revision"], 0)
            self.assertTrue(str(si.STATE_PATH).endswith("/ui-state/device-state.json"))
            self.assertEqual(stat.S_IMODE(si.STATE_DIR.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(si.STATE_PATH.stat().st_mode), 0o600)
            before, after = si.advance_revision()
            self.assertEqual((before, after), (0, 1))
            self.assertEqual(si.load_state()["revision"], 1)

    def test_token_revision_hash_profile_boot_and_age_guards(self):
        with tempfile.TemporaryDirectory() as td:
            si = self.load(Path(td))
            token = si.issue_token(
                V1,
                fingerprint_profile_id="semantic-v1.foreground-base.v1",
                boot_id="boot-1",
                boottime_ms=1000,
                max_age_ms=1000,
            )
            si.assert_token(
                token,
                V1,
                expected_profile_id="semantic-v1.foreground-base.v1",
                boot_id="boot-1",
                boottime_ms=1500,
            )
            with self.assertRaisesRegex(si.StateIntegrityError, "STALE_STATE_HASH"):
                si.assert_token(
                    token,
                    V1 | {"foreground": {"package": "x", "activity": "y"}},
                    expected_profile_id="semantic-v1.foreground-base.v1",
                    boot_id="boot-1",
                    boottime_ms=1500,
                )
            with self.assertRaisesRegex(si.StateIntegrityError, "STATE_TOKEN_PROFILE_MISMATCH"):
                si.assert_token(
                    token,
                    V1,
                    expected_profile_id="generic.element-base.v1",
                    boot_id="boot-1",
                    boottime_ms=1500,
                )
            with self.assertRaisesRegex(si.StateIntegrityError, "STATE_TOKEN_BOOT_MISMATCH"):
                si.assert_token(
                    token,
                    V1,
                    expected_profile_id="semantic-v1.foreground-base.v1",
                    boot_id="boot-2",
                    boottime_ms=1500,
                )
            with self.assertRaisesRegex(si.StateIntegrityError, "STATE_TOKEN_EXPIRED"):
                si.assert_token(
                    token,
                    V1,
                    expected_profile_id="semantic-v1.foreground-base.v1",
                    boot_id="boot-1",
                    boottime_ms=2501,
                )
            si.advance_revision()
            with self.assertRaisesRegex(si.StateIntegrityError, "STALE_STATE_REVISION"):
                si.assert_token(
                    token,
                    V1,
                    expected_profile_id="semantic-v1.foreground-base.v1",
                    boot_id="boot-1",
                    boottime_ms=1500,
                )

    def test_epoch_invalidation(self):
        with tempfile.TemporaryDirectory() as td:
            si = self.load(Path(td))
            token = si.issue_token(
                V1,
                fingerprint_profile_id="semantic-v1.foreground-base.v1",
                boot_id="boot",
                boottime_ms=100,
            )
            old_epoch = token["state_epoch"]
            fresh = si.bump_epoch("ADMIN_MUTATION")
            self.assertNotEqual(fresh["state_epoch"], old_epoch)
            with self.assertRaisesRegex(si.StateIntegrityError, "STALE_STATE_EPOCH"):
                si.assert_token(
                    token,
                    V1,
                    expected_profile_id="semantic-v1.foreground-base.v1",
                    boot_id="boot",
                    boottime_ms=101,
                )

    def test_projection_detects_manual_element_drift_and_overlay(self):
        with tempfile.TemporaryDirectory() as td:
            si = self.load(Path(td))
            obs = {
                "package": "com.android.settings",
                "elements": [{
                    "node_id": "n1",
                    "parent_id": None,
                    "resource_id": "android:id/switch_widget",
                    "class": "android.widget.Switch",
                    "package": "com.android.settings",
                    "clickable": True,
                    "enabled": True,
                    "selected": False,
                    "checked": True,
                }],
            }
            action = {
                "action": "click",
                "selector": {"resource_id": "android:id/switch_widget"},
                "fingerprint_profile_id": "settings.switch.element-base.v1",
            }
            snap, profile = si.project_snapshot(
                obs,
                interactive=True,
                keyguard_locked=False,
                activity="com.android.settings.Settings",
                blocking_overlay_present=False,
                blocking_overlay_owner_package=None,
                blocking_overlay_class=None,
                action=action,
            )
            token = si.issue_token(
                snap,
                fingerprint_profile_id=profile,
                boot_id="b",
                boottime_ms=1,
            )
            changed = json.loads(json.dumps(obs))
            changed["elements"][0]["checked"] = False
            snap2, _ = si.project_snapshot(
                changed,
                interactive=True,
                keyguard_locked=False,
                activity="com.android.settings.Settings",
                blocking_overlay_present=False,
                blocking_overlay_owner_package=None,
                blocking_overlay_class=None,
                action=action,
            )
            with self.assertRaisesRegex(si.StateIntegrityError, "STALE_STATE_HASH"):
                si.assert_token(
                    token,
                    snap2,
                    expected_profile_id=profile,
                    boot_id="b",
                    boottime_ms=2,
                )
            with self.assertRaisesRegex(si.StateIntegrityError, "UNEXPECTED_BLOCKING_OVERLAY"):
                si.project_snapshot(
                    obs,
                    interactive=True,
                    keyguard_locked=False,
                    activity="com.android.settings.Settings",
                    blocking_overlay_present=True,
                    blocking_overlay_owner_package="com.android.permissioncontroller",
                    blocking_overlay_class="android.app.Dialog",
                    action=action,
                )


class AuthorityLossRegressionTests(unittest.TestCase):
    load = StateIntegritySprint1Tests.load

    def test_missing_canonical_state_after_initialization_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            si = self.load(Path(td))
            si.load_state()
            self.assertTrue(si.STATE_INITIALIZED_MARKER.exists())
            si.STATE_PATH.unlink()
            with self.assertRaisesRegex(si.StateIntegrityError, "canonical state missing"):
                si.load_state()
            self.assertFalse(si.STATE_PATH.exists())

    def test_missing_state_with_marker_never_bootstraps_new_epoch(self):
        with tempfile.TemporaryDirectory() as td:
            si = self.load(Path(td))
            si._ensure_dir()
            si._install_initialization_marker()
            with self.assertRaisesRegex(si.StateIntegrityError, "canonical state missing"):
                si.load_state()
            self.assertFalse(si.STATE_PATH.exists())

class MarkerTrustRegressionTests(unittest.TestCase):
    load = StateIntegritySprint1Tests.load

    def test_untrusted_marker_is_not_treated_as_absent(self):
        with tempfile.TemporaryDirectory() as td:
            si = self.load(Path(td))
            si._ensure_dir()
            si.STATE_INITIALIZED_MARKER.write_bytes(b"wrong")
            with self.assertRaisesRegex(si.StateIntegrityError, "marker untrusted"):
                si.load_state()
            self.assertFalse(si.STATE_PATH.exists())

    def test_symlinked_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            si = self.load(Path(td))
            si._ensure_dir()
            victim = si.STATE_DIR / "victim"
            victim.write_bytes(b"initialized\n")
            si.STATE_INITIALIZED_MARKER.symlink_to(victim)
            with self.assertRaises((si.StateIntegrityError, OSError)):
                si.load_state()
            self.assertFalse(si.STATE_PATH.exists())

class LegacyMarkerMigrationTests(unittest.TestCase):
    load = StateIntegritySprint1Tests.load

    def test_existing_valid_authority_backfills_marker_without_epoch_reset(self):
        with tempfile.TemporaryDirectory() as td:
            si = self.load(Path(td))
            state = si.load_state()
            si.STATE_INITIALIZED_MARKER.unlink()
            loaded = si.load_state()
            self.assertEqual(loaded["state_epoch"], state["state_epoch"])
            self.assertEqual(loaded["revision"], state["revision"])
            self.assertTrue(si._marker_present())

    def test_corrupt_existing_authority_does_not_backfill_marker(self):
        with tempfile.TemporaryDirectory() as td:
            si = self.load(Path(td))
            si.load_state()
            si.STATE_INITIALIZED_MARKER.unlink()
            si.STATE_PATH.write_bytes(b"not-json")
            with self.assertRaises((si.StateIntegrityError, ValueError)):
                si.load_state()
            self.assertFalse(si.STATE_INITIALIZED_MARKER.exists())

class AuthorityReadContinuityTests(unittest.TestCase):
    load = StateIntegritySprint1Tests.load

    def test_concurrent_revision_change_during_read_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            si = self.load(Path(td))
            si.load_state()
            original = si._read_existing_state
            calls = [0]

            def changed_on_second_read():
                state = original()
                calls[0] += 1
                if calls[0] == 2:
                    return {**state, "revision": state["revision"] + 1}
                return state

            with patch.object(si, "_read_existing_state", side_effect=changed_on_second_read):
                with self.assertRaisesRegex(si.StateIntegrityError, "concurrent state transition"):
                    si.load_state()

    def test_existing_authority_marker_is_stable_across_reads(self):
        with tempfile.TemporaryDirectory() as td:
            si = self.load(Path(td))
            first = si.load_state()
            second = si.load_state()
            self.assertEqual(first["state_epoch"], second["state_epoch"])
            self.assertEqual(first["revision"], second["revision"])


if __name__ == "__main__":
    unittest.main()
