from __future__ import annotations

from pathlib import Path

from .common import atomic_json, read_json

VALID_TYPES = {"speech", "visual_text", "mixed", "visual_only"}


def validate(data: dict, duration: float) -> dict:
    ctype = data.get("content_type")
    if ctype not in VALID_TYPES:
        raise ValueError(f"invalid content_type: {ctype}")
    title = str(data.get("title_my", "")).strip()
    caption = str(data.get("caption_my", "")).strip()
    if not caption:
        raise ValueError("caption_my is required")
    vis = str(data.get("visibility", "PUBLIC")).upper()
    if vis not in {"PRIVATE", "FRIENDS", "PUBLIC"}:
        raise ValueError(f"invalid visibility: {vis}")
    cues = data.get("cues") or []
    normalized = []
    for row in cues:
        text = str(row.get("text_my", "")).strip()
        if not text:
            continue
        start = max(0.0, float(row.get("start", 0.0)))
        end = min(duration, float(row.get("end", duration)))
        if end <= start:
            raise ValueError(f"invalid cue range: {start}-{end}")
        normalized.append({"start": round(start, 3), "end": round(end, 3), "text_my": text})
    if not normalized and ctype != "visual_only":
        raise ValueError("at least one non-empty cue is required")
    return {
        "schema_version": 1,
        "content_type": ctype,
        "title_my": title,
        "caption_my": caption,
        "visibility": vis,
        "source_summary": str(data.get("source_summary", "")).strip(),
        "cues": normalized,
    }


def save(job_dir: Path, data: dict) -> dict:
    analysis = read_json(job_dir / "analysis" / "analysis.json")
    if not analysis:
        raise RuntimeError("analysis.json missing")
    validated = validate(data, float(analysis["duration"]))
    atomic_json(job_dir / "localization" / "localization.json", validated)
    return validated
