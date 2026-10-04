# CHECKPOINT

Date: 2026-10-04

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
- at the 2026-10-03 SOT migration closure, the live Y700 workspace was clean and aligned to `origin/main`
- at that closure, the Mac canonical workspace was clean and aligned to `origin/main`

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

## TikTok generic-core DRY_RUN migration — PASS / FROZEN

Validated on the real Y700 on 2026-10-04.

- acceptance baseline: `4c19067bc63d43df1472668ec0abeff98bc82283`;
- TikTok DRY_RUN migrated to the generic Android Automation Core;
- one instrumentation session per workflow;
- semantic selectors only; no absolute coordinates and no implicit first-match/index;
- final TikTok Publish button is asserted only and is never clicked in DRY_RUN;
- PRIVATE visibility is verified;
- 20 cold-start runs: **20/20 PASS (100%)**;
- PRD threshold: >=19/20 PASS;
- host workflow P50: 41,217.9 ms;
- host workflow max: 49,640.7 ms;
- `home-create` max: 9,391 ms after bounding UiAutomator implicit idle waits;
- public-safe evidence: `docs/TIKTOK-GENERIC-DRYRUN-ACCEPTANCE-2026-10-04.md`.

Freeze rule:

- do not modify `apps/tiktok/controller.py` or DRY_RUN routing in
  `publisher/publish_job.py` during remaining Core recovery/evidence work;
- if a future change alters selectors, action order, staging cardinality,
  visibility handling, or driver semantics used by the normal TikTok path,
  reopen and rerun the 20-run gate.

Deployment hardening accepted:

- compare built APK SHA with installed package SHA before install;
- identical packages are skipped;
- changed APKs install via stdin + `pm install -S`, avoiding the observed
  ZUXOS path-based install hang;
- installed SHA is verified after installation;
- instrumentation registration is checked after deployment.

## PRD v0.5 Sprint 6A Bridge v2 — PASS

Validated on the real Y700 on 2026-10-04.

Implemented and accepted:

- filesystem remains the required SOT;
- atomic `.staging -> active` submission;
- active/archive physical separation;
- archive-first race-safe status lookup;
- v1/v2 dual-read migration path;
- immutable claimed requests with SHA-256 binding;
- PID/PGID plus process-start identity evidence;
- heartbeat 2 s / lease 15 s;
- cooperative cancellation for generic `root_exec`;
- no automatic replay of ambiguous side effects;
- live-orphan detection and durable dispatch blocking;
- `RECONCILE_REQUIRED` terminal ambiguity state;
- stale staging visibility and explicit maintenance cleanup;
- bounded durable JSON sizes;
- atomic `control/*.json` publication;
- real failure-injection coverage for claim crash, child-running crash,
  result-before-archive crash, malformed state, request mutation, and timeout;
- generic Settings regression through Bridge v2: PASS;
- cooperative UI action-boundary cancellation: PASS.

Production runtime observation at closure:

- Bridge protocol advertisement: v2;
- no unknown active v2 jobs;
- no incomplete legacy v1 jobs;
- no live-orphan block;
- filesystem transport authoritative;
- Unix socket daemon not enabled.

`active_scan_ms` was corrected to measure filesystem discovery/stat cost only;
job execution time is not included in that metric.

Public-safe evidence: `docs/BRIDGE-V2-ACCEPTANCE-2026-10-04.md`.

The Y700 primary Git worktree currently contains protected local TikTok/UI
migration edits and was intentionally not reset during Bridge v2 closure.
Bridge runtime files were verified byte-identical to the accepted GitHub
implementation before production validation.

Sprint 6B remains closed until a separate measured-need experiment defines and
meets explicit latency/CPU/wakeup thresholds.

## Android Automation Core v0.5 — FINAL ACCEPTANCE

Decision: **PASS WITH PHYSICAL MAC-OFF / EXTERNAL-NETWORK GATE DEFERRED**.

Final runtime/code acceptance baseline:

`6285a6d23b4d33118e0db2cc25f5838d54551644`

Final real-Y700 acceptance on 2026-10-04:

