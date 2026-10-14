# R0-04 Burmese review-video gate (opt-in, not TikTok release)

The Mac production plane now supports an **explicit review-only** render path. The `pipeline.review_video` module accepts a private dual-translation draft, renders NORMAL and FUNNY review MP4s using Pango/HarfBuzz + Noto Sans Myanmar + ImageMagick + FFmpeg, and writes a review-only manifest. It does **not** alter the legacy production renderer, activate dynamic subtitles, export to Y700, or authorize TikTok publishing.

## Source-of-truth separation

- Recognition GT remains verbatim; e.g. F59 `不和物质发生作用` is not overwritten by a science edit.
- Publication text may record an explicitly reviewed scientific correction, e.g. F59 `几乎不与物质发生相互作用`.
- 76 translation targets, 152 draft variants, F05/F60/F65 excluded. The draft is **not native-speaker approved**.
- 36 speech subtitle events are included in the preview; 40 visual callouts are intentionally excluded from this first overlay, and original Chinese hard captions remain in the source.
- Timing conflicts use latest-start-wins only for the preview, not for canonical event timing. F79 ends on an incomplete sentence.

## Explicit offline command

From `mac/production-pipeline`:

```bash
python3 -m pipeline.review_video \
  --source /private/path/to/source.mp4 \
  --draft /private/path/to/dual-translation-draft-76.json \
  --output-dir /private/path/to/review-video \
  --variant both
```

Requires `ffprobe`, `ffmpeg` with libx264, `pango-view`, `magick` and Noto Sans Myanmar installed on the Mac. Input, output, Telegram receipts and media remain in ignored/private runtime paths. This command performs **no network actions**. The human-review Telegram delivery is a separate authorized step.

## Blockers before TikTok

1. Native Burmese speaker reviews science, naturalness and FUNNY register against the actual video.
2. Review display timings, overlapping primary events and very short cues; do not treat animation OCR spans as final subtitle durations.
3. Review and place visual callouts separately, including long-lived diagrams and repeated labels.
4. Resolve F79 partial end-of-clip sentence, and confirm scientific corrections without changing recognition GT.
5. Only a later independently approved release gate may enable production localization/publishing. Deploying this opt-in preview tool does not lift these blocks.
