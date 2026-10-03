# Douyin → Myanmar → TikTok Production Pipeline

PRD v0.4 Mac production plane.

## Human workflow

1. Paste one Douyin share URL into Cloud GPT.
2. Cloud GPT calls `scripts/pipeline.sh submit <url>`.
3. Mac/Douzy downloads and generates transcript + contact sheet.
4. Cloud GPT writes evidence-grounded `localization.json`.
5. Mac renders Burmese 1080×1920 output and exports it.
6. Cloud GPT sends the manifest URL to Y700 and runs TikTok DRY_RUN.
7. User approves.
8. Y700 COMMITs and verifies publication.
9. Cloud GPT finalizes the Mac job as VERIFIED.

No MQ, no R2 permanent library, no direct public root shell.

## Commands

```bash
./scripts/bootstrap.sh
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