- failure evidence contract: PASS;
- UI observation recovery: PASS;
- semantic scroll: PASS;
- normalized swipe without absolute pixel coordinates: PASS;
- longClick: PASS;
- Unicode input + IME dismiss: PASS;
- unknown selector key fail-closed: PASS;
- Settings reversible flow: PASS;
- Settings acceptance is foreground-aware and session-independent;
- UI cooperative cancellation: PASS;
- safe driver reset: PASS, workflow_replayed=false;
- unsafe checkpoint reset: RECONCILE_REQUIRED, workflow_replayed=false;
- health after both reset paths: HEALTHY;
- permissions: 0700 directories / 0600 files PASS;
- Bridge v2 health: active=0, running=0, orphaned=0, live-orphan block=false;
- root bridge round-trip: PASS;
- TikTok DRY_RUN remains frozen at 20/20 PASS (100%).

One archived Bridge `RECONCILE_REQUIRED` record remains intentionally durable
from the earlier ZUXOS path-based PackageManager install hang. Its process was
explicitly recovered; no live orphan remains; it is historical evidence only.

Physical Mac-Off plus external Wi-Fi / phone-hotspot acceptance is explicitly
deferred by project decision and must not be marked PASS until physically run.

Final public-safe evidence:

`docs/ANDROID-AUTOMATION-CORE-v0.5-FINAL-ACCEPTANCE-2026-10-04.md`

Sprint 6B remains NOT ACTIVATED / NOT REQUIRED unless future measurements show
a real filesystem polling latency/CPU/wakeup problem.

## Business Pipeline Production Closure — A/B/C

Status on 2026-10-04:

- A / Y700 production SOT: **PASS**.
  - old dirty workspace preserved as `/opt/y700/workspaces/y700-agent-legacy-69db187-20261004`;
  - clean release `/opt/y700/workspaces/y700-agent-release-f97bd15` verified against GitHub main;
  - stable production path `/opt/y700/workspaces/y700-agent` now resolves to the clean release;
  - Android host executor restarted from the stable path;
  - Bridge health/root round-trip PASS, no live orphan/block.
- B / Mac production plane SOT: **PASS**.
  - canonical `mac/production-pipeline` bootstrapped with local `.venv`, faster-whisper and `render_text`;
  - `scripts/pipeline.sh` loads Git-ignored `runtime/env.local`;
  - Git SOT deploys media runtime to `~/Library/Application Support/Y700Media` so launchd does not stall on macOS Documents/TCC protection;
  - `mac/media-export/install-launchd.sh` installs/refreshes the generated runtime, server and Cloudflare LaunchAgents;
  - launchd media server serves port 8790 from the deployed runtime export root;
  - canonical Cloudflare connector for `y700media.stanleyxyz.com` registered 4 QUIC connections;
  - old `y700-linux` media server/tunnel stopped but files retained for rollback;
  - real Mac -> Cloudflare -> Y700 handoff smoke reached READY twice, including after launchd migration, with SHA-256 PASS and Burmese text preserved.
- Final Y700 production pointer after CI success: `/opt/y700/workspaces/y700-agent` -> `y700-agent-release-f568284`; host executor restarted from this release; Bridge/root round-trip PASS.
- C / Generic TikTok COMMIT convergence: **CODE + PREFLIGHT PASS; REAL PUBLISH GATED**.
  - DRY_RUN remains unchanged and never clicks Publish;
  - COMMIT routes through Generic Android Core, not legacy `go_to_post_config` / `tap_publish`;
  - COMMIT requires both manifest `publish_mode=COMMIT` and explicit `--commit`;
  - same generic preparation path reaches verified PRIVATE POST_CONFIG;
  - separate commit-preflight reasserts exact caption, PRIVATE, enabled Publish and captures evidence;
  - durable `COMMITTING` is written before the single `EXTERNAL_IRREVERSIBLE` Publish click;
  - any error after entering COMMITTING becomes `AMBIGUOUS_COMMIT_NEEDS_RECONCILE`, `retry_allowed=false`;
  - profile/private verification uses Generic UI evidence;
  - real Y700 preflight-only acceptance PASS with `publish_action_executed=false`.

Remaining hard gate:

- one real PRIVATE COMMIT for a specifically approved current content item;
- exact-caption + PRIVATE profile verification after that publish;
- if the result is ambiguous, run durable reconcile; never blindly retry.

## TikTok PUBLIC publish flow migration — PREFLIGHT ACCEPTED

Production publish visibility was changed from PRIVATE to **PUBLIC** on
2026-10-04. Feature baseline:

`1a0499063d1f6059c4099b1a57b53eb2840f00ca`

Accepted behavior:

