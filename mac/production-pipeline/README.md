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

## Telegram control plane

Telegram is intentionally thin. The dedicated Hermes profile accepts explicit `自动发布` / `存到相册` intents, `/resume <job>` or `继续任务：<job>`, `/status`, `/cancel`, and `/help`; a bare Douyin URL does not execute. Every canonical job gets a write-once `workflow_intent` marker so resume cannot upgrade an album-only job into publication. `/resume` runs through `scripts/start-resume-job.sh`; retry-safe phases may continue, while any COMMIT/ambiguous state is handed to closure/reconciliation without a second COMMIT. Runtime bot credentials and allowlist values stay in the Hermes profile `.env`, never in this repository.
