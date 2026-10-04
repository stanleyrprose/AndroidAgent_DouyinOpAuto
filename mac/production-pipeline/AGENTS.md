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

Cloud GPT:
- Orchestrates the workflow.
- Reviews transcript/keyframes.
- Produces localization.json from evidence.
- Sends exported manifest URL to Y700.
- Requests explicit user approval before COMMIT.

Y700:
- Pull/checksum/stage/TikTok DRY_RUN.
- Commit only after explicit approval.
- Verify publication and reconcile durable state.

## Hard rules
- Never log Douzy bearer tokens or cookies.
- Never use unauthenticated direct Douyin scraping as production fallback.
- Never turn a failed/ambiguous TikTok COMMIT into an automatic retry.
- Same aweme_id must deduplicate by default.
- Production default visibility is PUBLIC. A different visibility requires an explicit user request.
- Runtime jobs and downloaded media do not enter Git.
