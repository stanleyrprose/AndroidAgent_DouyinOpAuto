#!/usr/bin/env python3
"""Offline-only R0 measurement; never exports, opens TikTok or connects to Y700.

Requires a privately stored manifest with 24 baseline and 2 pressure samples.
If GT is missing, output feasibility results but Gate R0 remains DATA_BLOCKED.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))
from pipeline.common import atomic_json, sha256_file
from pipeline.subtitle_events import EventRules, similarity, track_ocr
from pipeline.video_ocr import OCRConfig, run_video_ocr
from pipeline.analyze import ffprobe


def _quantile(rows: list[float], q: float) -> float | None:
    if not rows:
        return None
    xs = sorted(rows)
    return round(xs[int((len(xs) - 1) * q)], 3)


def _score(events: list[dict], gt: list[dict]) -> dict:
    meaningful = [x for x in gt if x.get("importance") == "important"]
    matched_actual: set[int] = set()
    matched_gt: set[int] = set()
    boundaries = []
    for i, detected in enumerate(events):
        for k, truth in enumerate(meaningful):
            if k in matched_gt:
                continue
            if similarity(detected["text_zh"], truth["text_zh"]) < .85:
                continue
            if max(detected["start"], truth["start"]) >= min(detected["end"], truth["end"]):
                continue
            matched_actual.add(i)
            matched_gt.add(k)
            boundaries.append(max(abs(detected["start"] - truth["start"]),
                                  abs(detected["end"] - truth["end"])))
            break
    tp = len(matched_gt)
    return {
        "gt_important": len(meaningful),
        "true_positive": tp, "false_positive": len(events) - len(matched_actual),
        "false_negative": len(meaningful) - tp,
        "recall": round(tp / len(meaningful), 4) if meaningful else None,
        "precision": round(len(matched_actual) / len(events), 4) if events else None,
        "boundary_within_500ms": round(
            sum(x <= .5 for x in boundaries) / len(boundaries), 4) if boundaries else None,
    }


def run_manifest(path: Path, outpath: Path, backend: str) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    samples = data.get("samples", [])
    ids = [x.get("id") for x in samples]
    if len(set(ids)) != len(ids):
        raise RuntimeError("duplicate R0 sample id")
    durations: list[float] = []
    rows = []
    baseline = [x for x in samples if x.get("group") == "baseline"]
    pressure = [x for x in samples if x.get("group") == "pressure"]
    full_gt = len(baseline) == 24 and len(pressure) == 2 and all(
        x.get("gt_path") and Path(x["gt_path"]).exists() for x in samples
    )
    for sample in samples:
        video = Path(sample["video_path"])
        if not video.is_file():
            rows.append({"sample_id": sample.get("id"), "status": "DATA_MISSING"})
            full_gt = False
            continue
        expected_sha = sample.get("source_sha256")
        if expected_sha and sha256_file(video) != expected_sha:
            rows.append({"sample_id": sample.get("id"), "status": "SHA_MISMATCH"})
            full_gt = False
            continue
        probe = ffprobe(video)
        duration = float(probe["format"]["duration"])
        t0 = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="R0-isolated-") as td:
            scratch = Path(td)
            result = run_video_ocr(video, scratch, duration, cfg=OCRConfig(backend=backend))
            events = track_ocr(result["observations"], duration, EventRules())
        elapsed = time.monotonic() - t0
        durations.append(elapsed)
        row = {
            "sample_id": sample["id"], "group": sample.get("group"),
            "video_seconds": duration,
            "runtime_seconds": round(elapsed, 3),
            "ocr_calls": result["diagnostics"].get("ocr_calls"),
            "budget_exhausted": result["diagnostics"].get("budget_exhausted"),
            "detected_event_count": len(events),
            "auto_translation_candidates": sum(
                "UNVERIFIED_LOW_CONFIDENCE_SINGLE_FRAME" not in e.get("review_flags", [])
                for e in events
            ),
            "held_non_han_candidates": sum(
                "UNVERIFIED_LOW_CONFIDENCE_SINGLE_FRAME" in e.get("review_flags", [])
                for e in events
            ),
            "status": "FEASIBILITY_MEASURED",
        }
        gt_path = sample.get("gt_path")
        if gt_path and Path(gt_path).is_file():
            truth = json.loads(Path(gt_path).read_text(encoding="utf-8"))
            row["scoring"] = _score(events, truth.get("events", []))
        else:
            full_gt = False
        rows.append(row)
    report = {
        "schema_version": 1, "backend": backend,
        "status": "R0_FEASIBILITY_MEASURED" if full_gt else "R0_DATA_BLOCKED",
        "gate_r0_pass": False,
        "baseline_count": len(baseline), "pressure_count": len(pressure),
        "kpi_qualified": full_gt,
        "note": "Automated score never substitutes for Myanmar human semantics and font review.",
        "runtime_p50_s": _quantile(durations, .5), "runtime_p95_s": _quantile(durations, .95),
        "samples": rows,
    }
    atomic_json(outpath, report)
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--ocr", choices=["vision", "paddle"], default="vision")
    args = ap.parse_args()
    report = run_manifest(Path(args.manifest), Path(args.report), args.ocr)
    print(json.dumps({"status": report["status"],
                      "report_path": args.report,
                      "sample_count": len(report["samples"])}))
    return 0 if report["kpi_qualified"] else 20


if __name__ == "__main__":
    raise SystemExit(main())
