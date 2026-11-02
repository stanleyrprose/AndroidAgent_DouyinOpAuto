"""Locked event -> Myanmar localization. LLM output can only fill text_my."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from .subtitle_events import digest, verify_ledger

class TranslationContractError(ValueError):
    code = "BLOCKED_TRANSLATION_CONTRACT"


class TranslationNetworkError(ConnectionError):
    pass


class TranslationExhaustedError(RuntimeError):
    code = "BLOCKED_UNRESOLVED_EVENT"


def translation_targets(ledger: dict) -> list[dict]:
    errors = verify_ledger(ledger)
    if errors:
        raise TranslationContractError("; ".join(errors))
    return [event for event in ledger["canonical_events"]
            if event["fact_disposition"] == "translate_target"]


def translation_request(ledger: dict, *, start: int = 0,
                        batch_size: int = 16, summary: str = "") -> dict:
    targets = translation_targets(ledger)
    batch = targets[start:start + batch_size]
    indexed = ledger["canonical_events"]
    around_ids = {e["event_id"] for e in batch}
    context = []
    for event in batch:
        pos = next(i for i, x in enumerate(indexed) if x["event_id"] == event["event_id"])
        for neighbor in indexed[max(0, pos - 2):pos + 3]:
            if neighbor["event_id"] not in around_ids and neighbor not in context:
                context.append(neighbor)
    context.sort(key=lambda x: (x["start"], x["event_id"]))
    output = {
        "schema_version": 1,
        "locked_fused_sha256": digest(ledger),
        "canonical_lock": ledger["canonical_lock"],
        "target_events": [
            {"event_id": e["event_id"], "text_zh": e["text_zh"],
             "role": e["role"], "source_refs": e["source_refs"]}
            for e in batch
        ],
        "readonly_context": {
            "full_context_summary": summary,
            "surrounding_events": [
                {"event_id": e["event_id"], "text_zh": e["text_zh"], "role": e["role"]}
                for e in context[:4]
            ],
        },
        "instruction": (
            "Return ONLY a translations array of {event_id,text_my} for target_events. "
            "Preserve IDs one-to-one. No extra IDs or fields, no timing edits. "
            "Use surrounding_events as read-only context. Do not invent plot details. "
            "Translate every source clause faithfully: preserve negation, numbers, "
            "named entities, scientific terminology, and speaker intent. "
            "Never replace an event with a summary of the video."
        ),
    }
    output["request_hash"] = digest(output)
    return output


def semantic_audit_request(ledger: dict, translations: dict[str, str]) -> dict:
    """Separate translation audit input; never alter canonical source events."""
    targets = translation_targets(ledger)
    expected = {e["event_id"] for e in targets}
    if set(translations) != expected:
        raise TranslationContractError("semantic audit requires complete target IDs")
    payload = {
        "schema_version": 1,
        "canonical_lock": ledger["canonical_lock"],
        "fused_events_sha256": digest(ledger),
        "pairs": [{"event_id": e["event_id"], "text_zh": e["text_zh"],
                   "text_my": translations[e["event_id"]]}
                  for e in targets],
        "verified_source_context": [
            {"event_id": e["event_id"], "meaning": e["human_verified_meaning"]}
            for e in targets if e.get("human_verified_meaning")
        ],
        "audit_instruction": (
            "Treat verified_source_context as the human-confirmed intended meaning "
            "of the original Chinese phrase; do not reinterpret its referent as a "
            "proper name when the reviewer has clarified the metaphor. "
            "Independently compare each Chinese source and Burmese translation. "
            "Identify omissions, changed negations, numerical errors, scientific "
            "terms, names and unrelated paraphrases. Return event_id, verdict "
            "(pass|fail|uncertain), reason and proposed correction. "
            "Do not infer correctness from Myanmar characters alone. "
            "Return JSON with audit_request_sha256 copied exactly from this request "
            "and findings array containing every event_id once. "
            "For every finding include verdict and reason."
        ),
    }
    payload["audit_request_sha256"] = digest(payload)
    return payload


def validate_semantic_audit(request: dict, response: dict) -> dict:
    """Check that an independent audit is complete and bound to its source."""
    if not isinstance(response, dict) or not isinstance(request, dict):
        raise TranslationContractError("semantic audit expects JSON objects")
    if response.get("audit_request_sha256") != request.get("audit_request_sha256"):
        raise TranslationContractError("semantic audit request hash mismatch")
    expected = {pair["event_id"] for pair in request["pairs"]}
    findings = response.get("findings")
    if not isinstance(findings, list) or len(findings) != len(expected):
        raise TranslationContractError("semantic audit findings incomplete")
    ids = [row.get("event_id") for row in findings if isinstance(row, dict)]
    if len(ids) != len(expected) or set(ids) != expected:
        raise TranslationContractError("semantic audit IDs invalid")
    if any(row.get("verdict") not in ("pass", "fail", "uncertain")
           or not isinstance(row.get("reason"), str)
           or (row.get("verdict") != "pass" and not row["reason"].strip())
           for row in findings):
        raise TranslationContractError("semantic audit verdict invalid")
    return response


def semantic_repair_request(request: dict, audit: dict, *, attempt: int = 1,
                            max_attempts: int = 2) -> dict:
    """Bounded, evidence-backed repair task for an external translator.

    No model invocation occurs here. Canonical IDs and Chinese facts stay locked.
    """
    validate_semantic_audit(request, audit)
    if not 1 <= attempt <= max_attempts:
        raise TranslationContractError("semantic repair attempt limit exceeded")
    findings = {row["event_id"]: row for row in audit["findings"]}
    targets = []
    for pair in request["pairs"]:
        finding = findings[pair["event_id"]]
        if finding["verdict"] != "pass":
            targets.append({**pair, "verdict": finding["verdict"],
                            "audit_reason": finding["reason"]})
    payload = {
        "schema_version": 1,
        "audit_request_sha256": request["audit_request_sha256"],
        "attempt": attempt,
        "max_attempts": max_attempts,
        "target_events": targets,
        "verified_source_context": [
            row for row in request.get("verified_source_context", [])
            if row.get("event_id") in {event["event_id"] for event in targets}
        ],
        "instruction": (
            "Human-verified source context is authoritative about meaning and referents. "
            "Do not substitute a different creature or named entity against verified context. "
            "Correct ONLY target_events. Preserve event IDs and Chinese meaning, "
            "including negations, numbers, science terms and names. "
            "Return translations array of {event_id,text_my}. "
            "Do not alter canonical IDs, timing or source facts."
        ),
    }
    payload["request_hash"] = digest(payload)
    return payload


def apply_semantic_repairs(request: dict, repair: dict,
                           repaired_response: dict) -> dict[str, str]:
    """Return complete translations with reviewed non-target rows untouched."""
    if repair.get("audit_request_sha256") != request.get("audit_request_sha256"):
        raise TranslationContractError("repair bound to different audit")
    fixed = validate_response(repair, repaired_response)
    original = {row["event_id"]: row["text_my"] for row in request["pairs"]}
    unchanged = [event_id for event_id, value in fixed.items()
                 if value == original.get(event_id)]
    if unchanged:
        raise TranslationContractError("repair did not change flagged translation IDs: "
                                       + ",".join(sorted(unchanged)))
    if not set(fixed).issubset(original):
        raise TranslationContractError("unknown repair ID")
    return {**original, **fixed}


def validate_response(request: dict, response: dict) -> dict[str, str]:
    if not isinstance(response, dict) or set(response) != {"translations"}:
        raise TranslationContractError("only translations field is allowed")
    rows = response["translations"]
    if not isinstance(rows, list):
        raise TranslationContractError("translations must be array")
    expected = [e["event_id"] for e in request["target_events"]]
    if len(set(expected)) != len(expected):
        raise TranslationContractError("duplicate target IDs")
    got: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"event_id", "text_my"}:
            raise TranslationContractError("invalid translation row schema")
        key = row["event_id"]
        if not isinstance(key, str) or key in got:
            raise TranslationContractError("duplicate/invalid response IDs")
        value = row["text_my"]
        if not isinstance(value, str) or not value.strip():
            raise TranslationContractError("empty/non-text translation")
        if "\ufffd" in value:
            raise TranslationContractError("replacement glyph not allowed")
        # A nonempty Chinese or English echo is not a Burmese translation.
        # Leave scientific names in Latin script, but require Burmese text too.
        if not re.search(r"[\u1000-\u109f\uaa60-\uaa7f]", value):
            raise TranslationContractError("translation has no Myanmar-script text")
        got[key] = value.strip()
    if set(got) != set(expected):
        raise TranslationContractError("target IDs missing or unexpected")
    return got


def retry_translator(request: dict, invoke: Callable[[dict], dict],
                     *, sleep: Callable[[float], None] = time.sleep) -> tuple[dict[str, str], list[dict]]:
    """Only network/timeout failures can retry; caller supplies transport."""
    log = []
    for attempt in range(1, 4):
        try:
            answer = invoke(request)
            return validate_response(request, answer), log
        except (TranslationNetworkError, TimeoutError, ConnectionError) as error:
            log.append({
                "attempt_no": attempt, "request_hash": request["request_hash"],
                "error_type": type(error).__name__,
            })
            if attempt >= 3:
                raise TranslationExhaustedError("translation network retry exhausted") from error
            sleep(float(attempt))
        # Invalid JSON/schema/IDs are not network exceptions and never retry.
    raise TranslationExhaustedError("unreachable")


def validate_translation_bundle(ledger: dict, bundle: dict) -> dict[str, str]:
    """Validate orchestrator result; can combine separately validated batches."""
    if not isinstance(bundle, dict):
        raise TranslationContractError("bundle must be object")
    if bundle.get("canonical_lock") != ledger["canonical_lock"]:
        raise TranslationContractError("canonical lock differs")
    if bundle.get("fused_events_sha256") != digest(ledger):
        raise TranslationContractError("fused hash differs")
    allowed = {"canonical_lock", "fused_events_sha256", "translations",
               "title_my", "caption_my", "visibility", "render_preset", "source_summary"}
    if set(bundle) - allowed:
        raise TranslationContractError("unrecognized localization keys")
    response = {"translations": bundle.get("translations")}
    request = {"target_events": [{"event_id": e["event_id"]} for e in translation_targets(ledger)]}
    return validate_response(request, response)


def _content_type(ledger: dict) -> str:
    kinds = {e["source_kind"] for e in ledger["canonical_events"] if e["fact_disposition"] == "translate_target"}
    has_speech = bool(kinds & {"speech", "ocr_asr_aligned"})
    has_visual = bool(kinds & {"visual_text", "ocr_asr_aligned"})
    if has_speech and has_visual:
        return "mixed"
    if has_speech:
        return "speech"
    if has_visual:
        return "visual_text"
    return "visual_only"


def build_timeline(ledger: dict, bundle: dict) -> tuple[dict, dict]:
    translations = validate_translation_bundle(ledger, bundle)
    events = []
    for event in ledger["canonical_events"]:
        if event["fact_disposition"] == "excluded_with_reason":
            continue
        entry = {**event}
        text = translations.get(event["event_id"])
        entry["localization"] = {
            "text_my": text or "",
            "status": "translated" if text else "review_required",
        }
        entry["layout"] = {
            "mode": "avoid_original", "zone": "safe_caption",
            "style": "callout" if event["role"] == "callout" else "primary",
        }
        events.append(entry)
    timeline = {
        "schema_version": 2,
        "source_video_sha256": ledger["source_video_sha256"],
        "fused_events_sha256": digest(ledger),
        "canonical_lock": ledger["canonical_lock"],
        "duration_s": ledger["duration_s"],
        "render_preset": bundle.get("render_preset", "dynamic_clean"),
        "events": events, "caption_my": str(bundle.get("caption_my", "")).strip(),
        "title_my": str(bundle.get("title_my", "")).strip(),
        "visibility": str(bundle.get("visibility", "PUBLIC")).upper(),
        "content_type": _content_type(ledger),
        "translation_bundle_sha256": digest(bundle),
    }
    if timeline["render_preset"] not in ("dynamic_clean", "dynamic_fun"):
        raise TranslationContractError("unknown render preset")
    if timeline["visibility"] not in ("PUBLIC", "PRIVATE", "FRIENDS"):
        raise TranslationContractError("invalid visibility")
    if not timeline["caption_my"]:
        raise TranslationContractError("caption_my required")
    # Legacy projection intentionally contains primary subtitle cues only.
    cues = [{"start": e["start"], "end": e["end"], "text_my": e["localization"]["text_my"]}
            for e in events if e["role"] == "primary_subtitle"
            and e["localization"]["status"] == "translated"]
    frame_refs = []
    transcript = []
    for e in events:
        if e["source_kind"] in ("visual_text", "ocr_asr_aligned"):
            frame_refs.extend([round(float(e["start"]), 3)])
        if e["source_kind"] in ("speech", "ocr_asr_aligned"):
            transcript.append(e["text_zh"])
    if not frame_refs and not transcript:
        # Existing contact sheet samples at least the middle of the video.
        frame_refs = [round(timeline["duration_s"] / 2, 3)]
    projection = {
        "schema_version": 2, "content_type": timeline["content_type"],
        "title_my": timeline["title_my"], "caption_my": timeline["caption_my"],
        "visibility": timeline["visibility"],
        "source_summary": str(bundle.get("source_summary", "")),
        "caption_basis": {
            "type": timeline["content_type"],
            "reason": "Dynamic timeline projection: direct source-event evidence",
            "source_frames": sorted(set(frame_refs)),
            "source_transcript": transcript,
        },
        "cues": cues,
        "dynamic_timeline_hash": digest(timeline),
    }
    return timeline, projection


def revise_layout(job_dir, *, event_id: str, mode: str,
                  verification_frame_refs: list[str] | None = None) -> dict:
    """Human-verifiable non-destructive layout revision, before render/export."""
    from pathlib import Path
    from .common import atomic_json, read_json
    from .subtitle_layout import verified_backplate
    path = Path(job_dir) / "localization" / "subtitle_timeline.json"
    legacy_path = Path(job_dir) / "localization" / "localization.json"
    timeline = read_json(path)
    legacy = read_json(legacy_path)
    if not timeline or not check_projection(timeline, legacy):
        raise TranslationContractError("current timeline/projection mismatch")
    if mode not in ("avoid_original", "retain_original", "cover_and_replace"):
        raise TranslationContractError("invalid layout mode")
    candidates = [e for e in timeline["events"] if e["event_id"] == event_id]
    if len(candidates) != 1:
        raise TranslationContractError("unknown event ID")
    event = candidates[0]
    if mode == "cover_and_replace":
        refs = verification_frame_refs or []
        if len(set(refs)) < 2 or any(not x.startswith("analysis/frames/") for x in refs):
            raise TranslationContractError("cover mode requires two independent local frame refs")
        for ref in refs:
            if not (Path(job_dir) / ref).is_file():
                raise TranslationContractError("cover evidence frame missing")
        event["layout"] = {
            "mode": mode, "zone": "verified_text_roi", "style": event["role"],
            "opaque_rect_verified": True, "verification_frame_refs": refs,
        }
        if not verified_backplate(event):
            raise TranslationContractError("opaque backplate not verified")
    else:
        event["layout"] = {"mode": mode, "zone": "safe_caption", "style": event["role"]}
    timeline["layout_revision_parent_sha256"] = digest(read_json(path))
    legacy["dynamic_timeline_hash"] = digest(timeline)
    atomic_json(path, timeline)
    atomic_json(legacy_path, legacy)
    return timeline


def check_projection(timeline: dict, projection: dict) -> bool:
    expected = [
        {"start": e["start"], "end": e["end"], "text_my": e["localization"]["text_my"]}
        for e in timeline["events"]
        if e["role"] == "primary_subtitle" and e["localization"]["status"] == "translated"
    ]
    return (projection.get("dynamic_timeline_hash") == digest(timeline)
            and projection.get("cues") == expected
            and projection.get("caption_my") == timeline.get("caption_my")
            and projection.get("visibility") == timeline.get("visibility"))
