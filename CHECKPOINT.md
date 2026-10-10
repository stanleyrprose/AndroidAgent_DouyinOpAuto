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

## Root compatibility baseline — PASS / STRONG not required

Validated on the real Y700 after enabling Zygisk Next 1.5.0.

- Play Integrity API Checker installed from Google Play: `MEETS_BASIC_INTEGRITY=PASS`, `MEETS_DEVICE_INTEGRITY=PASS`, `MEETS_STRONG_INTEGRITY=FAIL`.
- Current automation requirement does not require STRONG integrity; no Play Integrity Fix, TrickyStore or Shamiko was added.
- TikTok cold launch reached `MainActivity`, and semantic recovery reached authenticated HOME with the create control visible; no root/Zygisk block was observed.
- Existing legacy PRIVATE DRY_RUN fixtures are intentionally rejected by the current v0.5 PUBLIC-only fail-closed policy; no manifest was modified to bypass that guard.
- Google Play certification menu was not directly captured because ZUI foreground/accessibility window reporting was inconsistent; no certification claim is inferred from that missing UI observation.

## Final Git SOT deployment + reboot acceptance — PASS

Validated on the real Y700 after deploying GitHub `main` runtime code commit `cdade643861555e5635f7e9d53c862194346a902` as an immutable release and atomically switching the canonical workspace symlink.

- previous release retained for rollback; no in-place mutation of the prior release;
- full device reboot: PASS; `sys.boot_completed=1` after autonomous recovery;
- KernelSU root, Verified Boot green and SELinux Enforcing survived reboot;
- Zygisk Next 1.5.0 recovered with `inject_state=1` and `zygote_states=1`;
- host executor, SSH, Cloudflare tunnel, CodexPro and health loop restarted automatically;
- Cloud ChatGPT reconnected directly to Y700 after reboot; CodexPro retained full Debian chroot scope with `allowedRoots` including `/`;
- Android root bridge round-trip: PASS;
- TikTok cold-launch state reached authenticated HOME after the normal post-boot keyguard window settled;
- TikTok HOME detection was hardened against obfuscated resource-ID drift by accepting stable bottom-navigation semantics while retaining the legacy selector path;
- a short post-boot keyguard race was observed twice; no lock bypass was added, and retrying after keyguard cleared succeeded;
- PUBLIC DRY_RUN end-to-end acceptance is intentionally deferred pending separate discussion; no upload/publish path was exercised in this gate.

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

## Vision Locator PRD v0.3 Sprint V0 — PASS

Final reproducible Gate V0 run executed on the real Y700 on 2026-10-05. Scope remains benchmark / feasibility only.

Accepted benchmark source/build/result commit: `979c5779f8a1a1c5b8fd842f93371364b6954609`.

Accepted implementation and evidence:

- Vision is a locator backend inside the Generic Android Automation Core, not a
  second workflow engine;
- production `runWorkflow` remains semantic-first and is not wired to Vision;
- OpenCV 4.12 template matching validated on a real custom Canvas target with no
  useful semantic child selector;
- Android-side in-memory capture selected as primary from measured evidence;
- final reproducible in-memory capture warm P50/P95: 39.35 / 47.04 ms;
- 200-run capture stability P50/P95: 35.93 / 47.58 ms;
- raw `screencap` P50/P95: 93.75 / 129.14 ms and retained only as a
  diagnostic/fallback path;
- raw frame profile validated as a 16-byte four-field Android profile at
  1904x3040 RGBA_8888, not assumed to be a legacy 12-byte header;
- 250x250 ROI single-scale P50: 7.25 ms;
- 500x500 ROI single-scale P50: 14.10 ms;
- full-screen single-scale P50: 419.92 ms;
- alpha-mask 500x500 ROI P50: 23.96 ms;
- narrow 0.90-1.10 multi-scale 500x500 ROI P50: 105.51 ms;
- measured search policy is ROI-first, single-scale first, narrow multi-scale
  only when justified, full-screen last;
- low-information masked-template false positive demonstrated and blocked by
  variance guard;
- exactly-one capture retry and repeated-failure fail-closed: PASS;
- rotation/geometry race blocks action with zero click: PASS;
- stale-frame fingerprint blocks action: PASS;
- memory-pressure watermark fail-closed: PASS;
- peak concurrent full-resolution frames across 200 captures: 1;
- final post-GC managed/native memory deltas were negative;
- benchmark-only locate -> EXACT click -> visual postcondition: PASS;
- existing real Settings reversible semantic acceptance rerun: PASS,
  `selector_mode=semantic`, no absolute coordinate, Mac not required at runtime.

Routing policy is frozen at the V0 boundary:

```text
semantic RESOLVED -> semantic only
semantic unresolved/ambiguous/unreliable
  -> explicit vision fallback required
  -> template before OCR
external irreversible / COMMIT -> Vision DENY by default
```

Gate V0 passing does not enable production Vision automatically.
`vision_enabled=false`, benchmark-only mode and OCR-disabled remain the
fail-closed runtime defaults until separately authorized V1/V2 work.

Public-safe evidence:
`docs/VISION-V0-ACCEPTANCE-2026-10-05.md`.

Sprint V1 production Template Vision was separately authorized on 2026-10-05.
Sprint V2 OCR Benchmark & Integration was separately authorized on 2026-10-05 by the user's instruction to continue the PRD.
Sprint V3 hybrid routing remains **NOT AUTHORIZED / NOT STARTED**.

