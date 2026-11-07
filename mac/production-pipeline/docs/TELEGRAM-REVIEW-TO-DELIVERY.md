# Telegram review → Burmese video delivery (dynamic_v04)

## Goal and acceptance evidence

An allowlisted user sends `重新缅语化：<Douyin URL>` or the supported new-localization intent to the dedicated Y700 bot. Mac creates a durable versioned job, extracts the original Chinese subtitles, translates each eligible event one-to-one into Burmese, independently audits the translation, and renders a video. No TikTok publication or Y700 album transfer occurs for this workflow.

If a quality gate needs a human decision, the Mac bot sends **actual event evidence** to Telegram with the exact reply command and retains all source/intermediate media. The review reply must reference the correct evidence message (`reply_to_message_id`) in the same allowlisted chat. Successful Telegram video `sendVideo` acknowledgment (`message_id`) is required before task-scoped cleanup; an uncertain/failed send is never retried blindly.

## Legacy duplicate recovery and notification contract

When a localized TG-only request encounters an existing `dy-<aweme>` job, the wrapper tries an isolated `my-<aweme>-v04` upgrade using the old saved source. If the legacy state/media is incompatible, it **does not modify the old job**: it re-downloads the request into a new `my-<aweme>-v04-rNNN` job, binding the expected Aweme ID from the duplicate index and rejecting a conflicting downloaded video. Short `v.douyin.com` links are valid for this guarded fallback; standalone `重新缅语化` without a duplicate-ID context still needs a canonical video URL.

`RECOVERY_STARTED` means that an isolated analyzed job was created, **not** that the video was delivered. Failed re-download reports `LEGACY_UPGRADE_BLOCKED` and retains existing jobs/media. An already-existing upgraded job reports `RESUME_BLOCKED`; it must be reconciled, not blindly resent. This path only produces and sends Burmese video to TG; no Y700, Notes, TikTok or public COMMIT.

`QUALITY_REVIEW_REQUIRED` is reserved for OCR, semantic or layout review **with a confirmed, current Telegram evidence message ID**. If the evidence send is unconfirmed, the receipt is stale, or the QA issue is not human-reviewable, report `QUALITY_BLOCKED`; do not tell the user to reply to a generic status notification.

Dynamic v04 TG-only Jobs still carry the old internal `STORE_ALBUM` marker. The generic legacy `继续任务` album-resume script **fails closed** for `subtitle_mode=dynamic_v04` or a `my-<aweme>-v04[-rNNN]` Job ID; it must never export media to Y700. Human review continues exclusively by replying to the current verified evidence via `tg-review-and-resume.sh`. Restoring an interrupted TG-only job outside that review path requires an explicit, separate, state-aware resume implementation; no automatic retry of an ambiguous Telegram send is authorized.

### Review commands

- OCR noise: Reply to the bot's annotated OCR screenshot with `审核：<job_id>：英文OCR=误识别`. This excludes only the current bound `LATIN_ONLY_OCR_REVIEW` events and retains the original OCR observations and evidence hashes.
- Semantic ambiguity: Reply to the bot's Chinese/Burmese event comparison with `审核：<job_id>：语义：<event_id>：含义=<中文解释>` (4–180 chars). Mac retranslates only that event with the verified context, then executes an independent semantic audit again. The human explanation is **not** a blanket QA pass.
- Subtitle layout: Reply to the bot's position/contact-sheet evidence with `审核：<job_id>：布局=通过`. Approval is bound to the current `evidence_revision`; other blocking codes cannot be cleared by this review.

All other text is rejected or handled as ordinary conversation. The assistant should never instruct the user to edit Mac files or restart a finished job merely to record a review decision.

## Deterministic ingress

Hermes `gateway/run_inbound.py` is minimally patched **after platform admission/auth** and before LLM dispatch, via `scripts/install-hermes-review-ingress.py`. The handler loads the installed `scripts/tg-review-ingress.py`, validates exact command shape, requires the Telegram `reply_to_message_id`, uses a per-job `flock` claim, and invokes the bounded `tg-review-and-resume.sh` script (no user text interpolated into shell). The actual review handler validates chat, job, message ID and evidence/translation hashes. Review commands cannot access arbitrary shell/root tools.

The Hermes source injection is a small **reversible** runtime adapter, not the repo's SOT. It is intentionally protected by an anchored installer to reject incompatible upstream changes; upgrade/reinstall requires re-applying the installer and verifying its status. Rollback: `install-hermes-review-ingress.py remove --gateway-file <Hermes gateway/run_inbound.py>` then restart the dedicated gateway. Original prepatch file is saved beside the Hermes module as `run_inbound.py.y700-review-prepatch`.

The review ingress template now resolves the user's home directory instead of embedding a Mac account path. This intentionally changes its anchored block signature: an already installed legacy block must first be removed with the matching **old** installer, then the updated installer may apply the new block, with a gateway restart and fresh Telegram Reply verification at the separately authorized deployment gate. The updated installer refuses an unrecognized existing block; do not force an in-place string replacement or restart a production gateway during code development.

## QA → TG routing

1. Download and analyze: Chinese ASR/OCR event IDs and timestamps remain immutable; questionable low-confidence text stays `review_required`, not silently dropped.
2. Initial translation (one Chinese event → one Burmese event), independent semantic audit. A `REVIEW_REQUIRED_LAYOUT` result can cause `semantic-audit-auto` to return code 20 **even if all semantic findings pass**; the caller must inspect the actual quality codes rather than treating it as a translation failure.
3. Any OCR/semantic review: `tg-review-next.py` generates the relevant red-frame evidence or per-event bilingual comparison, stores a send intent before transmission, then binds the confirmed Telegram message ID. No duplicate sending after ambiguous delivery.
4. For layout-only warning, `tg-layout-evidence.py` sends video-derived source frames showing original-text regions versus planned Burmese overlay positions. It never treats a human reply as approval for semantic or hard blocking codes.
5. Once QA is `PASS`, render actual Burmese captions, run **post-render Q3** QA and re-evaluate hashes. Only then send MP4 to Telegram.
6. On verified `sendVideo` receipt persist the delivery ID/hash, compact review evidence, and final job state, then remove task-scoped `source/`, `analysis/`, `localization/`, `production/`, `export/`, `evidence/` and task-scoped export cache. Preserve `state.json`, `events.jsonl`, delivery receipt and review-claim metadata. Failed/ambiguous send retains video and intermediate files, requiring reconciliation before retry.

## Verification boundary

- Static checks and scoped regression tests cover the command parser, invalid reply references, OCR decision binding, semantic context preservation, layout approval binding, pre-render versus Q3 QA, acceptance/cleanup, and existing localization integration.
- The 2026-11-02 real `r001` job provided evidence that manual Mac-assisted review, translation, Q3 render, Telegram receipt and cleanup can finish. That run **did not prove** the newly injected deterministic Telegram ingress.
- A *new real Telegram reply* is needed for complete ingress acceptance: match a sent evidence `message_id` to the inbound `reply_to_id`, observe the deterministic review invocation, verify subsequent QA/status and video/cleanup receipts. Do not mark production ingress PASS before this evidence exists.
