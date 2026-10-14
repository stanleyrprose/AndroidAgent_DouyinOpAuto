"""Opt-in, non-publishing Burmese human-review preview renderer.

Never promotes a translation draft to an accepted production subtitle timeline.
Private media, translation JSON and Telegram receipts stay outside Git.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import shutil
import subprocess
from pathlib import Path


class ReviewContractError(ValueError):
    pass


def validate_draft(payload: dict, *, duration: float) -> list[dict]:
    if payload.get("status") != "DRAFT_UNVERIFIED_NATIVE_AND_TIMING":
        raise ReviewContractError("review-only draft status required")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise ReviewContractError("missing events")
    ids = set()
    for e in events:
        if not isinstance(e, dict) or e.get("event_id") in ids or not e.get("event_id"):
            raise ReviewContractError("duplicate/missing event ID")
        ids.add(e["event_id"])
        if e.get("role") not in {"callout", "primary_subtitle"}:
            raise ReviewContractError("unknown event role")
        start, end = e.get("start"), e.get("end")
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (start, end)):
            raise ReviewContractError("invalid timing")
        if not 0 <= start < end <= duration + 0.01:
            raise ReviewContractError("event outside source")
        for key in ("text_zh", "normal_my", "funny_my"):
            if not isinstance(e.get(key), str) or not e[key].strip():
                raise ReviewContractError(f"missing {key}")
    return events


def resolve_speech_segments(events: list[dict], duration: float) -> list[tuple[float, float, int | None]]:
    """Temporary latest-start-wins preview; never edits GT or approved timings."""
    speech = [e for e in events if e["role"] == "primary_subtitle"]
    bounds = sorted({0.0, duration, *(v for e in speech for v in (e["start"], e["end"]))})
    segments: list[tuple[float, float, int | None]] = []
    for a, b in zip(bounds, bounds[1:]):
        active = [e for e in speech if e["start"] <= a and e["end"] >= b]
        chosen = max(active, key=lambda e: (e["start"], e["fusion_index"])) if active else None
        index = chosen["fusion_index"] if chosen else None
        if segments and segments[-1][2] == index:
            segments[-1] = (segments[-1][0], b, index)
        else:
            segments.append((a, b, index))
    return segments


def _run(argv: list[str], *, timeout: int = 240) -> None:
    subprocess.run(argv, check=True, timeout=timeout, stdout=subprocess.DEVNULL)


def render_review(source: Path, draft: Path, output_dir: Path, *, variant: str) -> Path:
    """Review preview only: speech track, original audio, no publish/export action."""
    if variant not in {"normal", "funny"}:
        raise ReviewContractError("variant must be normal or funny")
    for command in ("ffprobe", "ffmpeg", "pango-view", "magick"):
        if not shutil.which(command):
            raise RuntimeError(f"missing rendering dependency: {command}")
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(source)
    ]))
    duration = float(probe["format"]["duration"])
    events = validate_draft(json.loads(draft.read_text()), duration=duration)
    segments = resolve_speech_segments(events, duration)
    output_dir.mkdir(parents=True, exist_ok=True)
    work = output_dir / f"overlay-{variant}"
    work.mkdir(exist_ok=True)
    lookup = {e["fusion_index"]: e for e in events if e["role"] == "primary_subtitle"}
    images = {}
    for index in {segment[2] for segment in segments}:
        target = work / f"{index if index is not None else 0:03}.png"
        images[index] = target
        if index is None:
            _run(["magick", "-size", "1280x720", "xc:none", str(target)])
            continue
        text = html.escape(lookup[index][variant + "_my"])
        markup = f'<span font_family="Noto Sans Myanmar" font_size="26000" foreground="white">{text}</span>'
        pane = work / f"text-{index:03}.png"
        _run(["pango-view", "--no-display", "--background=transparent", "--markup",
              "--align=center", "--width=1120", "--wrap=word-char", "--margin=8",
              "--text=" + markup, "--output=" + str(pane)])
        _run(["magick", "-size", "1280x720", "xc:none", "-fill", "#00000099",
              "-draw", "roundrectangle 65,542 1215,688 20,20", str(pane),
              "-gravity", "south", "-geometry", "+0+36", "-composite", str(target)])
    concat = work / "segments.ffconcat"
    lines = ["ffconcat version 1.0"]
    for a, b, index in segments:
        lines.extend([f"file '{images[index]}'", f"duration {b-a:.6f}"])
    lines.append(f"file '{images[segments[-1][2]]}'")
    concat.write_text("\n".join(lines) + "\n")
    dest = output_dir / f"{variant.upper()}-HUMAN-REVIEW-UNVERIFIED.mp4"
    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
          "-f", "concat", "-safe", "0", "-i", str(concat), "-filter_complex",
          "[0:v]fps=24,scale=1280:720:flags=bicubic,format=yuv420p[base];"
          "[1:v]fps=24,format=rgba[cap];"
          "[base][cap]overlay=0:0:shortest=1:format=auto,format=yuv420p[v]",
          "-map", "[v]", "-map", "0:a?", "-t", str(duration), "-c:v", "libx264",
          "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-b:a", "96k",
          "-movflags", "+faststart", str(dest)])
    (output_dir / f"{variant}-review-manifest.json").write_text(json.dumps({
        "status": "HUMAN_REVIEW_ONLY", "source": str(source), "variant": variant,
        "video": str(dest), "translated_speech_events": len(lookup),
        "visual_callouts_localized": False, "native_review_approved": False,
        "timing_approved": False, "publish_allowed": False,
    }, ensure_ascii=False, indent=2) + "\n")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--variant", choices=("normal", "funny", "both"), default="both")
    args = parser.parse_args()
    for variant in (("normal", "funny") if args.variant == "both" else (args.variant,)):
        print(render_review(args.source, args.draft, args.output_dir, variant=variant))


if __name__ == "__main__":
    main()
