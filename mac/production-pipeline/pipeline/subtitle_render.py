"""Mac one-shot dynamic subtitles using a single Swift batch render and FFmpeg."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .common import ROOT, atomic_json, read_json, run, sha256_file
from .subtitle_events import digest
from .subtitle_localization import check_projection
from .subtitle_layout import plan_position, verified_backplate, source_box_to_output


def _source_geometry(video: Path) -> tuple[int, int]:
    info = json.loads(run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", str(video),
    ]).stdout)
    row = info["streams"][0]
    return int(row["width"]), int(row["height"])


def _transform(width: int, height: int) -> dict:
    scale = min(1080 / width, 1920 / height)
    ox = (1080 - width * scale) / 2
    oy = (1920 - height * scale) / 2
    return {
        "source_dimensions": [width, height], "output_dimensions": [1080, 1920],
        "coordinate_system": "source_top_left_normalized",
        "source_to_output_affine_matrix": [
            [scale, 0, ox], [0, scale, oy], [0, 0, 1],
        ],
        "pixel_aspect": "1:1", "orientation": "ffmpeg_autorotate",
    }


def render_dynamic(job_dir: Path) -> dict:
    from .subtitle_quality import evaluate
    from .subtitle_notify import notify_if_blocked
    before = evaluate(job_dir)
    if before["status"] == "BLOCKED":
        notify_if_blocked(job_dir, before)
        raise RuntimeError("BLOCKED: subtitle timeline failed pre-render QA")
    timeline_path = job_dir / "localization" / "subtitle_timeline.json"
    timeline = read_json(timeline_path)
    projection = read_json(job_dir / "localization" / "localization.json")
    if not check_projection(timeline, projection):
        raise RuntimeError("BLOCKED_ARTIFACT_MISMATCH")
    source = read_json(job_dir / "source" / "source.json")
    video = Path(source["video_path"])
    if sha256_file(video) != timeline["source_video_sha256"]:
        raise RuntimeError("BLOCKED_ARTIFACT_MISMATCH: source SHA")
    production = job_dir / "production"
    overlays = production / "overlays-dynamic"
    overlays.mkdir(parents=True, exist_ok=True)
    binpath = ROOT / "runtime" / "bin" / "render_text_batch"
    if not binpath.is_file():
        raise RuntimeError("render_text_batch missing; run scripts/bootstrap.sh")
    t0 = time.monotonic()
    batch = json.loads(run([str(binpath), str(timeline_path), str(overlays)], timeout=300).stdout)
    swift_seconds = time.monotonic() - t0
    by_id = {x["event_id"]: x["asset_path"] for x in batch["assets"]}
    active = [e for e in timeline["events"] if e.get("localization", {}).get("text_my")]
    if set(by_id) != {e["event_id"] for e in active}:
        raise RuntimeError("BLOCKED_ARTIFACT_MISMATCH: overlay cardinality")
    w, h = _source_geometry(video)
    geometry = _transform(w, h)
    output = production / "video.my.mp4"
    command = ["ffmpeg", "-v", "error", "-y", "-i", str(video)]
    for event in active:
        command += ["-loop", "1", "-framerate", "30", "-i", by_id[event["event_id"]]]
    graph = "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black[v0]"
    prev = "v0"
    placements = []
    for index, event in enumerate(active, 1):
        after = f"v{index}"
        start, end = float(event["start"]), float(event["end"])
        placed = plan_position(event, geometry)
        if placed["collision"]:
            raise RuntimeError("REVIEW_REQUIRED_LAYOUT: no safe overlay region")
        if event.get("layout", {}).get("mode") == "cover_and_replace":
            if not verified_backplate(event):
                raise RuntimeError("REVIEW_REQUIRED_LAYOUT: opaque backplate not verified")
            box = source_box_to_output(event.get("ocr_bbox_norm"), geometry)
            assert box is not None
            mx, my, mx1, my1 = box
            mask_name = f"masked{index}"
            graph += (f";[{prev}]drawbox=x={mx}:y={my}:w={mx1-mx}:h={my1-my}:"
                      f"color=black@1:t=fill:enable='between(t,{start:.3f},{end:.3f})'"
                      f"[{mask_name}]")
            prev = mask_name
        graph += (f";[{prev}][{index}:v]overlay={placed['x']}:{placed['y']}:"
                  f"enable='between(t,{start:.3f},{end:.3f})'[{after}]")
        prev = after
        placements.append({"event_id": event["event_id"], **placed})
    command += [
        "-filter_complex", graph, "-map", f"[{prev}]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-shortest", str(output),
    ]
    t1 = time.monotonic()
    run(command, timeout=1800)
    ffmpeg_seconds = time.monotonic() - t1
    caption = production / "caption.my.txt"
    caption.write_text(timeline["caption_my"] + "\n", encoding="utf-8")
    metadata = {
        "title": timeline["title_my"], "visibility": timeline["visibility"],
        "source_aweme_id": source["aweme_id"], "source_url": source["source_url"],
        "content_type": timeline["content_type"], "audio": "original",
    }
    atomic_json(production / "metadata.json", metadata)
    duration = float(timeline["duration_s"])
    preview = production / "preview.jpg"
    run(["ffmpeg", "-v", "error", "-y", "-ss", str(duration / 2),
         "-i", str(output), "-frames:v", "1", str(preview)], timeout=50)
    frames_dir = production / "qa-contact-frames"
    frames_dir.mkdir(exist_ok=True)
    sampled = []
    for idx, event in enumerate(active[:12]):
        for point in (event["start"] + .02, (event["start"] + event["end"]) / 2, event["end"] - .02):
            if 0 <= point < duration:
                frame = frames_dir / f"ev-{idx:03d}-{len(sampled):02d}.jpg"
                run(["ffmpeg", "-v", "error", "-y", "-ss", f"{point:.3f}",
                     "-i", str(output), "-frames:v", "1", "-vf", "scale=270:-2",
                     str(frame)], timeout=30)
                sampled.append(frame)
    contact = production / "preview-contacts.jpg"
    if sampled:
        # Bounded horizontally-tiled QA evidence; never requires full-frame OCR.
        run(["ffmpeg", "-v", "error", "-y", "-pattern_type", "glob",
             "-i", str(frames_dir / "ev-*.jpg"), "-filter_complex",
             "tile=4x9:padding=4:margin=4", "-frames:v", "1", str(contact)], timeout=45)
    result = {
        "video": str(output), "caption": str(caption),
        "metadata": str(production / "metadata.json"), "preview": str(preview),
        "preview_contacts": str(contact) if contact.exists() else None,
        "render_mode": "dynamic_v04", "render_preset": timeline["render_preset"],
        "timeline_sha256": digest(timeline),
        **geometry, "swift_batch_seconds": round(swift_seconds, 3),
        "ffmpeg_seconds": round(ffmpeg_seconds, 3),
        "cue_count": len(active), "placements": placements,
        "sha256": {"video": sha256_file(output),
                   "caption": sha256_file(caption),
                   "metadata": sha256_file(production / "metadata.json")},
    }
    atomic_json(production / "render-result.json", result)
    after = evaluate(job_dir, after_render=True)
    notify_if_blocked(job_dir, after)
    if after["status"] == "BLOCKED":
        raise RuntimeError("BLOCKED: subtitle render failed post-render QA")
    return result
