import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.tiktok.state import TIKTOK, detect_state


class TikTokStateTests(unittest.TestCase):
    def test_home_detected_from_semantic_bottom_nav(self):
        elements = [
            {"package": TIKTOK, "content_desc": "首页"},
            {"package": TIKTOK, "content_desc": "创建"},
            {"package": TIKTOK, "content_desc": "主页"},
        ]
        self.assertEqual(detect_state(elements)["state"], "HOME")

    def test_legacy_home_id_still_requires_home_semantics(self):
        elements = [
            {"package": TIKTOK, "resource_id": f"{TIKTOK}:id/o70"},
            {"package": TIKTOK, "text": "首页"},
        ]
        self.assertEqual(detect_state(elements)["state"], "HOME")

    def test_create_state_wins_over_bottom_nav_semantics(self):
        elements = [
            {"package": TIKTOK, "resource_id": f"{TIKTOK}:id/upload_hot_area"},
            {"package": TIKTOK, "content_desc": "首页"},
            {"package": TIKTOK, "content_desc": "创建"},
            {"package": TIKTOK, "content_desc": "主页"},
        ]
        self.assertEqual(detect_state(elements)["state"], "CREATE")


if __name__ == "__main__":
    unittest.main()
