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

### Publish boundary

- TikTok DRY_RUN must stop before the final publish action.
- COMMIT requires explicit user approval for the current content.
- A failed or ambiguous COMMIT is reconciled from durable state/profile evidence before any retry.
- PRIVATE is the default visibility unless the user explicitly requests otherwise.

## Git SOT rule

- `main` on GitHub is canonical for code/config/docs.
- Secrets, runtime state, media, device backups and recovery binaries are external assets.
- Future changes should be made from or reconciled back to this repository; avoid parallel canonical copies.
- Update `CHECKPOINT.md` after accepted gates.
