"""Synthetic quality regressions; never require private videos or network."""
import copy
import unittest
from types import SimpleNamespace

import numpy as np

from pipeline.asr_tail import tail_review_candidates
from pipeline.subtitle_events import fuse_events, speech_events, track_ocr, verify_ledger
from pipeline.subtitle_review import HumanReviewError, reviewed_ledger
from pipeline.subtitle_localization import (
    TranslationContractError, build_dual_timelines, dual_translation_request,
)
from pipeline.subtitle_events import digest


def example():
    texts=["？","你笑死我了","◎","回味中"]
    visual=track_ocr([
        {"frame_ts":i+0.2,"text_zh_raw":text,
         "bbox_norm":[.2,.2,.4,.3],"ocr_confidence":.8}
        for i,text in enumerate(texts)],6)
    speech=speech_events({"segments":[{"start":1,"end":2,
                                       "text":"你叫我什么了","avg_logprob":-.2}]},6)
    machine=fuse_events(speech,visual,source_sha256="a"*64,duration=6)
    def group(numbers,text,start,end,kind="visual_text"):
        return {"ocr120_event_numbers":numbers,"text_zh":text,
                "start":start,"end":end,"importance":"important",
                "source_kind":kind,"required_localization_variants":["normal","funny"]}
    human={
        "review_state":"HUMAN_FEEDBACK_CLOSED","source_video_sha256":"a"*64,
        "duration_s":6,"translation_policy":{"variants":["normal","funny"]},
        "visual_canonical_events":[
            group([1],"？",.2,.45),
            group([2],"你笑死我了",1.2,1.45),
            group([4],"回味中",3.2,3.45),
            group([],"嗯",4.5,5.3,"synchronized_duplicate"),
        ],
        "ocr_excluded_false_positive_numbers":[3],
        "speech_review":{
            "machine_corrections":{"1":{"from":"你叫我什么了","to":"你笑死我了"}},
            "tail_t01":{"decision":"HUMAN_REJECTED_FALSE_POSITIVE"},
        }
    }
    return machine,visual,human


class ReviewQualityTest(unittest.TestCase):
    def test_review_preserves_raw_and_corrects_with_provenance(self):
        machine,visual,human=example()
        original=copy.deepcopy(machine)
        ledger=reviewed_ledger(machine,visual,human)
        self.assertEqual(machine,original)
        self.assertEqual(verify_ledger(ledger),[])
        self.assertTrue(ledger["human_adjudicated"])
        targets=[e for e in ledger["canonical_events"]
                 if e["fact_disposition"]=="translate_target"]
        words=[x["text_zh"] for x in targets]
        self.assertIn("？",words)
        self.assertIn("你笑死我了",words)
        self.assertIn("回味中",words)
        self.assertIn("嗯",words)
        self.assertNotIn("喔！",words)
        self.assertNotIn("你叫我什么了",words)
        self.assertEqual(sum(e["source_kind"]=="ocr_asr_aligned" for e in targets),2)
        excluded=[e for e in ledger["canonical_events"]
                  if e["fact_disposition"]=="excluded_with_reason"]
        self.assertEqual(len(excluded),1)
        self.assertEqual(excluded[0]["exclude_reason"],"HUMAN_CONFIRMED_FALSE_POSITIVE")

    def test_mismatch_or_omission_refuses_to_apply(self):
        machine,visual,human=example()
        bad=copy.deepcopy(human)
        bad["source_video_sha256"]="b"*64
        with self.assertRaises(HumanReviewError):
            reviewed_ledger(machine,visual,bad)
        bad=copy.deepcopy(human)
        bad["visual_canonical_events"][0]["ocr120_event_numbers"]=[]
        with self.assertRaises(HumanReviewError):
            reviewed_ledger(machine,visual,bad)
        bad=copy.deepcopy(human)
        bad["visual_canonical_events"][0]["required_localization_variants"]=["normal"]
        with self.assertRaises(HumanReviewError):
            reviewed_ledger(machine,visual,bad)

    def test_dual_version_is_all_or_nothing_and_events_identical(self):
        machine,visual,human=example()
        ledger=reviewed_ledger(machine,visual,human)
        req=dual_translation_request(ledger)
        self.assertEqual(req["variants"],["normal","funny"])
        targets=req["target_events"]
        def bundle(preset):
            return {"canonical_lock":ledger["canonical_lock"],
                    "fused_events_sha256":digest(ledger),
                    "translations":[{"event_id":e["event_id"],"text_my":"မြန်မာစာ"}
                                    for e in targets],
                    "caption_my":"မြန်မာစာ","render_preset":preset}
        pair={"normal":bundle("dynamic_clean"),"funny":bundle("dynamic_fun")}
        results=build_dual_timelines(ledger,pair)
        self.assertEqual(len(results),2)
        self.assertEqual(
            [e["event_id"] for e in results["normal"]["timeline"]["events"]],
            [e["event_id"] for e in results["funny"]["timeline"]["events"]])
        with self.assertRaises(TranslationContractError):
            build_dual_timelines(ledger,{"normal":pair["normal"]})
        broken=copy.deepcopy(pair)
        broken["funny"]["translations"].pop()
        with self.assertRaises(TranslationContractError):
            build_dual_timelines(ledger,broken)


class ASRTailTest(unittest.TestCase):
    def test_early_full_asr_tail_generates_review_candidates_not_subtitles(self):
        class Stub:
            calls=0
            def transcribe(self,audio,**kwargs):
                self.calls+=1
                seg=SimpleNamespace(start=1.0,end=1.4,text="嗯")
                return iter([seg]),SimpleNamespace(language="zh")
        model=Stub()
        audio=np.full(20*16000,.1,dtype=np.float32)
        original=[{"start":1.0,"end":4.0,"text":"你好"}]
        result=tail_review_candidates(model,audio,original)
        self.assertGreaterEqual(model.calls,1)
        self.assertEqual(original,[{"start":1.0,"end":4.0,"text":"你好"}])
        self.assertTrue(result["tail_review_required"])
        self.assertTrue(result["tail_review_candidates"])
        self.assertTrue(all(x["review_status"].startswith("REVIEW_REQUIRED")
                            for x in result["tail_review_candidates"]))

    def test_short_gap_and_silence_do_not_invent_speech(self):
        class NeverCall:
            def transcribe(self,*args,**kwargs):
                raise AssertionError("silent audio must not go to model")
        self.assertFalse(tail_review_candidates(
            NeverCall(),np.zeros(20*16000,dtype=np.float32),
            [{"start":1,"end":4}])["tail_review_candidates"])
        self.assertFalse(tail_review_candidates(
            NeverCall(),np.ones(20*16000,dtype=np.float32),
            [{"start":15,"end":19}])["tail_windows_checked_s"])


if __name__=="__main__":
    unittest.main()
