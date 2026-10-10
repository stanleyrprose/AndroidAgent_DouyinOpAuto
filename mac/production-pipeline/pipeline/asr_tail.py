"""Bounded ASR tail review discovery: evidence only, never automatic subtitles."""
from __future__ import annotations


def tail_review_candidates(model, audio, original_segments: list[dict],
                           sample_rate: int = 16000,
                           *, end_gap_s: float = 8.0) -> dict:
    """Inspect the entire supplied waveform when the full-pass ASR ends early.

    Independent partial-window Whisper outputs are not trustworthy enough to
    promote to canonical text. Always label them review candidates. In
    particular, a tail hallucination must never be treated as verified speech.
    """
    import numpy as np
    length = len(audio) / sample_rate
    last_end = max((float(s["end"]) for s in original_segments), default=0.0)
    report = {"audio_duration_s": round(length, 3),
              "full_pass_last_speech_end_s": round(last_end, 3),
              "tail_review_required": False, "tail_review_candidates": [],
              "tail_windows_checked_s": []}
    if length < 8 or length - last_end <= end_gap_s:
        return report
    for width in (7.5, 12.0):
        begin = max(last_end, length - width)
        if length - begin < 1.0:
            continue
        sample = audio[int(begin * sample_rate):]
        rms = float(np.sqrt(np.mean(np.square(sample.astype(np.float64)))))
        report["tail_windows_checked_s"].append([round(begin, 3), round(length, 3)])
        if rms < 0.002:
            continue
        segments, _ = model.transcribe(
            sample, language="zh", beam_size=5, vad_filter=True,
            condition_on_previous_text=False, word_timestamps=False)
        for segment in segments:
            value = str(segment.text).strip()
            start, end = begin + segment.start, min(length, begin + segment.end)
            if not value or end <= start:
                continue
            if any(r["text_zh_machine"] == value and
                   abs(r["start"] - start) < 1.0 for r in report["tail_review_candidates"]):
                continue
            report["tail_review_candidates"].append({
                "text_zh_machine": value,
                "start": round(start, 3), "end": round(end, 3),
                "source_window_start_s": round(begin, 3),
                "review_status": "REVIEW_REQUIRED_UNVERIFIED_ASR_TAIL",
            })
    report["tail_review_required"] = bool(report["tail_review_candidates"])
    return report