## Vision Locator PRD v0.3 Sprint V1 — PASS

Accepted on the real Y700 on 2026-10-05.

- branch acceptance baseline: `feat/vision-locator-v1`, code commit `249c541`;
- architecture remains semantic-first with explicit `vision_template` fallback
  only; click/postcondition/recovery/evidence stay shared with the Android
  Automation Core; high-risk/external irreversible Vision remains denied by default;
- OpenCV 4.12 native loading is closed on Android 16:
  `packaging.jniLibs.useLegacyPackaging=true` yields
  `extractNativeLibs=true`, `libopencv_java4.so` and `libc++_shared.so`
  are present, and the target app initializes OpenCV through
  `OpenCVLoader.initLocal()` in the target-app classloader/native namespace;
- the OpenCV AAR naming mismatch was explicitly handled: the packaged/StaticHelper
  library is `opencv_java4`, while `Core.NATIVE_LIBRARY_NAME` reports
  `opencv_java4120`;
- single real Vision fallback smoke: PASS, `locator_source=vision_template`,
  confidence approximately 0.9544, shared postcondition PASS;
- final durable Gate result:
  `/opt/y700/runtime/vision-v1/vision-v1-20261005-074917.json`;
- Gate V1: **20/20 locate-click-postcondition PASS (100%)**;
- semantic-first path: PASS with no unnecessary Vision request;
- alpha template, ambiguity fail-closed, bad template SHA fail-closed,
  postcondition-failure evidence, high-risk block, and Vision-disabled rollback:
  all PASS;
- wrong-target destructive actions: **0**;
- absolute-coordinate primary path: **not used**;
- 20-run host latency: P50 **5305.7 ms**, max **6708.5 ms**;
- Python Vision policy/evidence regression: 13/13 PASS;
- TikTok/state/publish routing regression: 19/19 PASS;
- artifact gateway regression: 4/4 PASS;
- Android app + androidTest build and Python compile checks: PASS;
- public-safe acceptance evidence:
  `docs/VISION-V1-ACCEPTANCE-2026-10-05.md`.

Mac -> Y700 APK transport is also accepted in this V1 work:

```text
Mac build
-> capability-scoped artifact manifest
-> Y700 HTTPS pull to .part
-> byte-size + SHA-256 validation
-> atomic completed bundle
-> second SHA-256 gate
-> root bridge / pm install
```

SSH/CodexPro remains the control plane; large APK bytes no longer rely on SCP.
The accepted candidate installed hashes are:

```text
app  = f2c691a71dfcb9471dd65b0b0a640ffe6efb0535ac5b17ef0391abb6e96d9e43
test = 35578bc7ae8d2823aae596907bd3c0abc2610cd6eb83c488930ad3302d09bb8f
```

Recurring Cloudflare connector loss is hardened by `c758444`: the existing health
loop may restart the same cloudflared connector after a bounded cooldown; no
second daemon or failover tunnel is introduced.

Accepted capability state at the Sprint V1 freeze point (historical; superseded by the Sprint V2 section below):

```text
Template Vision capability = READY
default/global Vision routing = OFF unless explicitly requested
OCR = OFF
Sprint V2 OCR = NOT STARTED at V1 freeze time
Sprint V3 hybrid routing = NOT STARTED
```

Pre-V1 installed app/test APK backups remain on Y700 under
`/data/local/y700-agent/runtime/automation-driver/backups/pre-v1-20261005`.

Production closure on 2026-10-05:

- accepted feature history was fast-forwarded to GitHub `main` at `330be74`;
- immutable Y700 release `/opt/y700/workspaces/y700-agent-release-330be74`
  was created from exact `origin/main`, verified clean, and passed all 36 directly
  affected Python regressions plus compile/shell checks;
- stable production pointer `/opt/y700/workspaces/y700-agent` was atomically
  switched from `y700-agent-release-a0dc24d` to `y700-agent-release-330be74`;
- previous release `y700-agent-release-a0dc24d` is recorded in
  `/opt/y700/runtime/deploy-previous-release` for symlink rollback;
- host executor restarted from the new stable path; health reported CodexPro,
  Cloudflare tunnel, Android bridge and job directory HEALTHY; root round-trip PASS;
- post-release real-device semantic sanity: PASS with `locator_source=semantic`;
- post-release real-device Vision sanity: PASS with
  `locator_source=vision_template`, confidence approximately 0.9544 and shared
  postcondition PASS.

## Vision Locator PRD v0.3 Sprint V2 OCR — PASS / FROZEN

Accepted on the real Y700 on 2026-10-06. Gate code baseline: `a31cd65` on
`feat/vision-locator-v2`, with current `main` as an ancestor.

Selected runtime: **PaddleOCR PP-OCRv6 tiny / Android ARM64 / ONNX Runtime /
OpenCV 4.12**, runtime id `paddle-ppocrv6-tiny-onnx`.

Candidate decision and real-device acceptance:

- bundled ML Kit clean rerun: **79/99 = 79.80%**, rejected below the frozen
  >=96% target-location threshold;
- selected PaddleOCR clean real-Settings dataset: **96/99 = 96.97%**, PASS;
- dataset: **6 real Android Settings screens / 99 targets**;
- accepted confidence threshold remains **0.85**; no generic `0/O` or `1/l`
  fuzzy matching was added;
