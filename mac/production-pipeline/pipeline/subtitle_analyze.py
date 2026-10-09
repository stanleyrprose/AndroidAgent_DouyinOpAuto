"""Feature-flagged dynamic subtitle evidence extraction after existing Mac analysis."""
from __future__ import annotations

from pathlib import Path

from .common import atomic_json, read_json, sha256_file
from .subtitle_events import EventRules, digest, fuse_events, speech_events, track_ocr
from .subtitle_localization import translation_request
from .video_ocr import run_video_ocr


def analyze_dynamic(video: Path, analysis_dir: Path, legacy_analysis: dict) -> dict:
    duration = float(legacy_analysis["duration"])
    rules = EventRules()
    transcript = read_json(analysis_dir / "transcript.zh.json", {}) or {}
    speech = speech_events(transcript, duration)
    atomic_json(analysis_dir / "asr_events.zh.json", {
        "schema_version": 1, "source_video_sha256": sha256_file(video),
        "source_events": speech,
    })
    try:
        result = run_video_ocr(video, analysis_dir, duration)
        observations = result["observations"]
        diagnostic = result["diagnostics"]
    except (RuntimeError, OSError, ValueError) as exc:
        # No silent speech-only fallback. Later quality gate examines OCR_UNAVAILABLE.
        observations = []
        diagnostic = {
            "error": "OCR_UNAVAILABLE", "failure_kind": type(exc).__name__,
            "coverage_incomplete": True, "unscanned": [[0, duration]],
            "ocr_observations": 0, "ocr_calls": 0,
        }
        atomic_json(analysis_dir / "ocr_observations.zh.json", {
            "schema_version": 1, "observations": [], "diagnostics": diagnostic,
        })
    visual = track_ocr(observations, duration, rules)
    atomic_json(analysis_dir / "ocr_events.zh.json", {
        "schema_version": 1, "source_events": visual,
        "rule_set_version": rules.fingerprint(),
    })
    fused = fuse_events(speech, visual, source_sha256=sha256_file(video),
                        duration=duration, rules=rules)
    atomic_json(analysis_dir / "fused_events.zh.json", fused)
    requests = []
    count = len([x for x in fused["canonical_events"] if x["fact_disposition"] == "translate_target"])
    for offset in range(0, count, 16):
        requests.append(translation_request(fused, start=offset, batch_size=16))
    atomic_json(analysis_dir / "translation_requests.json", {
        "schema_version": 1, "canonical_lock": fused["canonical_lock"],
        "fused_events_sha256": digest(fused),
        "batches": requests,
        "output_contract": {
            "translations": [{"event_id": "exact-target-id", "text_my": "valid Myanmar Unicode"}],
        },
    })
    analysis = {**legacy_analysis,
                "subtitle_mode": "dynamic_v04",
                "dynamic_ocr": diagnostic,
                "fused_events_sha256": digest(fused),
                "canonical_lock": fused["canonical_lock"],
                "translation_requests": "analysis/translation_requests.json"}
    atomic_json(analysis_dir / "analysis.json", analysis)
    return analysis
