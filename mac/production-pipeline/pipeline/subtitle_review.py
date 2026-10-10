"""Opt-in reviewed OCR and ASR fusion. Machine files remain immutable."""
from __future__ import annotations
from copy import deepcopy
from .subtitle_events import digest, fuse_events, verify_ledger


class HumanReviewError(ValueError):
    pass


def reviewed_ledger(machine: dict, machine_visual: list[dict], human: dict) -> dict:
    if human.get("review_state") != "HUMAN_FEEDBACK_CLOSED":
        raise HumanReviewError("review not closed")
    if human.get("source_video_sha256") != machine.get("source_video_sha256"):
        raise HumanReviewError("video hash mismatch")
    if human.get("duration_s") != machine.get("duration_s"):
        raise HumanReviewError("video duration mismatch")
    groups = human.get("visual_canonical_events", [])
    if not groups or human.get("translation_policy", {}).get("variants") != ["normal", "funny"]:
        raise HumanReviewError("dual tone event review required")
    mapping = {}
    extra = []
    for group in groups:
        numbers = group["ocr120_event_numbers"]
        if group.get("importance") != "important" or not group.get("text_zh", "").strip():
            raise HumanReviewError("important text required")
        if group.get("required_localization_variants") != ["normal", "funny"]:
            raise HumanReviewError("every subtitle needs normal and funny tone")
        start, end = float(group["start"]), float(group["end"])
        if not 0 <= start < end <= machine["duration_s"]:
            raise HumanReviewError("invalid reviewed timing")
        if not numbers:
            if group.get("source_kind") not in ("synchronized_duplicate", "visual_text"):
                raise HumanReviewError("extra text requires human evidence")
            extra.append(group)
        for n in numbers:
            if type(n) is not int or n < 1 or n > len(machine_visual) or n in mapping:
                raise HumanReviewError("duplicate/unknown OCR source")
            mapping[n] = group
    exclusions = human.get("ocr_excluded_false_positive_numbers", [])
    if len(set(exclusions)) != len(exclusions) or set(exclusions) & set(mapping):
        raise HumanReviewError("invalid false-positive exclusions")
    if set(mapping) | set(exclusions) != set(range(1, len(machine_visual) + 1)):
        raise HumanReviewError("OCR review does not cover all events")

    visual = []
    emitted = set()
    for n, machine_event in enumerate(machine_visual, 1):
        if n in exclusions:
            visual.append({**machine_event, "human_false_positive": True})
            continue
        group = mapping[n]
        if id(group) in emitted:continue
        emitted.add(id(group))
        members = [machine_visual[i - 1] for i in group["ocr120_event_numbers"]]
        refs = [ref for item in members for ref in item["source_refs"]]
        src_ids = [item["source_id"] for item in members]
        visual.append({
            "source_id": "review-ocr-" + digest([src_ids, group["text_zh"], group["start"], group["end"]])[:16],
            "source_kind": "visual_text", "text_zh": group["text_zh"],
            "start": group["start"], "end": group["end"],
            "source_refs": refs, "bbox_norm": members[0].get("bbox_norm"),
            "ocr_confidence": max(x.get("ocr_confidence", 0) for x in members),
            "machine_source_event_ids": src_ids, "review_flags": [], "human_verified": True,
        })
    for item in extra:
        visual.append({
            "source_id": "human-visual-" + digest([human["source_video_sha256"], item["text_zh"], item["start"]])[:16],
            "source_kind": "visual_text", "text_zh": item["text_zh"],
            "start": item["start"], "end": item["end"],
            "source_refs": ["human_gt:missing_visual"],
            "bbox_norm": None, "ocr_confidence": 0,
            "review_flags": ["HUMAN_CONFIRMED_OCR_MISSED"], "human_verified": True,
        })
    speech = [deepcopy(x) for x in machine["source_events"] if x["source_kind"] == "speech"]
    for n_string, change in human["speech_review"]["machine_corrections"].items():
        ref=f"analysis/transcript.zh.json#seg{int(n_string):03d}"
        matches=[x for x in speech if ref in x["source_refs"]]
        if len(matches)!=1 or matches[0]["text_zh"] != change["from"]:
            raise HumanReviewError("ASR correction source changed")
        matches[0]["text_zh"]=change["to"]
        matches[0]["review_flags"]=["HUMAN_CORRECTED_ASR"]
    rejected = human.get("speech_review", {}).get("tail_t01")
    if rejected and rejected.get("decision") != "HUMAN_REJECTED_FALSE_POSITIVE":
        raise HumanReviewError("unreviewed tail ASR candidate")
    for item in extra:
        if item["source_kind"] != "synchronized_duplicate":
            continue
        speech.append({
            "source_id": "human-speech-" + digest([human["source_video_sha256"], item["start"], item["text_zh"]])[:16],
            "source_kind": "speech", "text_zh": item["text_zh"],
            "start": item["start"], "end": item["end"],
            "confidence": 1.0, "source_refs": ["human_gt:missing_speech"],
            "review_flags": ["HUMAN_CONFIRMED_ASR_MISSED"],
        })
    result=fuse_events(speech,visual,source_sha256=machine["source_video_sha256"],
                       duration=machine["duration_s"])
    excluded_ids={machine_visual[n-1]["source_id"] for n in exclusions}
    for ev in result["canonical_events"]:
        if set(ev["source_event_ids"]) & excluded_ids:
            ev["fact_disposition"]="excluded_with_reason"
            ev["exclude_reason"]="HUMAN_CONFIRMED_FALSE_POSITIVE"
        elif ev["source_kind"] in ("visual_text","ocr_asr_aligned"):
            ev["fact_disposition"]="translate_target"
            ev["exclude_reason"]=None
            ev["role"]="primary_subtitle"
        ev["human_adjudication"]=True
    result["canonical_lock"]=digest([
        (e["event_id"],e["start"],e["end"],e["source_refs"],e["fact_disposition"])
        for e in result["canonical_events"]
    ])
    result["machine_ledger_hash"]=digest(machine)
    result["human_gt_hash"]=digest(human)
    result["human_adjudicated"]=True
    errors=verify_ledger(result)
    if errors:raise HumanReviewError("; ".join(errors))
    return result