- request ROI remains the acceptance/click boundary; bounded 512 px minimum
  inference-context retry is allowed only to improve OCR recognition, with the
  returned bbox still required inside the original request ROI;
- contract: 7/7 PASS; normalization/context: 7/7 PASS; cache/timeout: 2/2 PASS;
  lifecycle: 1/1 PASS; cold latency: 1/1 PASS; real dataset: 1/1 PASS;
  200-run stress: 1/1 PASS;
- final canonical Gate evidence:
  `/opt/y700/runtime/ocr-v2/ocr-v2-component-gate-20261006-090839.json`.

Final latency/resource evidence:

```text
cold request, 20 confirmed-unloaded runs:
  P50 63.72 ms / P95 109.05 ms
runtime cold-load component:
  P50 34.00 ms / P95 46.40 ms
warm OCR, 200 runs:
  P50 43.66 ms / P95 49.78 ms
clean real-dataset target wall latency:
  P50 32.41 ms / P95 60.66 ms
thermal delta across 200 warm runs: 0 C
```

- warm stress: **200/200 success**, timeout count 0;
- warm PSS delta: +128,381 KB; native-heap delta: +94,459,072 bytes;
- after unload: 54,808 KB PSS and 87,836,896 bytes native memory reclaimed;
- production lifecycle defaults remain 10-minute idle timeout and 60-second
  minimum post-load residency; load/unload is serialized and in-flight-safe.

Low-confidence no-click was verified end-to-end through the shared Action
Executor path. A normal `vision_text` action resolved `继续` at approximately
0.99999815 confidence and passed click/postcondition. Repeating from
`clicked=false` with `min_confidence=1.0` failed closed with
`VISION_OCR_NOT_FOUND`, recorded `ocr_low_confidence_rejected_count=1`, had
`ocr_success_count=0`, contained no `click_point`, and its failure-time UI tree
contained no `VISION_V1_CLICKED`.

Accepted Gate candidate APK hashes:

```text
app  = c134512e24008475a341dea3fbafdf106a19380971ae520b2950ee94969cd13d
test = 7f58a59300c5222c054f906e9fd6886feebc27f3376acad36575afb40ce5c4be
```

Frozen post-V2 capability state:

```text
Semantic Locator = primary
Template Vision = explicit fallback
OCR capability = READY via explicit vision_text
OCR default = OFF
external irreversible / COMMIT Vision = DENY
mixed Template + OCR hybrid routing = NOT ENABLED
Sprint V3 = AUTHORIZED / IN PROGRESS at this post-V2 checkpoint (superseded below)
```

Detailed implementation and acceptance evidence:
`docs/VISION-V2-IMPLEMENTATION.md` and
`docs/VISION-V2-ACCEPTANCE-2026-10-06.md`.

Production closure on 2026-10-06:

- GitHub `main` was fast-forwarded to `744e5a2` after clean pre-merge validation;
- clean final worktree: 111 related Python regressions PASS, Python compile PASS,
  shell syntax PASS, Android debug/app-test build PASS;
- immutable release `/opt/y700/workspaces/y700-agent-release-744e5a2` was created
  from exact `origin/main`, verified clean and passed the same 111 Y700-side
  regressions plus compile/shell checks;
- stable `/opt/y700/workspaces/y700-agent` was atomically switched from
  `y700-agent-release-5c9fb8c` to `y700-agent-release-744e5a2`; rollback pointer is
  `y700-agent-release-5c9fb8c`;
- post-promotion health: `production_sot=HEALTHY`, one host executor instance,
  Cloudflare tunnel healthy and Android bridge healthy;
- installed production APK hashes exactly match the accepted V2 Gate hashes;
- semantic production sanity PASS (`locator_source=semantic`);
- Template Vision production sanity PASS (`locator_source=vision_template`,
  confidence approximately 0.95442647, postcondition PASS);
- explicit OCR production sanity PASS (`locator_source=vision_text`, confidence
  approximately 0.99999815, postcondition PASS);
- OCR remained default OFF at the V2 production closure; V3 hybrid routing was not yet enabled at that historical checkpoint.

Current-production V2 revalidation on 2026-10-07: **PASS**.

- fixed a production-path integrity defect where an absolute stable symlink target made
  Android-host jobs unable to resolve `bridge/android-runtime-env.sh`; stable release
  promotion now uses a relative release basename and `production-sot-status.sh` flags
  an absolute stable symlink as `DRIFT`;
- production baseline for this revalidation: `3b93308`, raw stable target
  `y700-agent-release-3b93308`, rollback `y700-agent-release-a428cf3`,
  `production_sot=HEALTHY`, one Android bridge instance and overall health HEALTHY;
- fresh V2-only semantic / template / explicit `vision_text` sanity jobs all PASS with
  hybrid fallback count 0;
- full current-production V2 component Gate PASS at
  `/opt/y700/runtime/ocr-v2/ocr-v2-component-gate-20261007-065959.json`:
  7/7 contract, 7/7 normalization/context, 2/2 cache/timeout, lifecycle PASS,
  cold-latency PASS, 96/99 real-dataset accuracy PASS, 200-run stress PASS;
- current measured cold P95 96.17 ms, warm 200-run P95 49.09 ms, thermal delta 0 C;
- low-confidence no-click remains PASS: `ocr_success_count=0`, rejected count 4,
  no `click_point`, no clicked marker in failure tree. The current shared executor
  reports terminal `VISUAL_TIMEOUT` after bounded retries instead of the historical
  V2 `VISION_OCR_NOT_FOUND`, but the safety invariant remains intact;
