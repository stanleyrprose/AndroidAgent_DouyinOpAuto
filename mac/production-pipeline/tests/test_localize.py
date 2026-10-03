import unittest

from pipeline.localize import validate


class LocalizeTests(unittest.TestCase):
    def test_visual_text(self):
        d = validate({
            "content_type": "visual_text",
            "title_my": "ခေါင်းစဉ်",
            "caption_my": "စာတန်း",
            "visibility": "PRIVATE",
            "cues": [{"start": 0.2, "end": 9.5, "text_my": "စာ"}],
        }, 10.0)
        self.assertEqual(d["visibility"], "PRIVATE")
        self.assertEqual(len(d["cues"]), 1)

    def test_bad_range(self):
        with self.assertRaises(ValueError):
            validate({
                "content_type": "speech",
                "caption_my": "x",
                "cues": [{"start": 4, "end": 2, "text_my": "x"}],
            }, 10.0)


if __name__ == "__main__":
    unittest.main()
