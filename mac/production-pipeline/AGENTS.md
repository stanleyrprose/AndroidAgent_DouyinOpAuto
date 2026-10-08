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
- Requires an explicit Telegram intent prefix. Persist the normalized intent (`AUTO_PUBLISH`, `STORE_ALBUM`, or `DIRECT_DOWNLOAD`) on the canonical job as soon as its job id is known. `自动发布` / `Automatic Publish` authorize exactly one PUBLIC COMMIT after mandatory DRY_RUN; `存到相册` / `Save to Album` authorize localized/rendered video + Notes storage; `直接下载` / `Direct Download` authorize only original-video download + Y700 album storage. Neither authorizes publication. English aliases are ASCII case-insensitive. Bare Douyin URLs are not execution intents.
- Telegram `继续任务：<job>` / `Resume Task:<job>` must invoke only `scripts/start-resume-job.sh`; the deterministic resume controller refuses missing/mismatched intent markers and never replays an uncertain COMMIT.
- For Telegram ingress, emits public-safe status transitions through `scripts/tg-notify.sh`.

Y700:
- For normalized `AUTO_PUBLISH`: pull/checksum/stage/TikTok DRY_RUN, exactly-one COMMIT, verification/reconciliation, then restore initial screen power state after terminal closure.
- For normalized `STORE_ALBUM`: pull/checksum and non-destructively store the rendered video under `Movies/Y700Agent`, verify MediaStore, save Caption to Notes, restore initial screen power state, and stop without opening TikTok.
- For normalized `DIRECT_DOWNLOAD`: download the original Douyin MP4 only, generic-artifact export/pull with size+SHA-256 validation, store it under `Movies/Y700Agent`, verify MediaStore, restore initial screen power state, and stop without analysis/localization/render/Notes/TikTok.

## Hard rules
- Never log Douzy bearer tokens or cookies.
- Never use unauthenticated direct Douyin scraping as production fallback.
- Never turn a failed/ambiguous TikTok COMMIT into an automatic retry.
- On Y700, cross the PUBLIC commit boundary only through `scripts/approve-public-commit.sh`; do not manually combine a manifest edit with `publish-async.sh --commit`.
- Same aweme_id must deduplicate by default.
- Production default visibility is PUBLIC. A different visibility requires an explicit user request.
- Runtime jobs and downloaded media do not enter Git.
- Telegram is not a general-purpose shell. The dedicated profile accepts only the explicit Chinese/English plain-text publish, album, resume, status, cancel, and help intents defined in the canonical SOUL; bare Douyin links do not execute and Hermes slash commands are not Y700 workflow aliases.
- Telegram notification failure never changes job truth and never authorizes a retry.