- durable summary:
  `/opt/y700/runtime/ocr-v2/current-revalidation-20261007/current-production-v2-revalidation-summary.json`;
- detailed record: `docs/VISION-V2-REVALIDATION-2026-10-07.md`.

## Vision Locator PRD v0.3 Sprint V3 — PASS / FROZEN / PRODUCTION AUTHORIZED

A real-Y700 V3 engineering gate was run on 2026-10-07 at code baseline `7d73357` on
`feat/vision-locator-v3`, with `origin/main` as an ancestor. On 2026-10-08 the user
explicitly authorized Sprint V3 production hybrid routing. A clean device-global-lock
serialized current-main revalidation then passed 20/20 cold-start mixed workflows with
zero duplicate target actions and zero duplicate commit actions. Production promotion
is accepted. The authorization enables bounded multi-candidate Vision fallback when
explicitly requested; global/default Vision routing remains OFF.

Implemented/frozen V3 behavior:

- deterministic semantic -> template -> OCR cascade;
- semantic success bypasses Vision;
- mixed fallback request order is normalized so template executes before OCR;
- request/effective-ROI fingerprint participates in cache/change validation;
- stale/rotation-invalid targets are discarded before input and may re-resolve once;
- postcondition failure after input does not cascade to another locator/action;
- known-popup recovery is package/context bound and follows semantic dismiss ->
  bounded template dismiss -> workflow failure;
- OCR observation cache is explicitly invalidatable and package/geometry aware;
- Vision success evidence is metadata-first; unnecessary full screenshots are not
  persisted on normal successful routes;
- external irreversible / COMMIT Vision remains denied by default;
- shared Action Executor, postcondition, Bridge v2 durable job state and existing
  workflow model remain authoritative.

Final durable Gate result:

```text
/opt/y700/runtime/vision-v3/vision-v3-20261006-185335.json
```

Gate V3 acceptance:

- semantic-only no-regression: PASS;
- invalid recovery config fail-closed: PASS;
- template -> OCR hybrid fallback: PASS;
- representative mixed sample: PASS;
- known semantic popup recovery: PASS;
- known bounded-template popup recovery: PASS;
- stale-target pre-action re-resolution: PASS;
- external irreversible Vision block: PASS;
- metadata-only route evidence: PASS;
- 20 cold-start mixed workflows: **20/20 PASS (100%)**;
- duplicate target actions: **0**;
- duplicate commit actions: **0**;
- click-count postcondition proof: PASS.

Accepted 20-run cold-start end-to-end workflow latency:

```text
P50 = 5815.1 ms
P95 = 7000.8 ms
max = 8782.2 ms
```

Accepted candidate APK hashes:

```text
app  = 791478bb3ee74dca52503bbd62fa704143f76de3ed485d4a7d1412c129268956
test = 38566b77fa65afc24bf0eea5d58ad04205ece265b326639ac0d16dd9bf6f877f
```

One repeated Gate run exposed a benchmark-only representative mixed-request OCR
flake while the frozen 20-run suite still completed 20/20 PASS with valid
template-miss -> OCR metadata. The harness was hardened so the required cold-start
suite itself may provide routing/evidence proof; the >=19/20 threshold and complete
`mixed_pass()` route/postcondition contract were not weakened. The final accepted
run did not require that fallback because the representative mixed sample also
passed.

Final production-authorization revalidation on 2026-10-08:

```text
/opt/y700/runtime/vision-v3-production-final/vision-v3-20261008-034238.json
status = PASS
cold-start mixed workflows = 20/20 PASS (100%)
semantic-only no-regression = PASS
template -> OCR fallback = PASS
known semantic popup recovery = PASS
known bounded-template popup recovery = PASS
stale-target pre-action re-resolution = PASS
external irreversible Vision = BLOCKED
metadata-only route evidence = PASS
duplicate target actions = 0
duplicate commit actions = 0
P50 = 6040.7 ms
P95 = 7002.2 ms
max = 7010.9 ms
```

This rerun was serialized by the device-global Vision V3 acceptance lock; no second
acceptance process operated the UI concurrently.

Frozen post-V3 capability state:

```text
Semantic Locator = primary
Template Vision = READY fallback
OCR Vision = READY fallback
Hybrid semantic -> template -> OCR routing = READY / AUTHORIZED WHEN EXPLICITLY REQUESTED
global/default Vision routing = OFF
OCR default = OFF unless explicitly enabled in Vision policy
known popup recovery = READY, package/context bound
stale-target pre-action re-resolution = READY, bounded once
external irreversible / COMMIT Vision = DENY by default
```

Detailed evidence:
`docs/VISION-V3-IMPLEMENTATION.md`,
`docs/VISION-V3-ACCEPTANCE-2026-10-07.md`, and
`docs/VISION-V3-PRODUCTION-ACCEPTANCE-2026-10-08.md`.

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

## TG → TikTok zero-touch E2E — PASS / FROZEN (2026-10-05)

Frozen runtime/code baseline: `0dc50cf`.

Acceptance job: `dy-7692795483655254393` / aweme `7692795483655254393`.

Accepted path:

`Telegram Douyin URL -> Mac production -> Burmese localization schema v2 + caption_basis -> Y700 handoff -> TikTok DRY_RUN -> exactly-one PUBLIC COMMIT -> exact-caption public verification -> Mac VERIFIED -> Telegram terminal receipt`.

