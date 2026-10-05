import unittest

from pipeline.localize import validate


class LocalizeTests(unittest.TestCase):
    def test_visual_text(self):
        d = validate({
            "content_type": "visual_text",
            "title_my": "ခေါင်းစဉ်",
            "caption_my": "စာတန်း",
            "caption_basis": {
                "type": "visual_text",
                "reason": "The visible sign is the main hook.",
                "source_frames": [1.2],
                "source_transcript": [],
            },
            "visibility": "PUBLIC",
            "cues": [{"start": 0.2, "end": 9.5, "text_my": "စာ"}],
        }, 10.0)
        self.assertEqual(d["visibility"], "PUBLIC")
        self.assertEqual(len(d["cues"]), 1)

    def test_bad_range(self):
        with self.assertRaises(ValueError):
            validate({
                "content_type": "speech",
                "caption_my": "x",
                "caption_basis": {
                    "type": "speech",
                    "reason": "Spoken line drives the caption.",
                    "source_frames": [],
                    "source_transcript": ["source line"],
                },
                "cues": [{"start": 4, "end": 2, "text_my": "x"}],
            }, 10.0)

    def test_caption_basis_is_required(self):
        with self.assertRaisesRegex(ValueError, "caption_basis is required"):
            validate({
                "content_type": "visual_only",
                "caption_my": "x",
                "cues": [],
            }, 10.0)

    def test_visual_only_basis_requires_frame_evidence(self):
        with self.assertRaisesRegex(ValueError, "visual_only caption_basis requires source_frames"):
            validate({
                "content_type": "visual_only",
                "caption_my": "x",
                "caption_basis": {
                    "type": "visual_only",
                    "reason": "Visual hook",
                    "source_frames": [],
                    "source_transcript": ["not applicable"],
                },
                "cues": [],
            }, 10.0)

    def test_basis_type_must_match_content_type(self):
        with self.assertRaisesRegex(ValueError, "must match content_type"):
            validate({
                "content_type": "mixed",
                "caption_my": "x",
                "caption_basis": {
                    "type": "speech",
                    "reason": "Mismatch",
                    "source_frames": [],
                    "source_transcript": ["line"],
                },
                "cues": [{"start": 0, "end": 1, "text_my": "x"}],
            }, 10.0)


if __name__ == "__main__":
    unittest.main()
