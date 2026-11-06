# Douyin → Myanmar → TikTok Production Pipeline

PRD v0.4 Mac production plane.

## Human workflow

1. Paste one Douyin share URL into Cloud GPT **or** send it to the dedicated Y700 Automation Telegram bot.
2. Cloud GPT or the dedicated Hermes `y700automation` profile loads `douyin-tiktok-publish` and calls `scripts/pipeline.sh submit <url>`.
3. Mac/Douzy downloads and generates transcript + contact sheet.
4. Cloud GPT writes evidence-grounded `localization.json`.
5. Mac renders Burmese 1080×1920 output and exports it.
6. The orchestrator sends the manifest URL to Y700 and runs TikTok DRY_RUN.
7. The one-URL standing authorization satisfies the explicit approval gate unless the current turn narrows or revokes it.
8. Y700 performs exactly one PUBLIC COMMIT attempt and verifies/reconciles publication.
9. The orchestrator finalizes the Mac job and, for Telegram ingress, sends status transitions and the terminal receipt back to Telegram.

No MQ, no R2 permanent library, no direct public root shell.

## Commands

```bash
./scripts/bootstrap.sh
bash ./scripts/setup-telegram-control.sh  # no secrets; prepares dedicated Hermes profile
bash ./scripts/tg-notify.sh RECEIVED dy-example --detail '任务已接收'  # after Telegram is configured
./scripts/pipeline.sh submit 'https://v.douyin.com/...'
./scripts/pipeline.sh localize dy-<aweme_id> localization.json
./scripts/pipeline.sh render dy-<aweme_id>
./scripts/pipeline.sh export dy-<aweme_id>
./scripts/pipeline.sh mark-dryrun dy-<aweme_id>
./scripts/pipeline.sh approve dy-<aweme_id>
./scripts/pipeline.sh finalize dy-<aweme_id> --verified --evidence 'profile_private_exact_caption'
```

## Content routing

The worker does not invent language:

- meaningful Chinese speech → `speech_candidate`;
- weak/no speech → `visual_review`;
- Cloud GPT inspects transcript + contact sheet and chooses:
  `speech | visual_text | mixed | visual_only`.

All Burmese localization is stored in a durable `localization.json`.
New localization artifacts require `caption_basis`, recording a concise editorial rationale plus the observable frame/transcript evidence used to create `caption_my`.


## TG-only `下载并缅语化` / `Download and Localize`

This **new** intent does not replace `存到相册` (`STORE_ALBUM` still
delivers to Telegram, Y700 Movies and ZUI Notes). The `TG_LOCALIZED` route
never contacts Y700, Notes or TikTok and does not create a Y700 capability
export.

Use the explicit Telegram command `下载并缅语化：<Douyin URL>`
(`+`, `:`, `：` separators; English alias `Download and Localize:`).
After the authenticated `submit` step produces a canonical job id, the Hermes
orchestrator must immediately persist intent and generate localization from
transcripts/keyframes under the existing evidence and quality contracts. Place
all translation inputs and scratch outputs inside the job-owned localization or
temp directories so the success cleanup removes them; do not create working
artifacts in the repository root:

```bash
bash scripts/pipeline.sh submit '<Douyin URL>'
bash scripts/pipeline.sh set-intent dy-<aweme_id> TG_LOCALIZED
bash scripts/pipeline.sh localize dy-<aweme_id> runtime/jobs/dy-<aweme_id>/localization/translation-input.json
bash scripts/pipeline.sh render dy-<aweme_id>
bash scripts/pipeline.sh tg-finish dy-<aweme_id>
```

`tg-finish` sends the rendered `production/video.my.mp4` with the existing
`sendDocument` sender, requiring the correct Telegram chat, a positive
`message_id`, and a receipt bound to job, intent, size and SHA-256. After
the durable `SENT` checkpoint, it deletes that job's generated source,
analysis, localization, production and export directories and its exact
job-scoped temp directory. The final `TG_DELIVERED` state and a compact
non-media delivery receipt are retained for deduplication and crash recovery;
no original or rendered video remains on Mac.

On missing/uncertain Telegram acknowledgment or invalid size/chat/receipt,
**no cleanup occurs**. An uncertain Telegram send is not retried blindly.
Cleanup can resume after `TG_DELIVERED_CLEANUP_PENDING` without sending again.
`继续任务` supports `LOCALIZED`, `RENDERED`, and cleanup-pending
`TG_LOCALIZED` states; at `ANALYZED`, a new evidence-grounded localization
is required before the deterministic resume controller can proceed.

## Telegram control plane

Telegram is intentionally thin. The dedicated Hermes profile accepts explicit plain-text Chinese/English aliases: `自动发布` / `Automatic Publish`, `存到相册` / `Save to Album`, `直接下载` / `Direct Download`, `下载并缅语化` / `Download and Localize`, `继续任务` / `Resume Task`, `任务状态` / `Task Status`, `取消任务` / `Cancel Task`, and `帮助` / `Help`. English aliases are ASCII case-insensitive; payload-bearing intents accept `+`, `:`, or `：` as equivalent separators. A bare Douyin URL does not execute, and Hermes slash commands are not reused as Y700 workflow controls. Every canonical job gets a write-once `workflow_intent` marker (`AUTO_PUBLISH`, `STORE_ALBUM`, `DIRECT_DOWNLOAD`, or `TG_LOCALIZED`) so resume cannot upgrade an album-only job into publication. Resume runs through `scripts/start-resume-job.sh`; retry-safe phases may continue, while any COMMIT/ambiguous state is handed to closure/reconciliation without a second COMMIT. Runtime bot credentials and allowlist values stay in the Hermes profile `.env`, never in this repository.