Acceptance evidence:

- Mac production runtime pinned to `0dc50cf` and accepted job reached `VERIFIED`;
- Y700 canonical runtime pinned to `0dc50cf` and durable publisher state reached `PUBLISHED`;
- visibility was `PUBLIC`;
- `submission.accepted=true` with `generic_commit_dispatched`;
- publication verification passed with `generic_profile_public_exact_caption`;
- published job directory exists;
- the accepted localization artifact used schema v2 and included `caption_basis`;
- the run completed zero-touch from Telegram ingress through publication/final state without ChatGPT/manual command handoff.

Frozen contracts and evidence are documented in
`docs/TG-TIKTOK-ZERO-TOUCH-E2E-ACCEPTANCE-2026-10-05.md`.

Freeze refs:

- annotated tag: `tg-tiktok-zero-touch-e2e-v1.0.0` -> `0dc50cf`;
- freeze branch: `frozen/tg-tiktok-zero-touch-e2e-v1` -> `0dc50cf`.

Future changes must preserve this accepted path or establish a new acceptance baseline.

## Y700 locked-screen PUBLIC publish — PASS (2026-10-06)

Acceptance job: `dy-7686483339214313198` / aweme `7686483339214313198`.

Result: Y700 was explicitly put to sleep before the accepted run. Durable Bridge
history then recorded production secure-unlock / wake activity, followed by a
successful exactly-once PUBLIC TikTok COMMIT and
`generic_profile_public_exact_caption` verification. Mac final state is
`VERIFIED` and the Telegram terminal notification was sent.

The first attempt exposed that preflight/MediaStore staging ran before secure
unlock. PR #10 fixed the ordering to
`UNLOCKING -> PREFLIGHT -> STAGING -> TikTok cold-launch`, retained the existing
cold-launch keyguard recheck, and bounded staging root-exec/provider waits.

Acceptance evidence and boundary are documented in
`docs/Y700-LOCKSCREEN-PUBLIC-PUBLISH-ACCEPTANCE-2026-10-06.md`.

This acceptance covers normal sleep/lock. Post-reboot Direct Boot remains a
separate, unaccepted scenario.

## Android Automation Core v0.6 Rev3.6 Phase 0B — TOOLING / CI PASS; REAL-DEVICE EMPIRICAL GATES BLOCKED (2026-10-06)

Canonical implementation-input SOT:

- `docs/PRD-Y700-AAC-v0.6-Rev3.6-Frozen.md`;
- merged by PR #19 into GitHub `main`;
- merge commit: `14b46cd3191e3880284910749510d14a663977ac`;
- post-merge GitHub Actions `validate`: PASS.

Accepted Phase 0B scope now present in Git SOT:

- machine-readable validation tooling under `scripts/v06/`;
- semantic-v1 fixed-vector and fingerprint-profile reference checks;
- UI mutation / pressHome / pressBack / subordinate-job inventory fixtures;
- Catalog overlay-policy / readiness / claim-session reconcile fixtures;
- real-device evidence collectors for runtime permissions, process visibility,
  BOOTTIME/suspend, synthetic admission/fsync load, app/UI identity, ZUI overlay
  inventory, suspend/wake-lock policy and upgrade blockers;
- fault-injection harness self-tests under `tests/fault_injection/`;
- hardware-independent frozen-contract checks wired into CI.

Authorization boundary remains unchanged:

- Production Runtime Implementation Authorization = NO;
- no production Gateway/Core/Bridge behavior change is accepted by this gate;
- no BUSINESS capability activation is accepted by this gate;
- Sprint 1+ implementation remains blocked until the Rev3.6 Phase 0 empirical
  subset passes and a separate Production Runtime Implementation Authorization
  decision is made.

Real-device empirical status at this checkpoint:

- Y700 direct CodexPro connector: unavailable due connector internal error;
- Mac -> Y700 Cloudflare SSH path: unavailable;
- Cloudflare edge probe for the Y700 SSH hostname returned HTTP 530 and the SSH
  proxy reported `websocket: bad handshake`;
- therefore no Rev3.6 real-device empirical gate is marked PASS in this
  checkpoint;
- in particular, controlled suspend/wake evidence and full ZUI overlay-scenario
  coverage remain open and must fail closed until real evidence is collected.

Next gate after Y700 connectivity is restored:

1. align the canonical Y700 workspace to current GitHub `main`;
2. run all P0B_PRE_IMPLEMENTATION empirical checks on the real Y700;
3. collect controlled suspend/wake and overlay scenario evidence;
4. close any failed pre-implementation checks;
5. only then review whether Production Runtime Implementation may be authorized.

## Android Automation Core v0.6 Rev3.6 — PHASE 0 AUTHORIZATION GATE PASS (2026-10-06)

Decision: **PASS for the Rev3.6 Phase 0A/0B pre-implementation gate only.**

Accepted Git baseline:

- Rev3.6 Frozen implementation-input SOT is in `docs/PRD-Y700-AAC-v0.6-Rev3.6-Frozen.md`;
- Phase 0B validation tooling is merged to `main`;
- final validation-tooling baseline: `abc5333864a9b928ce16bfcecf157a7081e623e0`;
- GitHub Actions `validate` after PR #21 merge: PASS;
- real-device validation ran from a clean immutable Y700 worktree at the exact accepted baseline.

