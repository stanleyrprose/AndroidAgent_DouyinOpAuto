# AGENTS.md

## Scope
This repository is the Mac content-production plane for PRD v0.4.

## Responsibility boundary
Mac:
- Douyin authenticated download through Douzy.
- Media inspection and speech transcription.
- Keyframe/contact-sheet generation.
- Durable production job state.
- Burmese localization artifact rendering.
- Export through the existing y700 media gateway.

Orchestrator (Cloud GPT or dedicated Hermes `y700automation` profile):
- Loads the canonical `douyin-tiktok-publish` Skill contract.
- Reviews transcript/keyframes.
- Produces localization.json from evidence.
- Sends exported manifest URL to Y700.
- Requires an explicit Telegram intent prefix. Persist the normalized intent (`AUTO_PUBLISH`, `STORE_ALBUM`, or `DIRECT_DOWNLOAD`) on the canonical job as soon as its job id is known. Only `自动发布` / `Automatic Publish` authorizes a PUBLIC COMMIT after DRY_RUN. Under dynamic_v04, `存到相册` / `Save to Album` and `下载并缅语化` / `Download and Localize` use a TG-only localized MP4 delivery path (internal compatibility intent `STORE_ALBUM`), while `直接下载` / `Direct Download` sends the original MP4 to Telegram. Neither authorizes publication or Y700 delivery. English aliases are ASCII case-insensitive. Bare Douyin URLs are not execution intents.
- Telegram `继续任务：<job>` / `Resume Task:<job>` must invoke only `scripts/start-resume-job.sh`; the deterministic resume controller refuses missing/mismatched intent markers and never replays an uncertain COMMIT.
- For Telegram ingress, emits public-safe status transitions through `scripts/tg-notify.sh`.

Y700:
- For normalized `AUTO_PUBLISH`: pull/checksum/stage/TikTok DRY_RUN, exactly-one COMMIT, verification/reconciliation, then restore initial screen power state after terminal closure.
- For normalized `STORE_ALBUM` in dynamic_v04 TG-only processing: no Y700 action; the Mac produces Burmese video and requires confirmed Telegram delivery before cleanup.
- For normalized `DIRECT_DOWNLOAD` in this TG-only profile: Mac downloads and sends the original Douyin MP4 directly to Telegram with a confirmed receipt; no Y700, analysis, localization, render, Notes or TikTok.

## Hard rules
- Never log Douzy bearer tokens or cookies.
- Never use unauthenticated direct Douyin scraping as production fallback.
- Never turn a failed/ambiguous TikTok COMMIT into an automatic retry.
- On Y700, cross the PUBLIC commit boundary only through `scripts/approve-public-commit.sh`; do not manually combine a manifest edit with `publish-async.sh --commit`.
- Same aweme_id must deduplicate by default.
- Production default visibility is PUBLIC. A different visibility requires an explicit user request.
- Runtime jobs and downloaded media do not enter Git.
- Telegram is not a general-purpose shell. The dedicated profile accepts only explicit Chinese/English publish, TG-localize, repeat, direct-download, reviewed-evidence reply, resume, status, cancel and help intents defined in the canonical SOUL; bare Douyin links do not execute and Hermes slash commands are not Y700 workflow aliases. Legacy duplicate recovery must preserve the original Job; a human-review notification requires confirmed matching evidence.
- Telegram notification failure never changes job truth and never authorizes a retry.
