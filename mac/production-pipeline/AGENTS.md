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
- Requires an explicit Telegram intent prefix. `自动发布+` authorizes exactly one PUBLIC COMMIT after mandatory DRY_RUN; `存到相册+` authorizes only production + Y700 album storage and never publication. Bare Douyin URLs are not execution intents.
- For Telegram ingress, emits public-safe status transitions through `scripts/tg-notify.sh`.

Y700:
- For `自动发布+`: pull/checksum/stage/TikTok DRY_RUN, exactly-one COMMIT, verification/reconciliation, then restore initial screen power state after terminal closure.
- For `存到相册+`: pull/checksum and non-destructively store the rendered video under `Movies/Y700Agent`, verify MediaStore, restore initial screen power state, and stop without opening TikTok.

## Hard rules
- Never log Douzy bearer tokens or cookies.
- Never use unauthenticated direct Douyin scraping as production fallback.
- Never turn a failed/ambiguous TikTok COMMIT into an automatic retry.
- On Y700, cross the PUBLIC commit boundary only through `scripts/approve-public-commit.sh`; do not manually combine a manifest edit with `publish-async.sh --commit`.
- Same aweme_id must deduplicate by default.
- Production default visibility is PUBLIC. A different visibility requires an explicit user request.
- Runtime jobs and downloaded media do not enter Git.
- Telegram is not a general-purpose shell. Only `自动发布+<Douyin>`, `存到相册+<Douyin>`, `/status`, `/cancel`, and `/help` are accepted by the dedicated profile; bare Douyin links do not execute.
- Telegram notification failure never changes job truth and never authorizes a retry.