- Mac localization/export defaults to `PUBLIC`;
- Y700 manifest/publisher default visibility is `PUBLIC`;
- Generic TikTok DRY_RUN selects `所有人`, verifies the PUBLIC summary and never clicks Publish;
- real Y700 PUBLIC DRY_RUN: PASS;
- final state: `READY_TO_COMMIT`, manifest visibility `PUBLIC`, `published=false`, evidence present;
- Generic COMMIT requires both `publish_mode=COMMIT` and explicit `--commit`;
- real Y700 approval-gate injection without `--commit`: PASS;
- approval-gate result: exit non-zero, zero new TikTok UI jobs, TikTok not foreground, no Publish action;
- durable `COMMITTING` remains before the single `EXTERNAL_IRREVERSIBLE` Publish click;
- after COMMITTING, verification uncertainty remains `AMBIGUOUS_COMMIT_NEEDS_RECONCILE` with `retry_allowed=false`;
- PUBLIC reconciliation begins from the selected Profile `视频` tab, scans current semantic `ev2` tiles, and requires exact caption plus absence of a restricted-visibility label;
- historical PRIVATE reconciliation is retained only for historical PRIVATE published jobs.

Public-safe acceptance evidence:

`docs/TIKTOK-PUBLIC-PUBLISH-MIGRATION-ACCEPTANCE-2026-10-04.md`

Remaining hard gate:

- one real PUBLIC COMMIT for a specifically approved current content item;
- exact-caption PUBLIC Profile verification after that publish;
- ambiguous result must reconcile from durable state/Profile evidence and must never be blindly retried.

## CodexPro full-filesystem access — PASS

Validated on 2026-10-04.

- CodexPro launch policy includes `--allow-root /` in addition to the canonical project roots.
- Cloud ChatGPT successfully opened `/etc` as a CodexPro workspace and read a non-project file.
- The same Y700 CodexPro full-bash successfully listed the Android host `/data/adb` path through `/proc/1/root/data/adb`.
- The temporary bind-mount experiment used during validation was unmounted; no persistent recursive host-root bind was introduced.
- No boot, init_boot, vendor_boot, vbmeta, system, vendor, product, GPT or other critical partition was modified.

## Zygisk Next compatibility layer — PASS

Validated on the real Y700 on 2026-10-04.

- official Zygisk Next 1.5.0 (`843-5217106-release`) installed through KernelSU `ksud module install`;
- release ZIP SHA-256 verified as `474d58abc208c0779e7f8f1d8449db755a874d475c13b9cf8decf74bc171933b` before installation;
- active module id: `zygisksu`; `modules_update` empty after reboot;
- `znctl status`: `inject_state=1`, `zygote_states=1`, KernelSU root version `32601`;
- no Shamiko, Play Integrity Fix, TrickyStore or other Zygisk module installed;
- KernelSU root remains uid 0, Verified Boot remains green, SELinux remains Enforcing;
- CodexPro, Cloudflare tunnel, Android bridge and SSH health: PASS after reboot;
- pre-install KernelSU module backup retained outside Git under local runtime backup storage.



## Telegram Y700 Automation Control Plane v0.1 — CODE / LOCAL PROFILE PREP PASS

Status on 2026-10-04:

- Architecture decision: Telegram is a thin ingress + notification plane; existing Mac production, filesystem-first Y700 bridge and TikTok publisher remain authoritative.
- Dedicated Hermes profile name: `y700automation`; no bundled Skill set is inherited.
- Canonical `douyin-tiktok-publish` Skill is synchronized from `stanleyrprose/chatgpt-skills`.
- Dedicated profile Skill load smoke: PASS.
- Telegram tool surface is reduced to terminal/file/vision/skills/todo/clarify; unrelated web/browser/generation/memory/delegation/cron/computer-use surfaces are disabled.
- Dedicated profile working directory points to a clean GitHub-driven Mac runtime checkout, not the dirty development worktree.
- Clean Mac production pipeline bootstrap: PASS; faster-whisper runtime available.
- Existing local Y700 media server health: PASS (expected HTTP 404 at server root).
- Telegram status sender is best-effort and cannot mutate publisher truth or replay COMMIT.
- Bot token, allowlist identity, home channel/thread and runtime sessions remain outside Git.

Pending live gate:

1. inject the dedicated Telegram bot token and allowlisted user/chat identity;
2. start/install the `y700automation` Hermes gateway;
3. send one real Douyin URL through Telegram;
4. observe RECEIVED -> PRODUCING -> TRANSFERRING -> DRY_RUN -> COMMITTING -> terminal Telegram receipts;
5. verify one-shot PUBLIC publication/reconciliation and no secret/capability leakage.

Do not mark Telegram E2E PASS until the dedicated bot live gate completes.
