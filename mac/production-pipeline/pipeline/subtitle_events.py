"""Deterministic, auditable text observations and Chinese subtitle events.

No AI model is allowed to create event IDs, source evidence, or time boundaries.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

VERSION = "subtitle-events-v0.4"
EXCLUSION_REASONS = frozenset({
    "WATERMARK_OR_ACCOUNT", "DUPLICATE_EQUIVALENT",
    "NON_SEMANTIC_DECORATION", "UNRELATED_UI_TEXT",
    "HUMAN_CONFIRMED_FALSE_POSITIVE",
})
DISPOSITIONS = frozenset({"translate_target", "excluded_with_reason", "review_required"})


@dataclass(frozen=True)
class EventRules:
    iou: float = 0.60
    text_similarity: float = 0.85
    adjacent_gap_s: float = 1.5
    min_stable_observations: int = 2
    uncorroborated_noise_max_confidence: float = 0.35
    decoration_allowlist: tuple[str, ...] = ("✨", "🌟", "💫", "⭐")

    def fingerprint(self) -> str:
        return digest(asdict(self))[:16]


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalized_text(text: str, *, short: bool, rules: EventRules) -> str:
    value = unicodedata.normalize("NFC", str(text))
    value = "".join(ch for ch in value if not ch.isspace())
    for decoration in rules.decoration_allowlist:
        value = value.replace(decoration, "")
    if not short:
        # Only ornaments; keep semantic punctuation, digits, negations and variants.
        value = value.replace("【", "").replace("】", "").replace("「", "").replace("」", "")
    return value


def han_count(text: str) -> int:
    return sum(1 for c in text if "\u3400" <= c <= "\u9fff")


def similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, ac in enumerate(a, 1):
        cur = [i]
        for j, bc in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (ac != bc)))
        prev = cur
    return 1.0 - prev[-1] / max(len(a), len(b))


def match_text(a: str, b: str, rules: EventRules) -> bool:
    short = min(han_count(a), han_count(b)) <= 3
    x = normalized_text(a, short=short, rules=rules)
    y = normalized_text(b, short=short, rules=rules)
    if short:
        return bool(x) and x == y
    # Guard semantic reversals even when a long OCR string mostly agrees.
    # Even in long captions, one changed number or negation reverses meaning.
    a_tokens = re.findall(r"不|没|无|否|\d+|[０-９]+", x)
    b_tokens = re.findall(r"不|没|无|否|\d+|[０-９]+", y)
    if a_tokens != b_tokens:
        return False
    return similarity(x, y) >= rules.text_similarity


def bbox_iou(a: list[float] | tuple[float, ...] | None,
             b: list[float] | tuple[float, ...] | None) -> float:
    if not a or not b or len(a) != 4 or len(b) != 4:
        return 0.0
    x0, y0 = max(float(a[0]), float(b[0])), max(float(a[1]), float(b[1]))
    x1, y1 = min(float(a[2]), float(b[2])), min(float(a[3]), float(b[3]))
    area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    aa = max(0.0, float(a[2]) - float(a[0])) * max(0.0, float(a[3]) - float(a[1]))
    bb = max(0.0, float(b[2]) - float(b[0])) * max(0.0, float(b[3]) - float(b[1]))
    return area / max(1e-12, aa + bb - area)


def _same_region(a: dict, b: dict, rules: EventRules) -> bool:
    return bbox_iou(a.get("bbox_norm"), b.get("bbox_norm")) >= rules.iou


def _obs_key(row: dict) -> str:
    return "obs-" + digest([row.get("frame_ts"), row.get("bbox_norm"), row.get("text_zh_raw")])[:16]


def track_ocr(observations: list[dict], duration: float,
              rules: EventRules | None = None) -> list[dict]:
    """Neighbor-only, bounded track association; evidence observations stay intact."""
    rules = rules or EventRules()
    active: list[dict] = []
    completed: list[dict] = []
    seen = sorted(observations, key=lambda r: (float(r.get("frame_ts", 0)), str(r.get("text_zh_raw", ""))))
    for raw in seen:
        text = str(raw.get("text_zh_raw", "")).strip()
        if not text:
            continue
        ts = float(raw["frame_ts"])
        if not 0 <= ts <= duration:
            continue
        row = {**raw, "observation_id": raw.get("observation_id") or _obs_key(raw)}
        candidates = [
            t for t in active
            if 0 <= ts - t["last_ts"] <= rules.adjacent_gap_s
            and match_text(t["text_zh"], text, rules)
            and _same_region({"bbox_norm": t["last_bbox"]}, row, rules)
        ]
        if candidates:
            # Prefer geometric continuity; never merge two adjacent independent texts.
            t = max(candidates, key=lambda v: bbox_iou(v["last_bbox"], row["bbox_norm"]))
            t["last_ts"] = ts
            t["last_bbox"] = row["bbox_norm"]
            t["observations"].append(row["observation_id"])
            t["bbox_history"].append(row["bbox_norm"])
            if float(row.get("ocr_confidence", 0)) > t["best_confidence"]:
                t["best_confidence"] = float(row.get("ocr_confidence", 0))
                t["text_zh"] = text
        else:
            active.append({
                "text_zh": text, "first_ts": ts, "last_ts": ts,
                "last_bbox": row.get("bbox_norm"), "best_confidence": float(row.get("ocr_confidence", 0)),
                "observations": [row["observation_id"]],
                "bbox_history": [row.get("bbox_norm")],
                "first_bbox": row.get("bbox_norm"),
            })
        stale = [t for t in active if ts - t["last_ts"] > rules.adjacent_gap_s]
        for t in stale:
            active.remove(t)
            completed.append(t)
    completed.extend(active)
    out = []
    for track in sorted(completed, key=lambda t: (t["first_ts"], t["text_zh"])):
        # The true start/end are only bounded by sampled observations.
        start = max(0.0, track["first_ts"])
        end = min(float(duration), max(start + 0.05, track["last_ts"] + 0.25))
        stable = len(track["observations"]) >= rules.min_stable_observations
        row = {
            "source_id": "ocr-" + digest([track["observations"], track["text_zh"]])[:16],
            "source_kind": "visual_text",
            "text_zh": track["text_zh"],
            "start": round(start, 3), "end": round(end, 3),
            "bbox_norm": track["first_bbox"],
            "ocr_confidence": round(track["best_confidence"], 4),
            "source_refs": ["analysis/ocr_observations.zh.json#" + oid for oid in track["observations"]],
            "track_observation_ids": track["observations"],
            "track_stable": stable,
            # Preserve uncertain observations in the ledger but do not auto-translate
            # uncorroborated, very-low-confidence non-Han noise. A real English/
            # numerical one-frame callout may still exist: human review is mandatory.
            "review_flags": (
                ([] if stable else ["SHORT_EVENT_REVIEW"]) +
                (["UNVERIFIED_LOW_CONFIDENCE_SINGLE_FRAME"]
                 if (not stable
                     and track["best_confidence"] <= rules.uncorroborated_noise_max_confidence
                     and (han_count(track["text_zh"]) == 0 or
                          (han_count(track["text_zh"]) == 1 and
                           sum(ch.isascii() and ch.isalpha()
                               for ch in track["text_zh"]) >= 4)))
                 else [])
            ),
            "boundary_uncertainty_s": 0.25,
        }
        out.append(row)
    return out


def speech_events(transcript: dict, duration: float) -> list[dict]:
    rows = []
    for n, seg in enumerate(transcript.get("segments", []), 1):
        text = str(seg.get("text", "")).strip()
        start = max(0.0, float(seg.get("start", 0)))
        end = min(duration, float(seg.get("end", duration)))
        if not text or end <= start:
            continue
        rows.append({
            "source_id": "asr-" + digest([n, start, end, text])[:16],
            "source_kind": "speech",
            "text_zh": text,
            "start": round(start, 3), "end": round(end, 3),
            "confidence": max(0.0, min(1.0, 1.0 + float(seg.get("avg_logprob", -0.5)))),
            "source_refs": [f"analysis/transcript.zh.json#seg{n:03d}"],
            "review_flags": [] if han_count(text) >= 2 else ["ASR_SHORT_UNCERTAIN"],
        })
    return rows


def _overlap(a: dict, b: dict) -> float:
    shared = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    return shared / max(0.1, min(a["end"] - a["start"], b["end"] - b["start"]))


def _looks_like_account(event: dict) -> bool:
    text = event["text_zh"]
    box = event.get("bbox_norm") or [0, 0, 1, 1]
    return bool(re.search(r"抖音号\s*[:：]|@[\w.-]{4,}", text)) and (box[0] < .30 or box[2] > .70)


def fuse_events(speech: list[dict], visual: list[dict], *, source_sha256: str,
                duration: float, rules: EventRules | None = None) -> dict:
    rules = rules or EventRules()
    chosen_visual: set[str] = set()
    canonical: list[dict] = []
    all_source = sorted([*speech, *visual], key=lambda e: (e["start"], e["source_id"]))
    at = utc_now()
    for a in speech:
        matches = [v for v in visual if v["source_id"] not in chosen_visual
                   and _overlap(a, v) >= 0.6
                   and match_text(a["text_zh"], v["text_zh"], rules)]
        aligned = max(matches, key=lambda v: _overlap(a, v), default=None)
        if aligned:
            chosen_visual.add(aligned["source_id"])
        source_refs = list(a["source_refs"]) + (list(aligned["source_refs"]) if aligned else [])
        src_ids = [a["source_id"]] + ([aligned["source_id"]] if aligned else [])
        start, end = ((aligned["start"], aligned["end"]) if aligned else (a["start"], a["end"]))
        canonical.append({
            "event_id": "evt-" + digest(src_ids)[:16],
            "source_kind": "ocr_asr_aligned" if aligned else "speech",
            "role": "primary_subtitle",
            "text_zh": aligned["text_zh"] if aligned else a["text_zh"],
            "start": start, "end": end,
            "source_refs": source_refs, "source_event_ids": src_ids,
            "merged_from_event_ids": src_ids if aligned else [],
            "split_from_event_id": None,
            "boundary_decision_reason": "visible_subtitle_aligned" if aligned else "asr_segment",
            "decision_at_utc": at, "pipeline_version": VERSION,
            "rule_set_version": rules.fingerprint(),
            "fact_disposition": "translate_target", "exclude_reason": None,
            "ocr_bbox_norm": aligned.get("bbox_norm") if aligned else None,
            "review_flags": a.get("review_flags", []) + (aligned.get("review_flags", []) if aligned else []),
        })
    for v in visual:
        if v["source_id"] in chosen_visual:
            continue
        account = _looks_like_account(v)
        # Do not invent a "decoration" exclusion for a possible OCR hallucination.
        # Keep uncertain candidates in the ledger for human fact adjudication.
        uncertain_low_confidence = "UNVERIFIED_LOW_CONFIDENCE_SINGLE_FRAME" in v.get("review_flags", [])
        status = ("review_required" if uncertain_low_confidence else
                  "excluded_with_reason" if account else "translate_target")
        canonical.append({
            "event_id": "evt-" + digest([v["source_id"]])[:16],
            "source_kind": "visual_text",
            "role": "callout" if speech and any(_overlap(v, a) > 0.3 for a in speech) else "primary_subtitle",
            "text_zh": v["text_zh"],
            "start": v["start"], "end": v["end"],
            "source_refs": v["source_refs"], "source_event_ids": [v["source_id"]],
            "merged_from_event_ids": [], "split_from_event_id": None,
            "boundary_decision_reason": "independent_visual_track",
            "decision_at_utc": at, "pipeline_version": VERSION,
            "rule_set_version": rules.fingerprint(),
            "fact_disposition": status,
            "exclude_reason": ("WATERMARK_OR_ACCOUNT"
                               if status == "excluded_with_reason" else None),
            "ocr_bbox_norm": v["bbox_norm"],
            "review_flags": v.get("review_flags", []),
        })
    canonical.sort(key=lambda e: (e["start"], e["end"], e["event_id"]))
    return {
        "schema_version": 1, "source_video_sha256": source_sha256,
        "duration_s": duration, "rule_set_version": rules.fingerprint(),
        "pipeline_version": VERSION, "generated_at_utc": at,
        "source_events": all_source, "canonical_events": canonical,
        "canonical_lock": digest([
            (e["event_id"], e["start"], e["end"], e["source_refs"], e["fact_disposition"])
            for e in canonical
        ]),
    }


def verify_ledger(ledger: dict) -> list[str]:
    errors: list[str] = []
    sources = {e["source_id"] for e in ledger.get("source_events", [])}
    events = ledger.get("canonical_events", [])
    ids = {e["event_id"] for e in events}
    if len(ids) != len(events):
        errors.append("DUPLICATE_CANONICAL_EVENT")
    covered: set[str] = set()
    for e in events:
        covered.update(e.get("source_event_ids", []))
        disposition = e.get("fact_disposition")
        if disposition not in DISPOSITIONS:
            errors.append("INVALID_DISPOSITION:" + e.get("event_id", "?"))
        reason = e.get("exclude_reason")
        if disposition == "excluded_with_reason":
            if reason not in EXCLUSION_REASONS:
                errors.append("BLOCKED_INVALID_EXCLUSION:" + e.get("event_id", "?"))
            if reason == "DUPLICATE_EQUIVALENT" and e.get("duplicate_of_event_id") not in ids:
                errors.append("INVALID_DUPLICATE_TARGET:" + e.get("event_id", "?"))
        elif reason:
            errors.append("UNEXPECTED_EXCLUSION_REASON:" + e.get("event_id", "?"))
        if float(e.get("start", -1)) < 0 or float(e.get("end", 0)) <= float(e.get("start", 0)):
            errors.append("INVALID_EVENT_RANGE:" + e.get("event_id", "?"))
    if sources != covered:
        errors.append("ORPHAN_SOURCE_EVENTS")
    expected = digest([
        (e["event_id"], e["start"], e["end"], e["source_refs"], e["fact_disposition"])
        for e in events
    ])
    if ledger.get("canonical_lock") != expected:
        errors.append("FUSED_LOCK_MISMATCH")
    return errors
