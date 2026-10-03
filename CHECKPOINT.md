# CHECKPOINT

Date: 2026-10-03

This is the public-safe acceptance snapshot. Private runtime identifiers, endpoints, test screenshots, real sample URLs and device backup names are intentionally omitted.

## Device foundation — PASS

- Target: Lenovo TB323FU / Android 16 / aarch64
- Bootloader: locked
- KernelSU root: uid=0
- SELinux: Enforcing
- Root survives reboot: PASS
- BL unlock is not required by the runtime
- Normal runtime work does not modify critical partitions

## Linux / development plane — PASS

- Debian GNU/Linux 13 (trixie)
- Node.js 20.x
- npm 9.x
- Python 3.13.x
- Git 2.47.x
- ffmpeg 7.x
- CodexPro-Y700 0.30.x
- Cloud ChatGPT direct open/read/write/bash: PASS
- Canonical device workspace: `/opt/y700/workspaces/y700-agent`

## Remote development — PASS

- Cloudflare Named Tunnel path: PASS
- Bearer authentication: PASS
- boot auto-recovery: PASS
- Wi-Fi loss/reconnect recovery: PASS
- post-recovery health: HEALTHY

Public hostnames and credential material are not part of this repository.

## SSH plane — PASS

- OpenSSH server in Debian chroot
- port 2222
- public-key-only root authentication
- password login disabled
- boot persistence wired
- `sshd -t`: PASS
- live service status: PASS

Authorized keys and runtime IP addresses remain local-only.

## Filesystem-first Android bridge — PASS

- active jobs: `/opt/y700/jobs`
- completed root jobs archived outside the active directory
- root_exec round-trip: PASS
- push/pull file round-trip: PASS
- privileged read/write test: PASS
- package/process control: PASS
- screenshot/UI dump/launch/tap/swipe/Unicode input: PASS
- keyguard detection/dismiss: PASS

Observed performance: moving hundreds of completed jobs out of the active job directory reduced root-exec latency from multi-second range to sub-second range.

## Health / guards — PASS

- continuous health loop: PASS
- disk guard normal path: PASS
- forced low-disk block: PASS
- thermal guard normal path: PASS
- forced thermal block: PASS

## Mac -> Y700 media handoff — PASS

- Mac local media server + Cloudflare handoff: PASS
- random per-job capability URLs: PASS
- no directory listing: PASS
- TTL enforcement: PASS
- manifest/video/caption/metadata pull: PASS
- SHA-256 validation: PASS
- incoming -> ready transition: PASS
- Burmese text preservation: PASS

## TikTok publisher — PASS

State-driven flow:

```text
HOME -> CREATE -> GALLERY -> EDIT -> POST_CONFIG
```

Verified:

- isolated automation-owned media album
- MediaStore staging
- Unicode Burmese caption input
- normal IME restoration
- PRIVATE visibility selection
- DRY_RUN hard-stop at final publish control
- COMMIT requires both commit-mode manifest state and explicit command
- duplicate publication guard
- ambiguous COMMIT reconciliation without blindly tapping Publish

## Real Douyin -> Myanmar -> Y700 -> TikTok E2E — PASS

A real Douyin-produced artifact completed the full chain on 2026-10-03:

```text
authenticated Douyin ingest
-> Mac analysis
-> evidence-grounded Myanmar localization
-> 1080x1920 render
-> capability handoff
-> Y700 pull + SHA-256
-> TikTok state-driven publisher
-> PRIVATE COMMIT
-> Profile verification
```

The public repository deliberately omits the source URL, aweme identifier, screenshots, exact caption and per-job capability URL.

## PRD v0.4 production pipeline — IMPLEMENTED

Implemented on the Mac plane:

- one-link Douyin ingestion
- authenticated downloader integration
- durable per-job state
- URL + aweme dedupe
- local speech transcription
- speech-vs-visual evidence routing
- contact-sheet evidence
- `localization.json` contract
- Burmese timed-cue rendering
- 1080x1920 H.264/AAC output
- capability-based media export

Implemented on Y700:

- asynchronous publish runner
- status polling
- duplicate-run protection
- pre-COMMIT source dedupe
- durable publisher state
- ambiguous-COMMIT reconciliation

## Git SOT migration — PASS

Canonical repository:

- GitHub: `stanleyrprose/AndroidAgent_DouyinOpAuto`
- canonical branch: `main`
- accepted source commit: `d35482f`
- GitHub Actions `validate`: PASS
- live Y700 workspace: clean and aligned to `origin/main`
- Mac canonical workspace: clean and aligned to `origin/main`

Public SOT provenance:

- initial Y700 source snapshot: `c145f41`
- initial Mac production pipeline snapshot: `d0c96a0`
- root/recovery verification: 2026-10-02
- UI automation/runtime SOT capture: `d35482f`

The public history is intentionally scrubbed. Runtime secrets, media, UI evidence, device identifiers and binary recovery assets remain outside Git.

Closure verification on 2026-10-03:

1. Mac production/media-export source imported: PASS;
2. public-repo privacy/secret scan and minimal tests: PASS;
3. GitHub `main` push: PASS;
4. live Y700 workspace aligned to GitHub `main`: PASS;
5. Y700 Python UI-runner compile smoke: PASS;
6. Y700 health check: HEALTHY;
7. Y700 SSH service: RUNNING;
8. GitHub Actions validation for `d35482f`: PASS.

Rollback references retained locally on Y700:

- `legacy-local-c145f41`
- `y700-live-pre-sot-4287725`

From this checkpoint onward, GitHub `main` is the sole source of truth for code, scripts, non-secret configuration and public-safe project documentation. Emergency live-device fixes must be reconciled back into Git immediately after stabilization.

## PRD v0.5 Rev2 Android Automation Core — Sprint 0–5 PASS

Validated on 2026-10-03.

Implemented:

- AndroidX UI Automator 2.4.0 production driver;
- workflow-scoped instrumentation sessions;
- durable atomic UI jobs with heartbeat/journal/checkpoint;
- semantic selectors with deterministic 0/1/many behavior;
- relation selectors;
- click/long-click/input/clear/swipe/scroll/wait/assert;
- AndroidX waitStable;
- bounded retry/backoff;
- root-only 0700/0600 runtime permissions;
- driver health/permission probes;
- safe driver reset and RECONCILE_REQUIRED for unsafe checkpoints;
- screen-off wake + keyguard preflight;
- direct Mac build/release deployment over Cloudflare SSH;
- generic Android Settings acceptance.

Real Settings acceptance:

```text
Light -> temporary Dark -> verified -> restored Light -> verified -> HOME
```

The two-pane Settings false-positive was fixed by validating the actual checked
state of `dark_mode_white_check` / `dark_mode_black_check`, not by merely
checking whether the text `深色模式` remained visible in the left search pane.

Runtime acceptance reports `mac_runtime_required=false` and uses semantic
selectors only; no absolute coordinates are used. The hard physical Mac-Off
gate is still pending and must not be marked PASS until the Mac is actually
powered down during the acceptance run.

Next implementation gate: migrate the TikTok controller to the generic core,
then run 20 cold-start DRY_RUN regressions with >=95% success.