Real-Y700 pre-implementation evidence:

- preflight: PASS with clean Git, boot completed, Android root round-trip PASS, installed automation APK SHA evidence captured, `active_bridge_jobs=0`, and no current durable `android_ui` claim;
- runtime permission baseline: PASS after one explicitly audited ADMIN repair changed `/opt/y700/runtime/state` from `0777` to `0700`; the repair was re-preflighted and no silent permission repair is accepted as policy;
- `/proc` evidence: PASS for real Android `system_server` visibility plus executable MATCHING / DEAD / PID_REUSED / STOPPED / ZOMBIE / UNREADABLE classifier fixtures;
- host/chroot clock source: PASS; same-boot evidence and accepted uptime deltas remained below 1 second;
- controlled suspend/wake: PASS; the kernel suspend-success counter increased during a bounded RTC-wake-backed screen-off test;
- P0-G2 representative admission/UFS pressure: PASS under concurrent TikTok cold starts, representative video decode/media reads, fsync-heavy journal writes, and same/different-submission flock contention;
- accepted P0-G2 sample: 48 admission samples, P95 31.490 ms, P99 35.216 ms, 24 same-submission samples, 24 different-submission samples, 3 media-decode passes, >7 MB representative media reads, and 2 TikTok cold starts;
- initial admission timeout candidate: **5000 ms**, satisfying `representative p99 < candidate * 0.5`;
- installed app/UI evidence collector: PASS for Android Settings and TikTok package/version/signing identity evidence;
- ZUI/Android overlay inventory: PASS; only the measured exact Gboard InputMethod identity is proposed as benign allowlist evidence;
- expanded NotificationShade is blocking and not allowlisted; ZUI freeform sidebar APPLICATION_OVERLAY is not statically allowlisted; inactive game/PiP/Accessibility cases are not blanket-allowed;
- suspend/wake-lock policy: current runtime has no dedicated ownership-scoped wake-lock / keep-screen-awake mechanism; accepted policy is suspend may occur, stale tokens fail closed, and resume requires fresh AUTO observe/preflight;
- semantic-v1 fixed vectors and fingerprint-profile reference checks: PASS;
- UI mutation inventory and fault-injection harness self-test: PASS;
- all Sprint-gated checks have executable fixture/inventory/skeleton coverage; production behavior for those checks is intentionally not claimed PASS before the corresponding Sprint.

Local-only empirical evidence remains outside Git under the Y700 runtime evidence area. Device-specific runtime identifiers and raw evidence are intentionally not committed.

Authorization boundary after this gate:

- **Production Runtime Implementation Authorization remains NO.**
- Phase 0 PASS only makes the project eligible for a separate Production Runtime Implementation Authorization review.
- Sprint 1+ production Gateway/Core/Bridge mutation-path implementation must not begin until that separate authorization is explicitly granted.
- Existing Sprint-gated findings remain expected implementation work, including `pressHome` / `pressBack` mutation reclassification, legacy/direct mutation bypass migration, subordinate provenance enforcement, Catalog/runtime overlay enforcement, and recovery semantics.

## Android Automation Core v0.6 Rev3.6 — Production Runtime Authorization Review OPEN (2026-10-07)

- independent review completed against current GitHub `main` = `6201f3d52b7f27d4e4358be2855d8b16324fdcb3`;
- architecture review found no new Critical/High blocker;
- Vision V3 landed after the original Phase 0 validation baseline and changes the mutating click executor path;
- review recommendation is **CONDITIONAL APPROVE**, pending affected-path real-device revalidation on the then-current canonical `main`;
- Production Runtime Implementation Authorization remains **NO** until that revalidation passes and explicit authorization is granted;
- current external blocker: Y700 control plane unavailable (Cloudflare edge HTTP 530 / SSH WebSocket handshake failure; direct CodexPro_Y700 unavailable);
- review record: `docs/AAC-v0.6-REV3.6-PRODUCTION-AUTHORIZATION-REVIEW-2026-10-07.md`.

## Y700 Cloudflare Remote-Control Self-Heal Closure (2026-10-07)

Status: **PASS / CLOSED after final repeated real-device fault injection.**

The earlier `de1302f` closure was **invalidated by a later real test**: Cloudflare again fell to zero active connections and remained unavailable beyond 75 seconds while the existing health loop failed to recover it. That intermediate result is retained in Git history but is not the accepted closure baseline.

Final accepted GitHub `main` baseline:

`7bf800ee536dea9d33d8f23d002b4c6fe31f832b`

The final remediation keeps the previously accepted bounded wake/supervision design and additionally closes the failure modes exposed by repeated testing:

- chroot DNS is now Git-managed by default and no longer silently re-imports the stale Android-host resolver set; an explicit host override path remains available;
- on the tested mobile/hotspot path, `8.8.8.8` and `8.8.4.4` responded reliably while the previous secondary resolver `114.114.114.114` timed out; after the managed resolver fix, `github.com` lookup and Git fetch immediately recovered;
- remote-probe hysteresis applies only while cloudflared is still alive with HA connections, so one transient remote-probe/DNS failure does not churn a healthy tunnel; process-dead or zero-connection failures retain the fast recovery path;
- the restart helper performs bounded TERM -> KILL escalation for a stalled old cloudflared process before spawning a replacement;
- health-loop launch, self-update, and cloudflared restart are mode-independent through explicit `/bin/bash`, while the scripts still retain executable mode in Git;
- health-loop PID cleanup is ownership-safe: an exiting old loop removes the PID file only when the file still contains its own `BASHPID`, preventing an old instance from deleting a newer supervised instance's PID file;
- stale/wedged health-loop replacement is bounded: TERM is attempted first, then escalated to KILL if the live-but-stopped process does not exit, and a replacement is accepted only after publishing a fresh heartbeat;
- the Y700 self-heal contract suite is now part of GitHub Actions, so these recovery semantics are continuously validated.

