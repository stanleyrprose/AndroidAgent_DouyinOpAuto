"""Non-publishing preview contract regression tests."""
import unittest
from pipeline.review_video import ReviewContractError, resolve_speech_segments, validate_draft


class ReviewVideoTest(unittest.TestCase):
    def setUp(self):
        self.row = {"event_id": "a", "fusion_index": 1, "role": "primary_subtitle",
                    "start": 0, "end": 2, "text_zh": "原文", "normal_my": "မြန်မာ",
                    "funny_my": "မြန်မာ"}
        self.payload = {"status": "DRAFT_UNVERIFIED_NATIVE_AND_TIMING", "events": [self.row]}

    def test_only_unverified_review_draft(self):
        self.assertEqual(len(validate_draft(self.payload, duration=3)), 1)
        self.payload["status"] = "APPROVED"
        with self.assertRaises(ReviewContractError):
            validate_draft(self.payload, duration=3)

    def test_no_duplicate_and_no_invalid_timing(self):
        self.payload["events"] = [self.row, dict(self.row)]
        with self.assertRaises(ReviewContractError):
            validate_draft(self.payload, duration=3)
        self.payload["events"] = [dict(self.row, end=4)]
        with self.assertRaises(ReviewContractError):
            validate_draft(self.payload, duration=3)

    def test_speech_only_and_overlap_precedence(self):
        later = dict(self.row, event_id="b", fusion_index=2, start=1, end=3)
        visual = dict(self.row, event_id="c", fusion_index=3, role="callout", start=0, end=3)
        self.assertEqual(resolve_speech_segments([self.row, later, visual], 3),
                         [(0., 1, 1), (1, 3, 2)])


if __name__ == "__main__":
    unittest.main()
