# AGENTS.md

## Scope

This repository is the canonical Git SOT for the Y700 Android automation node plus its Mac content-production plane.

## Authority and boundaries

### Y700 runtime

- Target: Lenovo TB323FU / Android.
- Full Android privilege is exposed through the filesystem-first host executor.
- Cloud ChatGPT via CodexPro must retain full Debian-chroot filesystem scope (`--allow-root /`) rather than being limited to the project workspace.
- Android host filesystem inspection/administration is available from CodexPro full-bash through `/proc/1/root/...`; this does not authorize routine mutation of critical partitions or secret material.
- `/opt/y700/jobs` is durable canonical job state at runtime; runtime state itself is never committed.
- Linux/chroot, CodexPro, bridge and publisher state live under `/data/local` on Android and `/opt/y700` inside chroot.
- Do not modify boot, init_boot, vendor_boot, vbmeta, system, vendor, product, GPT or other critical partitions as part of normal application/runtime work.
- Prefer reversible tests and minimal changes.
- Do not add MQ, sockets, extra daemons or multi-tunnel failover without measured need.

### Mac production plane

- Authenticated Douyin download/ingest.
- Media inspection/transcription and keyframe evidence.
- Burmese localization and rendering.
- Capability-based export to Y700.
- Downloaded/runtime media never enters Git.

### Telegram control plane

- Telegram is a narrow control/notification surface for Y700 automation, not a general-purpose shell or root interface.
- A dedicated Hermes profile must use a dedicated Telegram bot and an allowlisted user/chat identity.
- A bare Douyin share URL is not an execution intent. Production control uses explicit plain-text Chinese or English aliases that normalize to the same workflow intents: `自动发布` / `Automatic Publish`, `存到相册` / `Save to Album`, `直接下载` / `Direct Download`, `继续任务` / `Resume Task`, `任务状态` / `Task Status`, `取消任务` / `Cancel Task`, and `帮助` / `Help`.
- English intent aliases are ASCII case-insensitive and use the same `+`, `:`, or `：` separators as Chinese intents where a payload is required.
- Hermes owns slash-command routing; Y700 workflow controls must not reuse `/resume`, `/status`, `/help`, or other Hermes slash commands.
- Telegram credentials, user/chat ids, runtime sessions and message history remain outside Git.
- Notification delivery failure must not mutate publication truth or cause a COMMIT replay.

### Publish boundary

- TikTok DRY_RUN must stop before the final publish action.
- COMMIT requires explicit user approval for the current content. Under the authorized `douyin-tiktok-publish` workflow, supplying one Douyin URL is that explicit authorization for exactly one PUBLIC COMMIT attempt after DRY_RUN.
- A failed or ambiguous COMMIT is reconciled from durable state/profile evidence before any retry.
- PUBLIC is the default visibility for the production publish workflow. A different visibility requires an explicit user request.

## Default development workflow (aligned with user Personalization)

- Before implementation, inspect the current Git branch, repository rules,
  applicable PRD, and **all GitHub workflow triggers**. Confirm a push to the
  intended development branch **will not trigger CI**; if this cannot be verified,
  do not push until the trigger configuration is safely resolved.
- Implement on a separate Mac **development branch**. During development,
  perform code changes and necessary static inspections only: **do not run tests,
  create a PR, invoke CI, merge or deploy**.
- **Commit locally and push the development branch to GitHub as the development
  source of truth (SOT)** throughout implementation. Never push unfinished code
  directly to `main`. Recheck CI triggers before pushing if workflows or branch
  rules have changed. Do not create a PR just to synchronize code.
- **Only after all requested code work and human reviews are complete**, enter
  the concentrated verification and closure phase: run affected-path tests,
  fix failures, validate results, then create a PR, run CI, and merge after
  checks pass. Do not start this phase early.
- GitHub development branches are the SOT for work in progress; GitHub `main`
  remains the canonical SOT for accepted code. Keep secrets and runtime media
  outside Git, and leave Mac release aliases, Y700 and TikTok publishing
  untouched unless separately authorized.

## Git SOT rule

- `main` on GitHub is canonical for code/config/docs.
- Secrets, runtime state, media, device backups and recovery binaries are external assets.
- Future changes should be made from or reconciled back to this repository; avoid parallel canonical copies.
- Update `CHECKPOINT.md` after accepted gates.
