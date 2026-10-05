from __future__ import annotations

import json
import re
import wave
from pathlib import Path

import numpy as np

from .common import MODEL_DEFAULT, atomic_json, run


def ffprobe(video: Path) -> dict:
    p = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size",
        "-show_entries", "stream=index,codec_type,codec_name,width,height",
        "-of", "json", str(video),
    ])
    return json.loads(p.stdout)


def extract_audio(video: Path, wav: Path) -> None:
    run([
        "ffmpeg", "-v", "error", "-y",
        "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(wav),
    ])


def transcribe(wav_path: Path, model_path: Path = MODEL_DEFAULT) -> dict:
    from faster_whisper import WhisperModel
    with wave.open(str(wav_path), "rb") as w:
        if (w.getnchannels(), w.getframerate(), w.getsampwidth()) != (1, 16000, 2):
            raise RuntimeError("unexpected WAV format")
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    model = WhisperModel(str(model_path), device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        audio,
        language="zh",
        beam_size=5,
        vad_filter=True,
        word_timestamps=False,
    )
    rows = []
    for s in segments:
        rows.append({
            "start": round(s.start, 3),
            "end": round(s.end, 3),
            "text": s.text.strip(),
            "avg_logprob": round(float(s.avg_logprob), 4),
            "no_speech_prob": round(float(s.no_speech_prob), 4),
        })
    return {
        "language": info.language,
        "language_probability": float(info.language_probability),
        "segments": rows,
    }


def meaningful_speech(transcript: dict) -> bool:
    text = " ".join(x.get("text", "") for x in transcript.get("segments", []))
    han = re.findall(r"[\u3400-\u9fff]", text)
    duration = sum(max(0.0, x["end"] - x["start"]) for x in transcript.get("segments", []))
    return len(han) >= 4 and duration >= 0.8


def keyframes(video: Path, out_dir: Path, duration: float) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    points = [max(0.2, duration * p) for p in (0.08, 0.28, 0.50, 0.72, 0.92)]
    files = []
    for idx, sec in enumerate(points, 1):
        path = out_dir / f"frame-{idx}.jpg"
        run([
            "ffmpeg", "-v", "error", "-y", "-ss", f"{sec:.3f}",
            "-i", str(video), "-frames:v", "1", "-vf", "scale=540:-2", str(path),
        ])
        files.append(path)
    sheet = out_dir / "contact-sheet.jpg"
    run([
        "ffmpeg", "-v", "error", "-y", "-pattern_type", "glob",
        "-i", str(out_dir / "frame-*.jpg"),
        "-filter_complex", "tile=5x1:padding=6:margin=6",
        str(sheet),
    ])
    return files


def analyze(video: Path, analysis_dir: Path) -> dict:
    analysis_dir.mkdir(parents=True, exist_ok=True)
    probe = ffprobe(video)
    duration = float(probe["format"]["duration"])
    wav = analysis_dir / "audio-16k.wav"
    extract_audio(video, wav)
    transcript = transcribe(wav)
    atomic_json(analysis_dir / "transcript.zh.json", transcript)
    (analysis_dir / "transcript.zh.txt").write_text(
        "\n".join(x["text"] for x in transcript["segments"]) + "\n",
        encoding="utf-8",
    )
    keyframes(video, analysis_dir / "frames", duration)
    route = "speech_candidate" if meaningful_speech(transcript) else "visual_review"
    result = {
        "duration": duration,
        "probe": probe,
        "route": route,
        "meaningful_speech": meaningful_speech(transcript),
        "transcript": transcript,
        "contact_sheet": "analysis/frames/contact-sheet.jpg",
    }
    atomic_json(analysis_dir / "analysis.json", result)
    atomic_json(analysis_dir / "localization_request.json", {
        "schema_version": 1,
        "route": route,
        "instructions": (
            "Use transcript and contact sheet as evidence. "
            "Do not invent speech. Produce Burmese title/caption and timed cues. "
            "Every caption must include caption_basis explaining why it fits, "
            "with concrete source frame timestamps and/or transcript snippets."
        ),
        "expected_output": {
            "content_type": "speech|visual_text|mixed|visual_only",
            "title_my": "string",
            "caption_my": "string",
            "visibility": "PUBLIC",
            "cues": [{"start": 0.0, "end": duration, "text_my": "string"}],
        },
    })
    return result
