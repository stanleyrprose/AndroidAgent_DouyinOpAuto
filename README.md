# AndroidAgent_DouyinOpAuto

Public Git-backed source of truth (SOT) for a Lenovo Legion Y700 / TB323FU Android automation node and its Mac content-production plane.

## What this repository contains

- **Y700 runtime**: Debian chroot, CodexPro development plane, filesystem-first root bridge, health guards, SSH service, and TikTok state-driven publisher.
- **Mac production plane**: Douyin authenticated ingest, media analysis, Burmese localization/rendering, and capability-based artifact export.
- **Root/recovery documentation**: public-safe record of the verified KernelSU/EDL implementation and minimal recovery rules.
- **Operations documentation**: architecture, SSH, SOT policy, and end-to-end workflow.

## Architecture

```text
Cloud ChatGPT
  ├─> CodexPro-Y700 -> Debian chroot -> filesystem jobs -> Android root executor -> TikTok
  └─> Mac production plane -> Douyin ingest -> Myanmar localization/render -> media handoff -> Y700
```

The Mac is content-production and recovery infrastructure. The Y700 is the mobile development/publishing node.

## Current verified status

As of 2026-10-03:

- KernelSU persistent root with locked bootloader: PASS
- Debian 13 ARM64 development plane: PASS
- CodexPro remote development: PASS
- roaming SSH service with public-key-only auth: PASS
- Android root bridge and UI controls: PASS
- health/disk/thermal guards: PASS
- Mac -> Y700 capability-based media pull with SHA-256 verification: PASS
- TikTok PRIVATE DRY_RUN/COMMIT/reconciliation path: PASS
- real Douyin -> Myanmar -> Y700 -> TikTok E2E: PASS
- PRD v0.4 production pipeline: IMPLEMENTED

See `CHECKPOINT.md` for the public-safe acceptance snapshot.

## Repository layout

```text
bridge/                 Android host/root bridge
config/                 non-secret runtime configuration
publisher/              TikTok state-driven publisher
scripts/                Y700 boot/runtime/health/SSH scripts
bootstrap/              public bootstrap helpers
mac/production-pipeline Mac Douyin -> Myanmar pipeline
mac/media-export/       capability-based Mac -> Y700 handoff
docs/                   architecture, recovery and operating docs
```

## Safety / public-repo boundary

This repository intentionally does **not** contain:

- SSH private/public authorization material
- CodexPro bearer tokens
- Cloudflare tunnel credentials
- device serial numbers or raw partition dumps
- firmware/proprietary vendor tool payloads
- downloaded Douyin media or produced TikTok media
- runtime screenshots/UI dumps/logs
- per-job capability URLs

Those are runtime or recovery assets, not source code. See `SECURITY.md`.

## Canonical rule

GitHub `main` is the source of truth for code, scripts, non-secret configuration and public-safe operational documentation. Runtime state and device recovery images remain outside Git and are referenced by policy/checksum, not committed.

See `docs/SOT-POLICY.md`.
