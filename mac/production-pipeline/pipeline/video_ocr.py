"""Bounded local-video OCR on the Mac production plane.

The ffmpeg difference scan is a proposal generator, not evidence that all text
has been found. OCR coverage gaps and failures are exposed to the QA gate.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .common import ROOT, atomic_json, run


@dataclass(frozen=True)
class OCRConfig:
    backend: str = "vision"
    scan_fps: float = 2.0
    baseline_fps: float = 1.0
    change_threshold: float = 18.0
    max_ocr_calls_per_minute: int = 90
    max_duration_s: float = 600.0
    scan_width: int = 180
    scan_height: int = 320


def _video_frames(video: Path, cfg: OCRConfig, duration: float):
    """Yield downscaled gray frames, bounding memory to a single frame."""
    command = [
        "ffmpeg", "-v", "error", "-i", str(video), "-an",
        "-vf", f"fps={cfg.scan_fps},scale={cfg.scan_width}:{cfg.scan_height},format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
    ]
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    count = cfg.scan_width * cfg.scan_height
    try:
        i = 0
        while True:
            frame = proc.stdout.read(count) if proc.stdout else b""
            if not frame or len(frame) != count:
                break
            ts = (i + .5) / cfg.scan_fps
            if ts > duration + 0.05:
                break
            yield ts, np.frombuffer(frame, dtype=np.uint8).reshape(cfg.scan_height, cfg.scan_width)
            i += 1
    finally:
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()


def select_candidate_times(video: Path, duration: float, cfg: OCRConfig) -> tuple[list[float], dict]:
    if not 0 < duration <= cfg.max_duration_s:
        return [], {"coverage_incomplete": True, "reason": "DURATION_LIMIT", "unscanned": [[0, duration]]}
    chosen: list[float] = []
    prev = None
    last_base = -10.0
    last_extra = -10.0
    scan_count = 0
    changes = 0
    for ts, frame in _video_frames(video, cfg, duration):
        scan_count += 1
        baseline = ts - last_base >= 1 / cfg.baseline_fps - .02
        changed = False
        if prev is not None:
            # Quadrants are not used; sample horizontal bands across full frame.
            # Avoid global-scene-movement triggering full OCR for every frame:
            # change must be significant in at least one region and bounded by budget.
            differences = np.abs(frame.astype(np.int16) - prev.astype(np.int16))
            band_scores = [float(x.mean()) for x in np.array_split(differences, 4, axis=0)]
            changed = any(score > cfg.change_threshold for score in band_scores)
        prev = frame.copy()
        if baseline:
            last_base = ts
        if changed:
            changes += 1
        if baseline or (changed and ts - last_extra >= 0.5):
            chosen.append(round(ts, 3))
            if changed:
                last_extra = ts
    chosen = sorted(set(chosen))
    # Preserve broad coverage if rapid scene-motion consumed too much of the budget.
    per_minute_limit = max(1, cfg.max_ocr_calls_per_minute)
    retained: list[float] = []
    discarded: list[float] = []
    minute_counts: dict[int, int] = {}
    for ts in chosen:
        minute = int(ts // 60)
        if minute_counts.get(minute, 0) < per_minute_limit:
            retained.append(ts)
            minute_counts[minute] = minute_counts.get(minute, 0) + 1
        else:
            discarded.append(ts)
    return retained, {
        "scan_frames": scan_count, "change_frames": changes, "candidate_frames": len(chosen),
        "ocr_calls_planned": len(retained), "ocr_budget_limit_per_minute": per_minute_limit,
        "budget_exhausted": bool(discarded),
        "coverage_incomplete": bool(discarded) or scan_count == 0 or not retained,
        "coverage_reason": "SCAN_EMPTY" if scan_count == 0 or not retained else (
            "OCR_BUDGET_EXHAUSTED" if discarded else None),
        "unscanned": [[round(max(0, t - 0.25), 3), round(min(duration, t + .25), 3)] for t in discarded[:80]],
        "unscanned_count": len(discarded),
        "scan_budget": asdict(cfg),
    }


def _vision_batch(inputs: list[dict]) -> list[dict]:
    tool = ROOT / "runtime" / "bin" / "vision_ocr"
    if not tool.is_file():
        raise RuntimeError("OCR_UNAVAILABLE: vision_ocr missing; run scripts/bootstrap.sh")
    with tempfile.TemporaryDirectory(prefix="vision-ocr-") as td:
        manifest = Path(td) / "frames.json"
        atomic_json(manifest, inputs)
        proc = run([str(tool), str(manifest)], timeout=900)
        data = json.loads(proc.stdout)
        return list(data["frames"])


def _paddle_batch(inputs: list[dict]) -> list[dict]:
    # Optional R0 comparator, not an always-on second OCR system.
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError("OCR_UNAVAILABLE: optional paddleocr not installed") from exc
    reader = PaddleOCR(use_doc_orientation_classify=False,
                       use_doc_unwarping=False, use_textline_orientation=False)
    frames = []
    for item in inputs:
        outcome = reader.predict(str(item["path"]))
        observations: list[dict] = []
        for result in outcome:
            payload = result.json if not callable(getattr(result, "json", None)) else result.json()
            payload = payload.get("res", payload)
            texts = payload.get("rec_texts", [])
            scores = payload.get("rec_scores", [])
            boxes = payload.get("rec_boxes", [])
            width, height = item["width"], item["height"]
            for text, score, box in zip(texts, scores, boxes):
                x0, y0, x1, y1 = map(float, box)
                observations.append({
                    "text_zh_raw": str(text), "ocr_confidence": float(score),
                    "bbox_norm": [x0 / width, y0 / height, x1 / width, y1 / height],
                })
        frames.append({"ts": item["ts"], "observations": observations})
    return frames


def run_video_ocr(video: Path, analysis_dir: Path, duration: float,
                  *, cfg: OCRConfig | None = None) -> dict:
    cfg = cfg or OCRConfig(
        backend=os.getenv("Y700_DYNAMIC_OCR_BACKEND", "vision"),
        max_ocr_calls_per_minute=int(os.getenv("Y700_DYNAMIC_OCR_CALLS_PER_MIN", "90")),
    )
    if cfg.backend not in ("vision", "paddle"):
        raise ValueError(f"unsupported OCR backend: {cfg.backend}")
    start = time.monotonic()
    times, diag = select_candidate_times(video, duration, cfg)
    records: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="subtitle-frames-", dir=analysis_dir) as td:
        frames = []
        for n, ts in enumerate(times):
            target = Path(td) / f"frame-{n:04d}.jpg"
            run(["ffmpeg", "-v", "error", "-y", "-ss", str(ts), "-i", str(video),
                 "-frames:v", "1", "-vf", "scale=960:-2", str(target)], timeout=30)
            # Actual extracted image dimensions read from ffprobe, not source dimensions.
            probe = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=width,height", "-of", "json", str(target)])
            stream = json.loads(probe.stdout)["streams"][0]
            frames.append({
                "path": str(target), "ts": ts,
                "width": int(stream["width"]), "height": int(stream["height"]),
            })
        if frames:
            results = _vision_batch(frames) if cfg.backend == "vision" else _paddle_batch(frames)
            if len(results) != len(frames):
                raise RuntimeError("OCR_UNAVAILABLE: OCR frame count mismatch")
            evidence_count = 0
            for index, frame in enumerate(results):
                if frame.get("observations") and evidence_count < 24:
                    local_evidence = analysis_dir / "frames" / f"ocr-sample-{index:04d}.jpg"
                    local_evidence.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(frames[index]["path"], local_evidence)
                    evidence_count += 1
                for obs in frame.get("observations", []):
                    text = str(obs.get("text_zh_raw", "")).strip()
                    bbox = obs.get("bbox_norm", [])
                    if not text or len(bbox) != 4:
                        continue
                    if not all(math.isfinite(float(x)) and 0 <= float(x) <= 1 for x in bbox):
                        continue
                    observation_id = "obs-" + hashlib.sha256(
                        json.dumps([times[index], bbox, text], ensure_ascii=False).encode()
                    ).hexdigest()[:16]
                    records.append({
                        "observation_id": observation_id,
                        "frame_ts": times[index], "text_zh_raw": text,
                        "bbox_norm": [round(float(x), 5) for x in bbox],
                        "ocr_confidence": round(float(obs.get("ocr_confidence", 0)), 4),
                        "provider": cfg.backend, "provider_version": "runtime",
                        "evidence_frame_ref": (f"analysis/frames/ocr-sample-{index:04d}.jpg"
                                               if (analysis_dir / "frames" / f"ocr-sample-{index:04d}.jpg").exists()
                                               else None),
                    })
    # Raw OCR is evidence: never infer text from a model when the OCR is empty.
    diag["ocr_observations"] = len(records)
    diag["ocr_calls"] = len(times)
    diag["ocr_elapsed_s"] = round(time.monotonic() - start, 3)
    diag["backend"] = cfg.backend
    atomic_json(analysis_dir / "ocr_observations.zh.json", {
        "schema_version": 1, "observations": records, "diagnostics": diag,
    })
    return {"observations": records, "diagnostics": diag}
