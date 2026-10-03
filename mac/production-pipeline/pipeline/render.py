from __future__ import annotations

import json
import shutil
from pathlib import Path

from .common import ROOT, atomic_json, run, sha256_file


def _render_overlay(text: str, out: Path, renderer: Path) -> None:
    txt = out.with_suffix(".txt")
    txt.write_text(text + "\n", encoding="utf-8")
    run([str(renderer), str(txt), str(out), "900", "260", "42"])


def render(job_dir: Path) -> dict:
    loc = json.load(open(job_dir / "localization" / "localization.json", encoding="utf-8"))
    source = json.load(open(job_dir / "source" / "source.json", encoding="utf-8"))
    video = Path(source["video_path"])
    prod = job_dir / "production"
    overlays = prod / "overlays"
    overlays.mkdir(parents=True, exist_ok=True)
    renderer = ROOT / "runtime" / "bin" / "render_text"
    if not renderer.exists():
        raise RuntimeError("render_text binary missing; run scripts/bootstrap.sh")

    cues = loc.get("cues", [])
    overlay_paths = []
    for idx, cue in enumerate(cues, 1):
        path = overlays / f"cue-{idx:03d}.png"
        _render_overlay(cue["text_my"], path, renderer)
        overlay_paths.append(path)

    out = prod / "video.my.mp4"
    args = ["ffmpeg", "-v", "error", "-y", "-i", str(video)]
    for path in overlay_paths:
        args += ["-loop", "1", "-framerate", "30", "-i", str(path)]

    graph = "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black[v0]"
    prev = "v0"
    for idx, cue in enumerate(cues, 1):
        nxt = f"v{idx}"
        graph += (
            f";[{prev}][{idx}:v]overlay=(W-w)/2:H-h-300:"
            f"enable='between(t,{cue['start']},{cue['end']})'[{nxt}]"
        )
        prev = nxt

    args += [
        "-filter_complex", graph,
        "-map", f"[{prev}]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(out),
    ]
    run(args, timeout=240)

    caption = prod / "caption.my.txt"
    caption.write_text(loc["caption_my"].strip() + "\n", encoding="utf-8")
    metadata = {
        "title": loc["title_my"],
        "visibility": loc["visibility"],
        "source_aweme_id": source["aweme_id"],
        "source_url": source["source_url"],
        "content_type": loc["content_type"],
        "audio": "original",
    }
    atomic_json(prod / "metadata.json", metadata)

    preview = prod / "preview.jpg"
    duration = json.load(open(job_dir / "analysis" / "analysis.json", encoding="utf-8"))["duration"]
    run([
        "ffmpeg", "-v", "error", "-y", "-ss", f"{duration/2:.3f}",
        "-i", str(out), "-frames:v", "1", str(preview),
    ])
    result = {
        "video": str(out),
        "caption": str(caption),
        "metadata": str(prod / "metadata.json"),
        "preview": str(preview),
        "sha256": {
            "video": sha256_file(out),
            "caption": sha256_file(caption),
            "metadata": sha256_file(prod / "metadata.json"),
        },
    }
    atomic_json(prod / "render-result.json", result)
    return result