Final real-Y700 acceptance evidence:

- Y700 self-heal tests: **36/36 PASS**; shell syntax PASS; key helper scripts mode `0755`;
- post-merge GitHub Actions `validate` for `main@7bf800e`: **SUCCESS**;
- final stable runtime points to immutable release `y700-agent-release-7bf800e`;
- health-loop PID, version SHA and heartbeat SHA were aligned to the final script before fault injection;
- final Hard Fault: deliberate cloudflared termination produced external `530 -> 200` recovery in **10.0 seconds**, then remained at 200 on repeated probes;
- internal evidence for that run: `CLOUDFLARED_SELF_HEAL_START` at 04:16:52 UTC, process restart at 04:16:57, and `CLOUDFLARED_SELF_HEAL_OK connections=4 probe_http=200` at 04:17:00;
- an earlier hard-fault run on the same remediation lineage recovered externally in **9.8 seconds**;
- soft-fault evidence showed `CLOUDFLARED_REMOTE_PROBE_GRACE connections=4 cycles=1 required=2` while the external endpoint remained HTTP 200, proving one transient remote-probe failure no longer causes immediate restart;
- PID ownership-safe cleanup semantics: PASS;
- wedged-loop fault injection: `SIGSTOP` left the old health-loop PID alive but stopped; after heartbeat expiry the supervisor recorded `STALE_HEALTH_LOOP_TERM_TIMEOUT ... escalating=KILL`, replaced it with a new PID, and restored heartbeat in approximately **53.3 seconds** while the external endpoint remained HTTP 200 throughout;
- accepted runtime tag: `y700-cloudflare-selfheal-v1.0.1` -> `7bf800e`; the earlier `v1.0.0` tag is retained as historical evidence but is superseded because it did not yet close the wedged-loop replacement gap;
- final runtime state after recovery: remote plane `READY`, remote probe HTTP 200, cloudflared HA connections `4`, restart failures `0`, and no pending retry backoff.

This closure supersedes the earlier Phase 0 observation that the current runtime had no dedicated wake-lock mechanism **only for the Y700 remote-control runtime**. It does not grant or widen Android Automation Core v0.6 Production Runtime Implementation Authorization, and it does not change TikTok publish/COMMIT authorization boundaries.

Detailed public-safe evidence: `docs/Y700-CLOUDFLARE-SELF-HEAL-FINAL-ACCEPTANCE-2026-10-07.md`.

Operational decision: the Y700 Cloudflare remote-control self-heal blocker is now closed on the final accepted baseline. Vision/OCR or other project gates may resume from their own checkpoints, but this connectivity acceptance must not be reused as evidence for unrelated functional gates.

## Android Automation Core v0.6 Rev3.6 — Affected-Path Real-Device Revalidation PASS (2026-10-07)

Status: **PASS / PHASE 1 SPRINT 1 AUTHORIZED.**

After the Cloudflare remote-control blocker was closed, the authorization review's required affected-path checks were rerun on a clean immutable Y700 release at exact canonical baseline `c8bae36daea200c9c427330bfdfc4cdf8766d80b`.

Durable local evidence:

`/opt/y700/runtime/v06-phase0b-evidence/revalidation-c8bae36-20261007/summary.json`

The evidence bundle contains PASS results for preflight baseline, runtime permissions, UI mutation inventory, pressHome/pressBack migration fixture, semantic vectors, fingerprint profiles, proc visibility, same-boot clock evidence, installed app/UI contract, ZUI overlay inventory, suspend/wakelock policy, representative admission/load, and the fault-injection harness.

Notable current-main evidence:

- preflight PASS with `active_bridge_jobs=0`, no current durable `android_ui` claim, root round-trip PASS and clean Git;
- representative admission/load PASS with 48 samples and P99 approximately 22.155 ms;
- the existing Sprint-1 mutation findings remain visible rather than being silently normalized away;
- controlled suspend evidence remains same-boot valid;
- the new `y700-remote-control` kernel wakelock belongs to the remote-control plane only and does not relax Android Automation AUTO/state-token or mutation-ownership rules.

Authorization boundary:

- the empirical blocker identified by the 2026-10-07 authorization review is cleared;
- explicit project-owner authorization was given on 2026-10-07 to continue Rev3.6 implementation/deployment;
- **Production Runtime Implementation Authorization = YES for Phase 1 / Sprint 1 only**;
- authorization baseline: `a428cf3ce1871f2f72ac2ea711c347630af3abc3`; changes since the accepted affected-path revalidation baseline are limited to Cloudflare/DNS self-heal, CI and documentation paths and do not alter the Android mutation executor;
- authorized Sprint 1 scope is shared `android_ui` ownership/claim, protocol-v2 `resource_guard`, legacy TikTok mutator migration/no nested reacquisition, `device-state.json` + token/AUTO state integrity, `pressHome`/`pressBack` mutation reclassification, mutation prepare/commit durability, revision ordering, and stale/manual-drift/direct-bypass rejection;
- Sprint 2+, BUSINESS capability activation, new daemon/MQ/DB, detached execution, weakened Bridge v2 guarantees, approval/effect-boundary work, and Vision external-irreversible policy changes remain unauthorized.

