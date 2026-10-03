from __future__ import annotations

import unittest

from apps.tiktok import controller
from apps.tiktok.state import TIKTOK, detect_state


class TikTokGenericCoreTests(unittest.TestCase):
    def test_media_selector_is_unique_by_contract_not_index(self) -> None:
        selector = controller.media_selector()
        self.assertNotIn("index", selector)
        self.assertNotIn("order_by", selector)
        self.assertEqual(selector["class_name"], "android.widget.FrameLayout")
        self.assertTrue(selector["clickable"])
        self.assertEqual(
            selector["has_parent"],
            {"resource_id": f"{TIKTOK}:id/jc5"},
        )

    def test_dry_run_actions_never_click_publish_button(self) -> None:
        actions = controller.build_dry_run_actions("caption", "Y700Agent")
        publish = controller.RID["publish"]
        for action in actions:
            if action.get("action") != "click":
                continue
            self.assertNotEqual(
                (action.get("selector") or {}).get("resource_id"),
                publish,
                msg=f"DRY_RUN must never click final publish button: {action}",
            )

    def test_visibility_selection_separates_sheet_close_from_summary(self) -> None:
        actions = controller.build_dry_run_actions("caption", "Y700Agent")
        by_id = {a["action_id"]: a for a in actions}
        choose = by_id["choose-private"]
        self.assertEqual(
            choose["expect"]["absent_selector"],
            {
                "resource_id": controller.RID["visibility_heading"],
                "text": "谁可以看",
            },
        )
        wait = by_id["wait-private-summary"]
        self.assertEqual(wait["action"], "waitFor")
        self.assertEqual(wait["timeout_ms"], 15_000)
        self.assertEqual(
            wait["selector"]["content_desc_contains"],
            "自己",
        )

    def test_dry_run_has_no_commit_api(self) -> None:
        self.assertFalse(hasattr(controller, "tap_publish"))
        self.assertFalse(hasattr(controller, "commit"))
        self.assertFalse(hasattr(controller, "publish"))

    def test_public_dry_run_fails_closed_before_runtime(self) -> None:
        with self.assertRaisesRegex(controller.TikTokCoreError, "PRIVATE required"):
            controller.prepare_dry_run("caption", visibility="PUBLIC")

    def test_state_detector_prioritizes_post_config_over_home(self) -> None:
        elements = [
            {
                "resource_id": f"{TIKTOK}:id/o70",
                "content_desc": "创建",
                "text": "首页",
                "package": TIKTOK,
            },
            {
                "resource_id": f"{TIKTOK}:id/st6",
                "text": "发布",
                "package": TIKTOK,
            },
        ]
        state = detect_state(elements)
        self.assertEqual(state["state"], "POST_CONFIG")
        self.assertTrue(state["tiktok_visible"])

    def test_state_detector_prioritizes_visibility_overlay(self) -> None:
        elements = [
            {
                "resource_id": f"{TIKTOK}:id/st6",
                "text": "发布",
                "package": TIKTOK,
            },
            {
                "resource_id": f"{TIKTOK}:id/pcq",
                "text": "谁可以看",
                "package": TIKTOK,
            },
            {
                "resource_id": f"{TIKTOK}:id/doy",
                "text": "仅自己",
                "package": TIKTOK,
            },
        ]
        self.assertEqual(detect_state(elements)["state"], "VISIBILITY")

    def test_all_selector_keys_are_supported_by_generic_driver(self) -> None:
        supported = {
            "resource_id",
            "text",
            "text_contains",
            "content_desc",
            "content_desc_contains",
            "class_name",
            "package",
            "clickable",
            "enabled",
            "selected",
            "checked",
            "checkable",
            "scrollable",
            "has_descendant",
            "has_child",
            "has_parent",
            "has_ancestor",
        }

        def check_selector(selector: dict) -> None:
            self.assertTrue(selector)
            for key, value in selector.items():
                self.assertIn(key, supported)
                if key.startswith("has_"):
                    self.assertIsInstance(value, dict)
                    check_selector(value)

        actions = controller.build_dry_run_actions("caption", "Y700Agent")
        for action in actions:
            if isinstance(action.get("selector"), dict):
                check_selector(action["selector"])
            for contract in ("precondition", "expect"):
                obj = action.get(contract) or {}
                for key in ("selector", "absent_selector"):
                    if isinstance(obj.get(key), dict):
                        check_selector(obj[key])


if __name__ == "__main__":
    unittest.main()
