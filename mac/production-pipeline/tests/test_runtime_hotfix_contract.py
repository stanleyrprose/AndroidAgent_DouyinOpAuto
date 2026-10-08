from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProductionHotfixContractTests(unittest.TestCase):
    def test_long_form_render_has_bounded_30_minute_timeout(self) -> None:
        text = (ROOT / "pipeline" / "render.py").read_text(encoding="utf-8")
        self.assertIn("run(args, timeout=1800)", text)
        self.assertNotIn("run(args, timeout=240)", text)

    def test_album_notification_braces_variable_before_fullwidth_punctuation(self) -> None:
        text = (ROOT / "scripts" / "store-to-y700-album.sh").read_text(encoding="utf-8")
        self.assertIn("Movies/${ALBUM}；缅语 Caption", text)
        self.assertNotIn("Movies/$ALBUM；缅语 Caption", text)


if __name__ == "__main__":
    unittest.main()