## AAC v0.6 Rev3.7 Freeze + Implementation Authorization (2026-10-08)

Status: **REV3.7 FROZEN / SPRINT 1 + SPRINT 1A AUTHORIZED.**

- Rev3.7 supersedes Rev3.6 as the frozen implementation-input SOT after delta freeze review.
- Rev3.6 accepted empirical evidence remains inherited unless a Rev3.7 delta changes the relevant authority/timing/routing/upgrade/diagnostic assumption.
- User explicitly authorized continuing Rev3.7 implementation on 2026-10-08.
- Authorized production scope: **Phase 1 / Sprint 1 + Phase 1A / Sprint 1A only**.
- Sprint 2+, BUSINESS activation, approval/effect-boundary work, new daemon/MQ/DB, cross-device scheduling/failover remain unauthorized.
- Freeze-gate validation-only artifacts: `schemas/rev37/*`, `scripts/v07/delta_contracts.py`, `scripts/v07/delta-freeze-check.py`, `tests/test_rev37_delta_freeze.py`.
- D-G3 remains a **real-device blocking gate before any visual-assisted mutation is enabled**.
- D-G4 remains blocking before first PATCH_SAFE automatic activation.

## OCR V2 instrumentation host-executor ART integration — PASS (2026-10-08)

Scope: close instrumentation launch/evidence/health-check issues only. Frozen OCR, Vision routing, Android Automation Core, APKs and publication authorization are unchanged.

- Root cause: Bridge-launched `am instrument` / `app_process` from Debian/chroot lacked Android ART environment (`BOOTCLASSPATH` and `DEX2OATBOOTCLASSPATH`) and could return `rc=0` without running tests. Host-executor now loads the necessary environment from Android zygote at startup.
- Instrumentation writes method JSON through target app context/UID to the target private files directory. Executor process count now uses exact argv matching, avoiding substring false positives.
- PR #38: https://github.com/stanleyrprose/AndroidAgent_DouyinOpAuto/pull/38 ; code merged into `main` at `0c2a1d60fc59fe0752c72f7e45258b62b83b4e0b`. The two Python runners no longer call the temporary `android-runtime-env.sh`; per-class evidence is invalidated without deleting unrelated artifacts.
- Clean immutable Y700 release `y700-agent-release-0c2a1d6`: focused OCR tests 4/4 PASS, host singleton tests 4/4 PASS, Python compilation PASS, complete **wrapperless Gate V2 20/20 method evidence PASS** across seven classes.
- Canonical runtime evidence (not committed): `/opt/y700/runtime/ocr-v2/ocr-v2-component-gate-20261008-093430.json`, `GATE_PASS`; warm 200-run P50/P95 **42.63/50.28 ms**, load/unload **1/0**, in-flight **0**, thermal delta approximately **+0.2 C**. Cold 20-run P50/P95 **64.39/116.93 ms**.
- Production stable symlink switched from `y700-agent-release-3835b77` to `y700-agent-release-0c2a1d6`, old release retained as rollback. Post-deployment SOT HEALTHY, one bridge executor, Cloudflare 4 connections, CodexPro/Bridge HEALTHY, and unwrapped `am help` PASS.
- Cloudflare long-duration fault-injection acceptance and v0.6 Phase-1 authorization remain independent gates. This OCR runner fix does not expand their scope.

## Douyin → TikTok Burmese Dynamic Subtitles v0.4 — CODE VALIDATED / BUSINESS GATES PENDING (2026-10-10)

- Scope: Mac production-pipeline opt-in implementation only, PR #42. No Y700/TikTok/publisher code, CI workflow trigger, or production runtime deployment changed.
- Git feature branch `feat/burmese-dynamic-subtitles-v04`, commits `7fbc12e` and `8ebfe88` (before final review fixes); branch pushes did not trigger GitHub CI; PR creation is the first CI trigger.
- Implementation: Apple Vision Chinese OCR, bounded frame sampling and explicit coverage diagnostics, deterministic ASR/OCR event ledger, immutable timed source IDs, constrained Myanmar translation IDs, timeline SOT plus legacy localization projection, Swift batch Myanmar shaping and FFmpeg cue overlays, pre-export fail-closed quality checks, Telegram quality outbox and offline inspection.
- Local acceptance: 44 Mac Python tests PASS, including 19 new tests without third-party packages; Swift OCR and batch renderer compile/typecheck PASS; 6-second synthetic visual-only source gives three independent OCR events and timed Myanmar overlay cues; final MP4 duration 6.000 seconds, local Q3 PASS; contact image manually inspected.
- **NOT accepted**: real 24+2 Douyin sample GT recall/precision KPI, field OCR benchmarking, Myanmar native-speaking semantic/shaping review, R0/R2 human release gates, zero-touch production activation, and any real TikTok COMMIT. These gates MUST remain independent; Git merge does not authorize production dynamic mode.
- Activation guard: dynamic mode disabled by default; legacy subtitle workflow and DIRECT_DOWNLOAD unchanged. Without later accepted R0/R2 evidence and separate production authorization, do not set `Y700_SUBTITLE_MODE=dynamic_v04` or issue `--dynamic-subtitles` for real publishing.
