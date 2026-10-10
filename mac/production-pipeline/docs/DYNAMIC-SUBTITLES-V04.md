# Dynamic Myanmar subtitles v0.4 — Mac-only

Status: implemented behind explicit feature switch, unapproved for production until R0 and R2 evidence gates pass.

## Boundaries

All OCR, Chinese speech evidence, event fusion, translations, layout and encoding run on the Mac. The Y700/TikTok publisher, PUBLIC authorization, deduplication, reconciliation, and DIRECT_DOWNLOAD stay unchanged. Do not commit private media or runtime state.

Existing pipeline submit remains legacy by default. For an authorized experimental job, opt in with --dynamic-subtitles or Y700_SUBTITLE_MODE=dynamic_v04. Build Mac Swift tools with scripts/bootstrap.sh after the code-development phase; dependencies include FFmpeg and a locally installed Noto Sans Myanmar font.

## Mac-only workflow

1. Submit an authorized Douyin link with the dynamic flag; inspect new artifacts under analysis/asr_events.zh.json, ocr_observations.zh.json, ocr_events.zh.json, fused_events.zh.json and translation_requests.json.
2. The existing Cloud GPT/Hermes orchestrator must use every translation_requests.json batch as locked read-only input. Each LLM batch response must contain ONLY translations: an array of event_id, text_my objects. Combine all target event translations with canonical_lock, fused_events_sha256, title_my, caption_my and visibility into one bundle. Do not change event IDs, source refs, event times or translate surrounding context as a target.
3. Run pipeline.sh localize JOB bundle.json. This produces the timeline (Mac render schedule SOT), derived legacy v2 localization projection and Q1/Q2 quality report. Contract errors are BLOCKED; they do not create an all-video caption fallback.
4. If REVIEW_REQUIRED, inspect original frame refs and use pipeline.sh quality-review JOB --code CODE --reviewer NAME --reason EVIDENCE, then rerun quality-check. A reviewer can clear reviewable items only, not BLOCKED errors.
5. Optional layout-set for a confirmed opaque stable rectangular backplate requires at least two existing local frame refs before choosing cover_and_replace. Otherwise avoid_original is the default. No inpainting, watermark removal or bulk color-patch replacement.
6. Run pipeline.sh render JOB; one Swift batch invocation generates Myanmar PNG assets and FFmpeg composites cues at their locked times; Q3 generates a quality report and contact frames. Only Q3 PASS permits pipeline.sh export JOB. The pre-existing capability handoff and Y700 publish workflow are separate.

## Notification and recovery

quality_report.json is quality truth. Per-job production/quality-notify.json is a durable outbox, persisted before existing TG send attempt. Notifications can fail without authorizing export. pipeline.sh quality-queue lists pending, failed, blocked tasks entirely offline. Explicit quality-resend JOB only retries notification, no publication actions. Do not add daemons or remote channels.

## Source and version lock

Fused events preserve all source observations and legal exclusion reasons. Canonical IDs, start/end times and source refs cannot be changed by an LLM. Initial R0 tuning values: IoU>=0.60; similarity>=0.85 for 4+ Chinese characters; 1–3 Han chars NFC+whitespace removal+versioned decoration filter strict exact; adjacent gap<=1.5s. These are not measured production thresholds. OCR budget exhaustion must not pass silently. Actual videos, OCR evidence frames and sensitive user identifiers remain outside Git.

## R0/R2 constraints

Offline comparison script scripts/subtitle_r0_benchmark.py reads an explicitly approved private manifest and writes a local report; absent real 24+2 samples and independent GT => R0_DATA_BLOCKED and no business KPI claim. Swift batch / existing overlay / ASS comparisons require real Myanmar complex-shaping and CPU/RSS/latency measurements. R2 needs named Myanmar reviewer and MP4-level inspection of script shaping and meaning. Do not enable public zero-touch new mode before those gates and regression evidence. No real TikTok COMMIT is authorized by this feature.
