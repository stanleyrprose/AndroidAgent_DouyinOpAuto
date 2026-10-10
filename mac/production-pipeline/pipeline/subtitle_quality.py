"""Fail-closed, inspectable quality gate for new subtitle production jobs."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .common import atomic_json, read_json, sha256_file
from .subtitle_events import digest, verify_ledger
from .subtitle_localization import check_projection

BLOCKED = "BLOCKED"
REVIEW = "REVIEW_REQUIRED"


def review_status(codes: list[str]) -> str:
    if any(c.startswith("BLOCKED_") for c in codes):
        return BLOCKED
    if any(c.startswith("REVIEW_REQUIRED") or c in ("OCR_BUDGET_EXHAUSTED", "OCR_UNAVAILABLE", "OCR_COVERAGE_INCOMPLETE")
           for c in codes):
        return REVIEW
    return "PASS"


def evaluate(job_dir: Path, *, after_render: bool = False) -> dict:
    """Deterministic machine-verifiable checks, with conservative review on ambiguity."""
    analysis = read_json(job_dir / "analysis" / "analysis.json", {}) or {}
    ledger = read_json(job_dir / "analysis" / "fused_events.zh.json", {}) or {}
    timeline = read_json(job_dir / "localization" / "subtitle_timeline.json", {}) or {}
    legacy = read_json(job_dir / "localization" / "localization.json", {}) or {}
    source = read_json(job_dir / "source" / "source.json", {}) or {}
    codes: list[str] = []
    detail: list[dict] = []
    duration = float(analysis.get("duration", 0))
    source_video = Path(source.get("video_path", "__source_missing__"))
    if not source_video.is_file() or not ledger:
        codes.append("BLOCKED_ARTIFACT_MISMATCH")
    else:
        if sha256_file(source_video) != ledger.get("source_video_sha256"):
            codes.append("BLOCKED_ARTIFACT_MISMATCH")
        for err in verify_ledger(ledger):
            codes.append("BLOCKED_INVALID_EXCLUSION" if "EXCLUSION" in err else "BLOCKED_ARTIFACT_MISMATCH")
            detail.append({"ledger_error": err})
    ocr = analysis.get("dynamic_ocr", {})
    if ocr.get("budget_exhausted") or ocr.get("coverage_incomplete"):
        codes.append("OCR_BUDGET_EXHAUSTED" if ocr.get("budget_exhausted") else "OCR_COVERAGE_INCOMPLETE")
        has_reliable_asr = bool(analysis.get("meaningful_speech"))
        if not has_reliable_asr:
            codes.append("BLOCKED_OCR_COVERAGE_VISUAL")
        elif any(e["source_kind"] == "visual_text" for e in ledger.get("canonical_events", [])):
            codes.append("REVIEW_REQUIRED_OCR_COVERAGE")
        else:
            codes.append("REVIEW_REQUIRED_SPEECH_ONLY")
        detail.append({
            "missing_windows": ocr.get("unscanned", []),
            "ocr_budget_limit": ocr.get("ocr_budget_limit_per_minute"),
            "ocr_calls": ocr.get("ocr_calls"),
        })
    if ocr.get("error"):
        codes.append("OCR_UNAVAILABLE")
        codes.append("BLOCKED_OCR_COVERAGE_VISUAL" if not analysis.get("meaningful_speech")
                     else "REVIEW_REQUIRED_OCR_COVERAGE")
    if not analysis.get("meaningful_speech") and not analysis.get("dynamic_ocr", {}).get("ocr_observations"):
        # Cannot distinguish truly text-free video from total OCR miss without review.
        codes.append("REVIEW_REQUIRED_OCR")
    if timeline:
        if (timeline.get("fused_events_sha256") != digest(ledger)
            or timeline.get("canonical_lock") != ledger.get("canonical_lock")
            or timeline.get("source_video_sha256") != ledger.get("source_video_sha256")
            or not check_projection(timeline, legacy)):
            codes.append("BLOCKED_ARTIFACT_MISMATCH")
        eligible = [e for e in ledger.get("canonical_events", [])
                    if e.get("fact_disposition") == "translate_target"]
        output_ids = [e.get("event_id") for e in timeline.get("events", [])
                      if e.get("fact_disposition") == "translate_target"]
        if len(output_ids) != len(set(output_ids)) or set(output_ids) != {e["event_id"] for e in eligible}:
            codes.append("BLOCKED_UNRESOLVED_EVENT")
        for e in timeline.get("events", []):
            eid = e.get("event_id")
            if e.get("fact_disposition") == "review_required" or e.get("review_flags"):
                codes.append("REVIEW_REQUIRED_OCR")
                detail.append({"event_id": eid, "review_flags": e.get("review_flags", [])})
            if e.get("fact_disposition") == "translate_target" and not e.get("localization", {}).get("text_my"):
                codes.append("BLOCKED_UNRESOLVED_EVENT")
                detail.append({"event_id": eid, "reason": "MISSING_TRANSLATION"})
            start, end = float(e.get("start", -1)), float(e.get("end", -1))
            if start < 0 or end <= start or end > duration + .01:
                codes.append("BLOCKED_INVALID_TIMELINE")
            if e.get("layout", {}).get("mode") not in ("avoid_original", "retain_original", "cover_and_replace"):
                codes.append("BLOCKED_INVALID_LAYOUT")
            from .subtitle_layout import plan_position, verified_backplate
            from .subtitle_render import _transform
            streams = analysis.get("probe", {}).get("streams", [])
            video_stream = next((x for x in streams if x.get("codec_type") == "video"), {})
            if video_stream.get("width") and video_stream.get("height"):
                placement = plan_position(e, _transform(int(video_stream["width"]), int(video_stream["height"])))
                if placement["collision"]:
                    codes.append("REVIEW_REQUIRED_LAYOUT")
            if e.get("layout", {}).get("mode") == "cover_and_replace" and not verified_backplate(e):
                codes.append("REVIEW_REQUIRED_LAYOUT")
            # User-visible main captions must never mask their own text with fake whole-film summaries.
            if e.get("role") == "callout" and any(
                other.get("role") == "primary_subtitle" and
                max(other["start"], start) < min(other["end"], end)
                for other in timeline["events"]
            ):
                codes.append("REVIEW_REQUIRED_LAYOUT")
        if len(eligible) >= 2:
            primary = [e for e in timeline["events"]
                       if e.get("role") == "primary_subtitle" and e.get("localization", {}).get("text_my")]
            if len(primary) == 1 and (primary[0]["end"] - primary[0]["start"]) >= .8 * max(.01, duration):
                codes.append("BLOCKED_DYNAMIC_CUE_COLLAPSE")
            if len(primary) == 0 and eligible:
                codes.append("REVIEW_REQUIRED_LAYOUT")
    else:
        codes.append("BLOCKED_ARTIFACT_MISMATCH")
    if after_render:
        product = job_dir / "production" / "video.my.mp4"
        result = read_json(job_dir / "production" / "render-result.json", {}) or {}
        if not product.is_file() or not result.get("sha256") or (
            result.get("sha256", {}).get("video") != sha256_file(product)
        ):
            codes.append("BLOCKED_ARTIFACT_MISMATCH")
        if not result.get("source_to_output_affine_matrix"):
            codes.append("BLOCKED_ARTIFACT_MISMATCH")
        if result.get("timeline_sha256") != digest(timeline):
            codes.append("BLOCKED_ARTIFACT_MISMATCH")
        caption_path = job_dir / "production" / "caption.my.txt"
        if (not caption_path.is_file() or
            result.get("sha256", {}).get("caption") != sha256_file(caption_path) or
            caption_path.read_text(encoding="utf-8").strip() != timeline.get("caption_my")):
            codes.append("BLOCKED_ARTIFACT_MISMATCH")
    codes = sorted(set(codes))
    evidence_revision = digest({
        "source_sha": ledger.get("source_video_sha256"),
        "fused_lock": ledger.get("canonical_lock"), "timeline_sha": digest(timeline),
        "ocr_diagnostics_sha": digest(ocr),
    })[:20]
    review_record = read_json(job_dir / "production" / "quality-approvals.json", {}) or {}
    approvals = [x for x in review_record.get("approvals", [])
                 if x.get("evidence_revision") == evidence_revision]
    approved_codes = {x["code"] for x in approvals}
    # Only explicitly reviewable warnings can be cleared, never hard errors.
    remaining = [c for c in codes
                 if not (c.startswith("REVIEW_REQUIRED") and c in approved_codes)]
    if not any(c.startswith("REVIEW_REQUIRED") for c in remaining):
        if "OCR_BUDGET_EXHAUSTED" in remaining and any(
            c.startswith("REVIEW_REQUIRED") for c in approved_codes
        ):
            remaining.remove("OCR_BUDGET_EXHAUSTED")
        for warning in ("OCR_UNAVAILABLE", "OCR_COVERAGE_INCOMPLETE"):
            if warning in remaining and any(
                c.startswith("REVIEW_REQUIRED") for c in approved_codes
            ):
                remaining.remove(warning)
    codes = remaining
    report = {
        "schema_version": 1,
        "revision": digest({
            "evidence_revision": evidence_revision,
            "codes": codes, "after_render": after_render,
        })[:16],
        "evidence_revision": evidence_revision,
        "review_approvals": [x for x in approvals if x.get("code") in approved_codes],
        "job_id": job_dir.name,
        "quality_stage": "Q3_POST_RENDER" if after_render else "Q1_Q2",
        "status": review_status(codes), "codes": codes,
        "source_video_sha256": ledger.get("source_video_sha256"),
        "fused_events_sha256": digest(ledger) if ledger else None,
        "timeline_sha256": digest(timeline) if timeline else None,
        "ocr_budget_limit": ocr.get("ocr_budget_limit_per_minute"),
        "ocr_calls": ocr.get("ocr_calls", 0),
        "ocr_unchecked_windows": ocr.get("unscanned", []),
        "classification_evidence": {
            "meaningful_speech": bool(analysis.get("meaningful_speech")),
            "recognized_visual": ocr.get("ocr_observations", 0),
        },
        "details": detail,
        "next_action": "Review evidence and repair/re-generate in Mac before export"
                       if codes else "Export permitted",
    }
    atomic_json(job_dir / "production" / "quality_report.json", report)
    return report


def require_pass(job_dir: Path) -> dict:
    report = read_json(job_dir / "production" / "quality_report.json", {})
    if not report or report.get("status") != "PASS" or report.get("quality_stage") != "Q3_POST_RENDER":
        raise RuntimeError("new dynamic subtitle job export blocked: quality report is not Q3 PASS")
    # Reevaluate to prevent stale PASS after timeline/source/artifact modification.
    checked = evaluate(job_dir, after_render=True)
    if checked["status"] != "PASS":
        raise RuntimeError("new dynamic subtitle job export blocked: " + ",".join(checked["codes"]))
    return checked


def approve_review(job_dir: Path, *, code: str, reviewer: str, reason: str) -> dict:
    if not code.startswith("REVIEW_REQUIRED"):
        raise ValueError("only REVIEW_REQUIRED conditions can be approved")
    if not reviewer.strip() or len(reason.strip()) < 12:
        raise ValueError("named reviewer and sufficient evidence description required")
    report = read_json(job_dir / "production" / "quality_report.json", {}) or {}
    if code not in report.get("codes", []):
        raise ValueError("code not pending in current quality report")
    evidence_rev = report.get("evidence_revision")
    if not evidence_rev:
        raise ValueError("missing evidence lock")
    path = job_dir / "production" / "quality-approvals.json"
    data = read_json(path, {"schema_version": 1, "approvals": []}) or {"schema_version": 1, "approvals": []}
    if any(x["code"] == code and x["evidence_revision"] == evidence_rev
           for x in data["approvals"]):
        return data
    from datetime import datetime, timezone
    data["approvals"].append({
        "code": code, "evidence_revision": evidence_rev,
        "reviewer": reviewer.strip(), "reason": reason.strip(),
        "approved_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    atomic_json(path, data)
    return data


def list_quality_queue(jobs_dir: Path, statuses: set[str] | None = None) -> list[dict]:
    statuses = {x.lower() for x in statuses} if statuses else {"pending", "failed", "blocked"}
    out = []
    if not jobs_dir.exists():
        return out
    for job in sorted(jobs_dir.iterdir()):
        if not job.is_dir():
            continue
        qa = read_json(job / "production" / "quality_report.json", {}) or {}
        notice = read_json(job / "production" / "quality-notify.json", {}) or {}
        alerts = notice.get("alerts", [])
        problem = qa.get("status") in ("BLOCKED", "REVIEW_REQUIRED")
        unsent = [a for a in alerts if a.get("status") in ("PENDING", "FAILED")]
        if (problem and "blocked" in statuses or
            any(a.get("status", "").lower() in statuses for a in unsent)):
            out.append({
                "job_id": job.name, "quality_status": qa.get("status"),
                "quality_codes": qa.get("codes", []),
                "unsent_alerts": [
                    {"alert_id": a.get("alert_id"), "status": a.get("status"),
                     "attempts": a.get("attempts", 0)}
                    for a in unsent
                ],
            })
    return out
