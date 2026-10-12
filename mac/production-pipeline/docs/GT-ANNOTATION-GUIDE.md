# Ground Truth Annotation Guide — R0 Chinese hard subtitles

This guide is Git-safe; GT files and source media remain private and outside Git.

## Sample protocol

Offline manifest JSON contains samples[]: unique id, group (baseline|pressure), video_path, source_sha256 and gt_path. Exactly 24 baseline: A six speech+matching subtitles; B six text-only with music; C four speech+independent callout; D four static/visual; E four rapid/flower/low-quality. Two pressure: S01 dense rolling comments and S02 overlapping speakers. Missing sample or GT => R0_DATA_BLOCKED, not KPI PASS.

## Independent GT

Each private gt_path file includes events[] with text_zh, start, end, source_kind (speech|visual_text|synchronized_duplicate), role (primary_subtitle|callout|non_narrative), importance (important|non_narrative), optional bbox_norm original source coordinates top-left [x0,y0,x1,y1], exclusion_category, uncertainty, and human annotator/review timestamp. Source SHA and guide version link each GT to a stable video.

Important events materially change story, spoken content, reveal, punchline, numbers, negation or comprehension. Watermarks/accounts, repeated scrolling duplicates and meaningless decoration do not count as separate important GT events but remain in the filtered-evidence audit. A one-character reversal can count even when <0.5 seconds. Matching speech+hard subtitle counts as one canonical GT target. Uncertain overlaps need second-person adjudication, never self-labeled AI output.

## Metrics

Baseline 24 only: event recall TP/important-GT events >=90%; precision TP/automatically-important detected >=90%; 90% of matched event start and end times within +/-0.5 sec; 100% accounted-for important translations, exclusions or review states. Report tiny flashes and failure modes explicitly; do not quietly change the denominator. S01 filters irrelevant comments while preserving main narrative and OCR budget; S02 retains conflicting source evidence without fictional speaker attribution, then enters review.

## R2 Myanmar human checks

Inspect final MP4 as well as the PNGs: stacked consonants, medials, upper/lower vowels, tone/nasal marks, suspicious Zawgyi, mixed English/Chinese/numbers, soft wraps, cropping, font fallback, voice consistency, negations, names, punchlines and plots. Model confidence and Unicode validity alone do not prove correct Myanmar semantics. R2 requires a named qualified Myanmar-reading reviewer; without one the gate remains NOT PASS.
