from __future__ import annotations

from pathlib import Path

from .common import atomic_json, read_json

VALID_TYPES = {"speech", "visual_text", "mixed", "visual_only"}


def _validate_caption_basis(data: dict, *, content_type: str, duration: float) -> dict:
    basis = data.get("caption_basis")
    if not isinstance(basis, dict):
        raise ValueError("caption_basis is required")
    basis_type = str(basis.get("type", "")).strip()
    if basis_type not in VALID_TYPES:
        raise ValueError(f"invalid caption_basis.type: {basis_type}")
    if basis_type != content_type:
        raise ValueError("caption_basis.type must match content_type")
    reason = str(basis.get("reason", "")).strip()
    if not reason:
        raise ValueError("caption_basis.reason is required")

    frames = []
    for raw in basis.get("source_frames") or []:
        ts = float(raw)
        if ts < 0 or ts > duration:
            raise ValueError(f"caption_basis source frame out of range: {ts}")
        frames.append(round(ts, 3))

    transcript = []
    for raw in basis.get("source_transcript") or []:
        text = str(raw).strip()
        if text:
            transcript.append(text)

    if not frames and not transcript:
        raise ValueError("caption_basis requires source_frames or source_transcript evidence")
    if basis_type == "visual_only" and not frames:
        raise ValueError("visual_only caption_basis requires source_frames")
    if basis_type == "speech" and not transcript:
        raise ValueError("speech caption_basis requires source_transcript")

    return {
        "type": basis_type,
        "reason": reason,
        "source_frames": frames,
        "source_transcript": transcript,
    }


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
    caption_basis = _validate_caption_basis(data, content_type=ctype, duration=duration)
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
        "schema_version": 2,
        "content_type": ctype,
        "title_my": title,
        "caption_my": caption,
        "caption_basis": caption_basis,
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
