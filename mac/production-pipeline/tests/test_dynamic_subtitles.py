"""Regression contracts for deterministic Myanmar subtitle mode (no real media or TikTok)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.common import atomic_json, sha256_file
from pipeline.subtitle_events import (
    EventRules, bbox_iou, fuse_events, match_text, speech_events,
    track_ocr, verify_ledger,
)
from pipeline.subtitle_localization import (
    TranslationContractError, TranslationExhaustedError,
    TranslationNetworkError, build_timeline, retry_translator,
    translation_request, validate_response,
)
from pipeline.subtitle_quality import approve_review, evaluate, list_quality_queue
from pipeline.subtitle_notify import notify_if_blocked


def make_speech():
    return speech_events({
        "segments": [
            {"start": .5, "end": 1.5, "text": "怎么回事"},
            {"start": 2.0, "end": 3.0, "text": "原来如此"},
            {"start": 3.5, "end": 5.0, "text": "还没结束"},
        ],
    }, 7.0)


class ContextualAsrTests(unittest.TestCase):
    def test_hotwords_are_opt_in_bounded_and_deduplicated(self):
        from pipeline.analyze import asr_hotwords
        with patch.dict("os.environ", {"Y700_ASR_HOTWORDS": "中微子, 地幔,地幔;核聚变"}):
            self.assertEqual(asr_hotwords(), "中微子，地幔，核聚变")
        with patch.dict("os.environ", {"Y700_ASR_HOTWORDS": ""}):
            self.assertIsNone(asr_hotwords())
        with patch.dict("os.environ", {"Y700_ASR_HOTWORDS": ",".join(["a"] * 33)}):
            with self.assertRaises(ValueError):
                asr_hotwords()


class VisualOnlyInputTests(unittest.TestCase):
    def test_dynamic_analysis_accepts_video_without_audio_track(self):
        from pipeline.analyze import analyze
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            location = Path(tmp)
            no_audio_probe = {
                "format": {"duration": "3.0"},
                "streams": [{"codec_type": "video", "width": 540, "height": 960}],
            }
            with patch("pipeline.analyze.ffprobe", return_value=no_audio_probe):
                with patch("pipeline.analyze.keyframes", return_value=[]):
                    with patch("pipeline.analyze.extract_audio") as extract:
                        with patch("pipeline.analyze.transcribe") as transcribe:
                            result = analyze(location / "silent.mp4", location / "analysis",
                                             allow_no_audio=True)
                            self.assertFalse(result["meaningful_speech"])
                            self.assertEqual(result["route"], "visual_review")
                            self.assertFalse(result["transcript"]["segments"])
                            extract.assert_not_called()
                            transcribe.assert_not_called()


class TextTrackTests(unittest.TestCase):
    def test_short_exact_does_not_merge_numbers_negation_or_punctuation(self):
        rules = EventRules()
        for a, b in (("吗", "马"), ("不", "没"), ("1", "１"), ("吗？", "吗?")):
            self.assertFalse(match_text(a, b, rules), (a, b))
        self.assertTrue(match_text(" 吗 ", "吗", rules))
        self.assertTrue(match_text("你✨", "你", rules))

    def test_nearby_same_text_stays_track_but_reappearance_splits(self):
        observations = [
            {"frame_ts": t, "text_zh_raw": s,
             "bbox_norm": [0.1, .75, .9, .85], "ocr_confidence": .95}
            for t, s in [(.5, "精彩反转"), (1.0, "精彩反转"),
                         (4.0, "精彩反转"), (4.5, "精彩反转")]
        ]
        events = track_ocr(observations, 6.0)
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e["track_stable"] for e in events))

    def test_one_frame_text_is_reviewable_not_discarded(self):
        events = track_ocr([{
            "frame_ts": 1.0, "text_zh_raw": "不",
            "bbox_norm": [0, .5, .2, .6], "ocr_confidence": .80,
        }], 2.0)
        self.assertEqual(len(events), 1)
        self.assertIn("SHORT_EVENT_REVIEW", events[0]["review_flags"])

    def test_uncertain_short_flash_requires_review_before_translation(self):
        visual = track_ocr([{
            "frame_ts": 1.0, "text_zh_raw": "不",
            "bbox_norm": [.1, .7, .4, .8], "ocr_confidence": .75,
        }], 3.0)
        ledger = fuse_events([], visual, source_sha256="a" * 64, duration=3.0)
        events = ledger["canonical_events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["fact_disposition"], "review_required")
        self.assertIn("SHORT_EVENT_REVIEW", events[0]["review_flags"])
        self.assertEqual(len(translation_request(ledger)["target_events"]), 0)

    def test_global_layout_prevents_simultaneous_overlays(self):
        from pipeline.subtitle_layout import plan_timeline, intersects
        geometry = {'source_dimensions': [1080, 1920],
                    'source_to_output_affine_matrix': [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}
        events = [{'event_id': f'e{i}', 'start': 0, 'end': 2, 'role': 'callout'}
                  for i in range(2)]
        positions = plan_timeline(events, geometry)
        a, b = (positions[x['event_id']] for x in events)
        self.assertFalse(intersects((a['x'], a['y'], a['x'] + 900, a['y'] + 260),
                                    (b['x'], b['y'], b['x'] + 900, b['y'] + 260), margin=0))
        with self.assertRaisesRegex(ValueError, 'BLOCKED_CONCURRENT_SUBTITLE_LAYOUT'):
            plan_timeline([dict(events[0], event_id=f'overflow-{i}') for i in range(7)], geometry)

    def test_aligned_ocr_does_not_clip_speech_tail(self):
        speech = speech_events({"segments": [{"start": 0.0, "end": 4.0,
                                               "text": "还没有结束"}]}, 6.0)
        visual = track_ocr([{"frame_ts": t, "text_zh_raw": "还没有结束",
                             "bbox_norm": [.1, .7, .9, .8], "ocr_confidence": .95}
                            for t in (1.0, 1.5)], 6.0)
        ledger = fuse_events(speech, visual, source_sha256="a" * 64, duration=6.0)
        aligned = ledger["canonical_events"][0]
        self.assertEqual(aligned["source_kind"], "ocr_asr_aligned")
        self.assertEqual((aligned["start"], aligned["end"]), (0.0, 4.0))

    def test_bbox(self):
        self.assertAlmostEqual(bbox_iou([0, 0, 1, 1], [0, 0, 1, 1]), 1)
        self.assertEqual(bbox_iou([0, 0, .2, .2], [.8, .8, 1, 1]), 0)


class HumanGtCalibrationContracts(unittest.TestCase):
    def test_candidate_only_gt_does_not_count_exclusions_as_accepted(self):
        from importlib.util import spec_from_file_location, module_from_spec
        script = Path(__file__).resolve().parents[1] / "scripts" / "extract_gt_calibration.py"
        spec = spec_from_file_location("extract_gt_calibration", script)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for layer in ("ocr", "asr", "fusion"):
                atomic_json(root / f"{layer}-human-gt.json", {
                    "meta": {"source_sha256": "a" * 64},
                    "events": [
                        {"index": 1, "decision": "accept", "start": 0, "end": 1,
                         "machine_text_zh": "地盒", "human_text_zh": "地核"},
                        {"index": 2, "decision": "false_positive_exclude",
                         "machine_text_zh": "凶"},
                    ],
                })
            result = module.build_cases(root)
            self.assertFalse(result["independent_recall_evidence"])
            self.assertEqual(result["layers"]["ocr"]["accepted_count"], 1)
            self.assertEqual(len(result["layers"]["asr"]["corrections"]), 1)
            self.assertEqual(len(result["layers"]["fusion"]["excluded"]), 1)


class FullSpanQualityRegressionTests(unittest.TestCase):
    def test_numeric_review_does_not_silently_pass(self):
        from pipeline.subtitle_quality import review_status
        self.assertEqual(review_status(["REVIEW_REQUIRED_NUMERIC_SEMANTICS"]),
                         "REVIEW_REQUIRED")

    def test_missing_late_speech_cue_blocks_qa(self):
        from pipeline.subtitle_quality import review_status
        self.assertEqual(review_status(["BLOCKED_SPEECH_SUBTITLE_GAP"]), "BLOCKED")
        self.assertEqual(review_status(["BLOCKED_VISUAL_SUBTITLE_GAP"]), "BLOCKED")
        self.assertEqual(review_status(["BLOCKED_SEMANTIC_AUDIT_UNCERTAIN"]), "BLOCKED")


class LockedTranslationTests(unittest.TestCase):
    def setUp(self):
        self.ledger = fuse_events(make_speech(), [], source_sha256="a" * 64, duration=7)
        self.req = translation_request(self.ledger)

    def test_deterministic_event_identity_and_ledger(self):
        other = fuse_events(make_speech(), [], source_sha256="a" * 64, duration=7)
        self.assertEqual(self.ledger["canonical_lock"], other["canonical_lock"])
        self.assertFalse(verify_ledger(self.ledger))
        self.assertEqual(len(self.ledger["canonical_events"]), 3)

    def test_wrong_id_is_not_accepted(self):
        with self.assertRaises(TranslationContractError):
            validate_response(self.req, {"translations": [
                {"event_id": "unknown", "text_my": "မင်္ဂလာပါ"}
            ]})
        with self.assertRaises(TranslationContractError):
            validate_response(self.req, {"translations": [
                {"event_id": self.req["target_events"][0]["event_id"],
                 "text_my": "မင်္ဂလာပါ", "start": 0}
            ]})

    def test_semantic_audit_tracks_all_event_ids(self):
        from pipeline.subtitle_localization import semantic_audit_request, validate_semantic_audit
        translations = {e["event_id"]: "မင်္ဂလာပါ" for e in self.ledger["canonical_events"]}
        request = semantic_audit_request(self.ledger, translations)
        response = {"audit_request_sha256": request["audit_request_sha256"],
                    "findings": [{"event_id": e["event_id"], "verdict": "uncertain",
                                  "reason": "needs independent comparison"}
                                 for e in self.ledger["canonical_events"]]}
        self.assertEqual(validate_semantic_audit(request, response), response)
        with self.assertRaises(TranslationContractError):
            validate_semantic_audit(request, {**response, "findings": response["findings"][:-1]})
        with self.assertRaises(TranslationContractError):
            validate_semantic_audit(request, {**response, "audit_request_sha256": "stale"})

    def test_semantic_repair_only_rewrites_flagged_events(self):
        from pipeline.subtitle_localization import semantic_audit_request, semantic_repair_request, apply_semantic_repairs
        translations = {e["event_id"]: "မင်္ဂလာပါ" for e in self.ledger["canonical_events"]}
        audit_req = semantic_audit_request(self.ledger, translations)
        bad_id = audit_req["pairs"][0]["event_id"]
        audit = {"audit_request_sha256": audit_req["audit_request_sha256"],
                 "findings": [{"event_id": p["event_id"],
                               "verdict": "fail" if p["event_id"] == bad_id else "pass",
                               "reason": "meaning changed" if p["event_id"] == bad_id else ""}
                              for p in audit_req["pairs"]]}
        repair = semantic_repair_request(audit_req, audit)
        self.assertEqual(len(repair["target_events"]), 1)
        updated = apply_semantic_repairs(audit_req, repair,
                  {"translations": [{"event_id": bad_id, "text_my": "ဟုတ်ကဲ့"}]})
        with self.assertRaises(TranslationContractError):
            apply_semantic_repairs(audit_req, repair,
                {"translations": [{"event_id": bad_id, "text_my": translations[bad_id]}]})
        self.assertEqual(updated[bad_id], "ဟုတ်ကဲ့")
        self.assertTrue(all(updated[k] == v for k, v in translations.items() if k != bad_id))
        with self.assertRaises(TranslationContractError):
            semantic_repair_request(audit_req, audit, attempt=3)

    def test_chinese_or_english_echo_is_not_burmese_translation(self):
        for wrong in ("怎么回事", "This is a summary"):
            with self.assertRaises(TranslationContractError):
                validate_response({"target_events": [{"event_id": "evt-test"}]},
                                  {"translations": [{"event_id": "evt-test", "text_my": wrong}]})

    def test_retry_only_network_and_timeout(self):
        calls = []
        def flaky(_):
            calls.append(1)
            if len(calls) <= 2:
                raise TranslationNetworkError("temporary")
            return {"translations": [{"event_id": t["event_id"], "text_my": "မင်္ဂလာပါ"}
                                     for t in self.req["target_events"]]}
        translated, errors = retry_translator(self.req, flaky, sleep=lambda _: None)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(errors), 2)
        self.assertEqual(len(translated), 3)
        def invalid(_):
            raise TranslationContractError("missing ID")
        with self.assertRaises(TranslationContractError):
            retry_translator(self.req, invalid, sleep=lambda _: None)

    def test_three_network_failures_end_blocked(self):
        with self.assertRaises(TranslationExhaustedError):
            retry_translator(self.req,
                             lambda _: (_ for _ in ()).throw(TimeoutError()),
                             sleep=lambda _: None)

    def test_translator_cannot_collapse_three_events(self):
        from pipeline.subtitle_events import digest
        bundle = {
            "canonical_lock": self.ledger["canonical_lock"],
            "fused_events_sha256": digest(self.ledger),
            "translations": [
                {"event_id": e["event_id"], "text_my": f"မြန်မာစာ {i}"}
                for i, e in enumerate(self.ledger["canonical_events"])
            ],
            "caption_my": "မြန်မာစာ", "visibility": "PUBLIC",
        }
        timeline, projection = build_timeline(self.ledger, bundle)
        self.assertEqual(len(timeline["events"]), 3)
        self.assertEqual(len(projection["cues"]), 3)


class RenderDurationTests(unittest.TestCase):
    def test_looped_png_inputs_have_hard_output_time_limit(self):
        from pipeline.subtitle_render import duration_limit_args
        self.assertEqual(duration_limit_args(6.0), ["-t", "6.000"])
        with self.assertRaises(ValueError):
            duration_limit_args(0)
        with self.assertRaises(ValueError):
            duration_limit_args(float("inf"))


class QualityGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.job = Path(self.temp.name) / "dy-offline"
        for folder in ("source", "analysis", "localization", "production"):
            (self.job / folder).mkdir(parents=True, exist_ok=True)
        source = self.job / "source" / "source.mp4"
        source.write_bytes(b"offline test source - never published")
        source_hash = sha256_file(source)
        self.ledger = fuse_events(make_speech(), [], source_sha256=source_hash, duration=7)
        atomic_json(self.job / "source" / "source.json", {"video_path": str(source)})
        atomic_json(self.job / "analysis" / "analysis.json", {
            "duration": 7, "meaningful_speech": True,
            "dynamic_ocr": {"ocr_observations": 0, "ocr_calls": 7,
                            "budget_exhausted": False},
            "probe": {"streams": [{"codec_type": "video", "width": 1080, "height": 1920}]},
        })
        atomic_json(self.job / "analysis" / "fused_events.zh.json", self.ledger)
        from pipeline.subtitle_events import digest
        bundle = {
            "canonical_lock": self.ledger["canonical_lock"],
            "fused_events_sha256": digest(self.ledger),
            "translations": [
                {"event_id": e["event_id"], "text_my": "မြန်မာစာ"}
                for e in self.ledger["canonical_events"]
            ], "caption_my": "မြန်မာစာ",
        }
        self.timeline, self.projection = build_timeline(self.ledger, bundle)
        atomic_json(self.job / "localization" / "subtitle_timeline.json", self.timeline)
        atomic_json(self.job / "localization" / "localization.json", self.projection)
        # QA requires an independent audit; an unaudited synthetic translation
        # must never be treated as clean simply because it contains Burmese.
        from pipeline.subtitle_localization import semantic_audit_request
        translations = {e["event_id"]: e["localization"]["text_my"]
                        for e in self.timeline["events"] if e["fact_disposition"] == "translate_target"}
        audit_request = semantic_audit_request(self.ledger, translations)
        atomic_json(self.job / "localization" / "semantic_audit.json", {
            "audit_request_sha256": audit_request["audit_request_sha256"],
            "findings": [{"event_id": eid, "verdict": "pass", "reason": "fixture"}
                         for eid in translations],
        })
        atomic_json(self.job / "analysis" / "transcript.zh.json", {
            "segments": [{"start": e["start"], "end": e["end"], "text": e["text_zh"]}
                         for e in self.ledger["source_events"] if e["source_kind"] == "speech"]
        })

    def test_clean_three_cues_pass_data_gate(self):
        report = evaluate(self.job)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["codes"], [])

    def test_hash_mismatch_blocks(self):
        source = self.job / "source" / "source.mp4"
        source.write_bytes(b"changed")
        report = evaluate(self.job)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("BLOCKED_ARTIFACT_MISMATCH", report["codes"])

    def test_post_render_rejects_stale_timeline_artifact(self):
        from pipeline.subtitle_events import digest
        video = self.job / "production" / "video.my.mp4"
        video.write_bytes(b"synthetic mock render")
        caption = self.job / "production" / "caption.my.txt"
        caption.write_text("မြန်မာစာ\n", encoding="utf-8")
        atomic_json(self.job / "production" / "render-result.json", {
            "sha256": {"video": sha256_file(video), "caption": sha256_file(caption)},
            "source_to_output_affine_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "timeline_sha256": "stale-timeline",
        })
        report = evaluate(self.job, after_render=True)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("BLOCKED_ARTIFACT_MISMATCH", report["codes"])

    def test_invalid_exclusion_blocks(self):
        self.ledger["canonical_events"][0]["fact_disposition"] = "excluded_with_reason"
        self.ledger["canonical_events"][0]["exclude_reason"] = "TOO_HARD_TO_TRANSLATE"
        atomic_json(self.job / "analysis" / "fused_events.zh.json", self.ledger)
        report = evaluate(self.job)
        self.assertIn("BLOCKED_INVALID_EXCLUSION", report["codes"])

    def test_budget_does_not_auto_pass(self):
        data = json.loads((self.job / "analysis" / "analysis.json").read_text())
        data["dynamic_ocr"]["budget_exhausted"] = True
        data["dynamic_ocr"]["unscanned"] = [[2, 3]]
        atomic_json(self.job / "analysis" / "analysis.json", data)
        report = evaluate(self.job)
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertIn("REVIEW_REQUIRED_SPEECH_ONLY", report["codes"])

    @patch("pipeline.telegram_notify.send_status")
    def test_outbox_retained_on_notification_failure(self, send):
        send.return_value = {"sent": False, "reason": "TELEGRAM_DELIVERY_FAILED"}
        data = json.loads((self.job / "analysis" / "analysis.json").read_text())
        data["dynamic_ocr"]["budget_exhausted"] = True
        atomic_json(self.job / "analysis" / "analysis.json", data)
        report = evaluate(self.job)
        notify_if_blocked(self.job, report)
        pending = list_quality_queue(self.job.parent)
        self.assertEqual(len(pending), 1)
        self.assertGreaterEqual(len(pending[0]["unsent_alerts"]), 1)

    def test_no_manual_override_of_hard_error(self):
        report = evaluate(self.job)
        with self.assertRaises(ValueError):
            approve_review(self.job, code="BLOCKED_ARTIFACT_MISMATCH",
                           reviewer="QA", reason="It seems acceptable")
