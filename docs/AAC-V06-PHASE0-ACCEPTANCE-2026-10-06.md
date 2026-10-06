# AAC v0.6 Rev3.6 — Phase 0 Validation Acceptance

Date: 2026-10-06  
Target: Lenovo Y700 / TB323FU / Android 16 / Debian 13 chroot  
Feature branch: `feat/aac-v06-rev36`  
Validation baseline commits: `be6099c`, `229d896`

## Decision

**PASS — Phase 0A/0B empirical gate is sufficient to enter Sprint 1 production-runtime implementation under the user's explicit /goal authorization.**

This acceptance does not claim any Rev3.6 runtime behavior exists yet. Sprint-gated checks intentionally report `SPRINT_GATED` until their owning sprint implements the contract.

## Isolation / rollback safety

- Production checkout remains `/opt/y700/workspaces/y700-agent-release-0160b5f`.
- Production symlink `/opt/y700/workspaces/y700-agent` was not switched.
- Rev3.6 validation ran from isolated Y700 worktree `/opt/y700/workspaces/y700-agent-v06-rev36`.
- No active Bridge jobs were present at baseline.
- No durable `android-ui.claim.json` existed.
- Publisher durable state was `PUBLISHED`, not `COMMITTING` or ambiguous.

## P0-G1 — Process identity and cross-environment clock source

PASS.

- Debian chroot and Android host expose the same kernel PID-1 process identity:
  - state `S`
  - start ticks `0`
- Android host `system_server` was independently observed as PID 3138 with state `S` and a readable non-zero start-tick field.
- `CLOCK_BOOTTIME` is supported in the chroot.
- First measured chroot/host uptime delta: `0.0 ms`.
- Later measurement while the tablet was naturally `mWakefulness=Asleep`: chroot/host uptime delta remained `0.0 ms`.
- Current asleep-period sample:
  - chroot uptime: `117643860 ms`
  - Android-host root uptime: `117643860 ms`
  - Python CLOCK_BOOTTIME: `117643867 ms`

Conclusion: Android host and Debian chroot share the same BOOTTIME/boot epoch semantics required by Rev3.6. Suspend time is intentionally included; stale state tokens are not extended across sleep.

## P0-G2 — Admission lock / durability load

PASS.

Y700 synthetic benchmark parameters:

- serial iterations: 60
- concurrent workers: 4
- payload per binding: 64 KiB
- total samples: 120
- temp write + file fsync + rename + parent-dir fsync inside the admission critical section

Y700 results at `229d896`:

- hold p50: `1.975 ms`
- hold p95: `3.780 ms`
- hold p99: `4.190 ms`
- hold max: `5.853 ms`
- wait p95: `11.446 ms`
- wait p99: `12.986 ms`
- total p99: `15.454 ms`

The Rev3.6 initial `admission_lock_timeout_ms=5000` remains the deployment candidate because `p99_hold << 0.5 * timeout`. The value is deployment configuration, not a wire constant.

## P0-G3 — ZUI / Android 16 window inventory

PASS for observed scenarios; unobserved classes remain fail-closed.

Observed concurrently on the real device:

- ScreenDecorOverlayBottom / ScreenDecorOverlay / ScreenDecorHwcOverlay
- Taskbar
- NotificationShade
- StatusBar
- InputMethod
- `com.zui.freeform.sidebar`
- multiple application windows including Settings and TikTok splash

Scenario matrix:

- IME: observed
- floating sidebar: observed
- notification shade: observed
- system decor: observed
- Toast: not observed in this sample
- Accessibility overlay: not observed in this sample
- PiP/pinned window: not observed in this sample

No exact benign allowlist is accepted by Phase 0 and wildcard allowlisting is forbidden. Presence alone never makes a window benign. Unobserved classes remain fail-closed until explicitly exercised and versioned.

## P0-G4 — Suspend / wake-lock policy

PASS.

- Correctness does not depend on a wake lock.
- State-token age uses `CLOCK_BOOTTIME`, so sleep/suspend consumes token lifetime by design.
- Resume after token expiry requires a fresh observation and full preflight.
- A bounded keep-awake optimization remains measurement-gated availability work, not a correctness dependency.
- A naturally sleeping device still produced identical host/chroot BOOTTIME-derived uptime evidence.

## Static/runtime integrity baseline

PASS.

- `/opt/y700/runtime`: root-owned 0700
- `/opt/y700/jobs`: root-owned 0700
- `/opt/y700/ui-jobs`: root-owned 0700
- `/opt/y700/runtime/android-ui.lock`: root-owned 0600
- no durable claim present
- approximately 180 GB free at validation time

## semantic-v1 reference gates

PASS on both Mac and Y700.

Fixed vectors:

- foreground-base-v1: `074e74b0f725954b789fea7d905715c7e096c4ab159029a1c6c8ef8a6b610b66`
- settings-switch-element-base-v1: `6bab7e2cd22bb7e2804f75638edfda2546f73802003c57fde3ecbdd322f32fd4`

Profile reference behavior also PASS:

- unwatched text/content-desc noise is omitted
- watched-field changes alter semantic identity
- watched null is explicit
- empty string differs from null
- unavailable watched field fails closed

## App / UI contract evidence

PASS for Phase 0 inventory.

Installed TikTok:

- package: `com.zhiliaoapp.musically`
- versionCode: `2024700030`
- versionName: `47.0.3`
- signing identity metadata is available from package diagnostics, but Phase 0 did not derive a stable certificate digest

Sprint 2/6 Catalog must pin the exact accepted version contract; no wildcard version acceptance is permitted.

## Current migration inventory

Baseline intentionally still shows legacy behavior that Sprint 1 must remove:

- `automation/ui_job.py` classifies `pressHome` / `pressBack` inside legacy `SAFE_ACTIONS`
- TikTok controller contains one `ui_lease()` definition and multiple call sites
- root-level coordinate taps remain in current TikTok/publisher paths
- current lock is only live flock ownership; durable Rev3.6 claim semantics do not yet exist

These are not Phase 0 failures; they are the measured Sprint 1 migration surface.

## Fault-injection harness

PASS self-test on Mac and Y700.

Named seams cover:

- temp write before file fsync
- file fsync before rename
- rename before parent-dir fsync
- parent-dir fsync before next causal step
- before/after revision durable write
- before/after MUTATION_COMMITTED append
- before/after effect-boundary durable publish
- after external-effect dispatch before terminal-result publish

Production named-boundary recovery PASS is deferred to the sprint that owns the behavior.

## Existing baseline regression

Mac baseline before runtime implementation:

- Bridge v2 unit tests: 15/15 PASS
- TikTok / publish routing / UI evidence safety tests: 30/30 PASS
- Python compile checks: PASS

## Authorization transition

Rev3.6 itself froze production runtime implementation behind a separate authorization review. The user's current `/goal落地执行该PRD` instruction explicitly authorizes implementation. With the Phase 0 empirical gates above closed, implementation may now proceed to Sprint 1 without changing any other frozen architectural constraint.
