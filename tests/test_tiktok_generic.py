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
            {"class_name": "android.widget.GridView"},
        )

    def test_dry_run_home_create_uses_semantic_selector_not_resource_id(self) -> None:
        actions = controller.build_dry_run_actions("caption", "Y700Agent")
        by_id = {a["action_id"]: a for a in actions}
        expected = {"content_desc": "创建", "clickable": True}
        self.assertEqual(by_id["wait-cold-home"]["selector"], expected)
        self.assertEqual(by_id["home-create"]["selector"], expected)
        self.assertNotIn("resource_id", by_id["wait-cold-home"]["selector"])

    def test_dry_run_waits_for_home_stability_before_create_click(self) -> None:
        actions = controller.build_dry_run_actions("caption", "Y700Agent")
        ids = [a["action_id"] for a in actions]
        self.assertLess(ids.index("wait-home-stable"), ids.index("home-create"))
        by_id = {a["action_id"]: a for a in actions}
        self.assertEqual(by_id["wait-home-stable"]["action"], "waitStable")
        self.assertEqual(by_id["wait-home-stable"]["stable_interval_ms"], 800)

    def test_album_menu_uses_semantic_selector_not_obfuscated_resource_id(self) -> None:
        actions = controller.build_dry_run_actions("caption", "Y700Agent")
        by_id = {a["action_id"]: a for a in actions}
        selector = by_id["album-menu"]["selector"]
        self.assertEqual(selector["class_name"], "android.widget.LinearLayout")
        self.assertTrue(selector["clickable"])
        self.assertEqual(selector["has_descendant"], {"text": "最近项目"})
        self.assertNotIn("resource_id", selector)

    def test_album_row_uses_exact_text_without_obfuscated_resource_id(self) -> None:
        actions = controller.build_dry_run_actions("caption", "Y700Agent")
        by_id = {a["action_id"]: a for a in actions}
        expected = {
            "class_name": "android.widget.RelativeLayout",
            "clickable": True,
            "has_descendant": {"text": "Y700Agent"},
        }
        self.assertEqual(by_id["wait-album-entry"]["selector"], expected)
        self.assertEqual(by_id["select-album"]["selector"], expected)
        self.assertNotIn("resource_id", expected["has_descendant"])

    def test_edit_next_uses_semantic_selector_not_obfuscated_resource_id(self) -> None:
        actions = controller.build_dry_run_actions("caption", "Y700Agent")
        by_id = {a["action_id"]: a for a in actions}
        expected = {
            "class_name": "android.widget.LinearLayout",
            "clickable": True,
            "has_descendant": {"text": "下一步"},
        }
        self.assertEqual(by_id["wait-edit"]["selector"], expected)
        self.assertEqual(by_id["next-to-post-config"]["selector"], expected)
        self.assertEqual(by_id["next-to-post-config"]["precondition"]["selector"], expected)
        self.assertNotIn("resource_id", expected)

    def test_dry_run_actions_never_click_publish_button(self) -> None:
        actions = controller.build_dry_run_actions("caption", "Y700Agent")
        publish = controller.publish_button_selector()
        for action in actions:
            if action.get("action") != "click":
                continue
            self.assertNotEqual(
                action.get("selector"),
                publish,
                msg=f"DRY_RUN must never click final publish button: {action}",
            )

    def test_post_config_controls_use_semantic_selectors(self) -> None:
        actions = controller.build_dry_run_actions("caption", "Y700Agent")
        by_id = {a["action_id"]: a for a in actions}
        publish = {
            "class_name": "android.widget.Button",
            "text": "发布",
            "clickable": True,
            "enabled": True,
        }
        caption = {
            "class_name": "android.widget.EditText",
            "clickable": True,
        }
        self.assertEqual(by_id["next-to-post-config"]["expect"]["selector"], publish)
        self.assertEqual(by_id["wait-caption"]["selector"], caption)
        self.assertEqual(by_id["caption"]["selector"], caption)
        self.assertEqual(by_id["caption"]["precondition"]["selector"], publish)
        self.assertEqual(by_id["assert-publish-ready"]["selector"], publish)

    def test_visibility_summary_uses_semantic_selector(self) -> None:
        actions = controller.build_dry_run_actions("caption", "Y700Agent")
        by_id = {a["action_id"]: a for a in actions}
        expected = {
            "class_name": "android.widget.Button",
            "content_desc": "所有人可见",
            "clickable": True,
        }
        self.assertEqual(by_id["open-visibility"]["selector"], expected)
        self.assertEqual(by_id["wait-public-summary"]["selector"], expected)
        self.assertEqual(by_id["assert-public"]["selector"], expected)
        self.assertEqual(by_id["open-visibility"]["expect"]["selector"], {"text": "谁可以看"})

    def test_visibility_selection_separates_sheet_close_from_summary(self) -> None:
        actions = controller.build_dry_run_actions("caption", "Y700Agent")
        by_id = {a["action_id"]: a for a in actions}
        choose = by_id["choose-public"]
        self.assertEqual(
            choose["expect"]["absent_selector"],
            {
                "resource_id": controller.RID["visibility_heading"],
                "text": "谁可以看",
            },
        )
        wait = by_id["wait-public-summary"]
        self.assertEqual(wait["action"], "waitFor")
        self.assertEqual(wait["timeout_ms"], 15_000)
        self.assertEqual(
            wait["selector"]["content_desc_contains"],
            "所有人",
        )

    def test_commit_api_is_explicit_but_not_legacy_named(self) -> None:
        self.assertFalse(hasattr(controller, "tap_publish"))
        self.assertFalse(hasattr(controller, "publish"))
        self.assertTrue(callable(controller.commit_public))
        with self.assertRaisesRegex(controller.TikTokCoreError, "before_irreversible"):
            controller.commit_public("caption")

    def test_commit_actions_have_exactly_one_irreversible_publish_click(self) -> None:
        actions = controller.build_commit_actions("caption")
        publish = controller.publish_button_selector()
        clicks = [
            a for a in actions
            if a.get("action") == "click"
            and a.get("selector") == publish
        ]
        self.assertEqual(len(clicks), 1)
        self.assertEqual(clicks[0]["action_id"], "commit-publish")
        self.assertEqual(clicks[0]["side_effect"], "EXTERNAL_IRREVERSIBLE")
        self.assertEqual(actions[-1], clicks[0])

    def test_private_post_match_requires_exact_caption_and_private_label(self) -> None:
        caption = "Y700 test"
        elements = [
            {
                "resource_id": controller.RID["post_caption"],
                "text": caption,
            },
            {
                "resource_id": controller.RID["private_label"],
                "text": "私密",
            },
        ]
        self.assertTrue(controller._private_post_matches(elements, caption))
        self.assertFalse(controller._private_post_matches(elements, "other"))
        self.assertFalse(
            controller._private_post_matches(
                [elements[0]],
                caption,
            )
        )

    def test_public_post_match_requires_exact_caption_and_no_restricted_label(self) -> None:
        caption = "Y700 public test"
        public = [{"resource_id": controller.RID["post_caption"], "text": caption}]
        self.assertTrue(controller._public_post_matches(public, caption))
        self.assertFalse(controller._public_post_matches(public, "other"))
        restricted = public + [
            {"resource_id": controller.RID["private_label"], "text": "私密"}
        ]
        self.assertFalse(controller._public_post_matches(restricted, caption))

    def test_private_tile_bounds_are_filtered_and_sorted(self) -> None:
        elements = [
            {
                "resource_id": controller.RID["private_tile"],
                "clickable": True,
                "bounds": [636, 1030, 1268, 1874],
            },
            {
                "resource_id": controller.RID["private_tile"],
                "clickable": True,
                "bounds": [0, 1030, 633, 1874],
            },
            {
                "resource_id": controller.RID["private_tile"],
                "clickable": False,
                "bounds": [1271, 1030, 1904, 1874],
            },
            {
                "resource_id": "other",
                "clickable": True,
                "bounds": [0, 0, 10, 10],
            },
        ]
        self.assertEqual(
            controller._video_tile_bounds(elements),
            [[0, 1030, 633, 1874], [636, 1030, 1268, 1874]],
        )

    def test_private_dry_run_fails_closed_before_runtime(self) -> None:
        with self.assertRaisesRegex(controller.TikTokCoreError, "PUBLIC required"):
            controller.prepare_dry_run("caption", visibility="PRIVATE")

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

        action_sets = [
            controller.build_dry_run_actions("caption", "Y700Agent"),
            controller.build_commit_actions("caption"),
        ]
        for actions in action_sets:
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
