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
- Treats one supplied Douyin URL as explicit authorization for exactly one PUBLIC COMMIT after mandatory DRY_RUN unless the current turn narrows/revokes it.
- For Telegram ingress, emits public-safe status transitions through `scripts/tg-notify.sh`.

Y700:
- Pull/checksum/stage/TikTok DRY_RUN.
- Commit only after explicit approval.
- Verify publication and reconcile durable state.

## Hard rules
- Never log Douzy bearer tokens or cookies.
- Never use unauthenticated direct Douyin scraping as production fallback.
- Never turn a failed/ambiguous TikTok COMMIT into an automatic retry.
- On Y700, cross the PUBLIC commit boundary only through `scripts/approve-public-commit.sh`; do not manually combine a manifest edit with `publish-async.sh --commit`.
- Same aweme_id must deduplicate by default.
- Production default visibility is PUBLIC. A different visibility requires an explicit user request.
- Runtime jobs and downloaded media do not enter Git.
- Telegram is not a general-purpose shell. Only Douyin URL, `/status`, `/cancel`, and `/help` control intents are accepted by the dedicated profile.
- Telegram notification failure never changes job truth and never authorizes a retry.
