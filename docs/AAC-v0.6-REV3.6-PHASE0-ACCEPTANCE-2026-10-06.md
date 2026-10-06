# Android Automation Core v0.6 Rev3.6 — Phase 0 Acceptance

Date: 2026-10-06

Status: **PHASE 0 AUTHORIZATION GATE PASS**

This document records only the Rev3.6 Phase 0A/0B validation result. It does not grant Production Runtime Implementation Authorization.

## Accepted baseline

- Git SOT: GitHub `main`
- Validation tooling baseline: `abc5333864a9b928ce16bfcecf157a7081e623e0`
- GitHub Actions validate: PASS
- Real device: Lenovo TB323FU / Android 16 / Debian 13 chroot
- Validation source: clean immutable Y700 worktree at the exact accepted Git baseline

## P0-G1 — process and clock evidence

PASS.

- Real Android `system_server` process evidence is readable from the Debian chroot.
- Executable fixtures cover MATCHING, DEAD, PID_REUSED, STOPPED, ZOMBIE and UNREADABLE classification.
- Android-host and chroot boot identity matched.
- Accepted host/chroot uptime deltas were below 1 second.
- A bounded RTC-wake-backed screen-off test produced a real kernel suspend/resume increment on the same boot.
- CLOCK_BOOTTIME-includes-suspend semantics remain fail-closed.

## P0-G2 — admission/UFS pressure

PASS.

Representative concurrent workload included 2 TikTok cold starts, 3 representative video-decode passes, >7 MB media reads, fsync-heavy journal/atomic writes, 24 same-submission contention samples and 24 different-submission contention samples.

Accepted result: P95 31.490 ms, P99 35.216 ms, initial deployment timeout candidate 5000 ms. The Phase 0 threshold passes because representative P99 is far below 50% of the candidate.

This is the Phase 0 synthetic representative baseline only. Sprint 2 must still run A69 against the actual production admission critical section.

## P0-G3 — Android/ZUI overlay inventory

PASS.

- Gboard InputMethod: measured benign class for presence-only handling; exact package/version/window identity proposed for the versioned allowlist.
- NotificationShade: explicitly expanded and captured as blocking when visible; not allowlisted.
- ZUI freeform sidebar: observed APPLICATION_OVERLAY; not statically allowlisted.
- ZUI game/performance package and overlay-capable components: installed, no active game overlay observed; not allowlisted.
- PiP: capability present, no active PiP window observed.
- Accessibility: services installed, no enabled/bound service and no active Accessibility overlay observed.

No package wildcard, class wildcard or unknown-system-window blanket allow is accepted.

## P0-G4 — suspend/wake-lock policy

PASS for characterization and frozen fail-closed policy.

The current runtime has no dedicated ownership-scoped WakeLock or keep-screen-awake implementation. Real suspend was demonstrated. Therefore suspend may occur; CLOCK_BOOTTIME token age continues advancing; stale tokens require fresh AUTO observe/preflight after resume; token validity is never extended to hide suspend.

## Other Phase 0B gates

PASS: machine-readable preflight, runtime permission baseline, installed Settings/TikTok identity evidence, semantic-v1 fixed vectors, fingerprint profile reference tests, UI mutation inventory and fault-injection harness self-test.

One permission defect was found and repaired as an explicit audited ADMIN maintenance action: `/opt/y700/runtime/state` was changed from mode `0777` to `0700`, then re-preflighted PASS.

Sprint-gated fixtures/inventories are present but do not claim production PASS before their owning Sprint.

## Decision boundary

Phase 0 passes the prerequisite gate for a **separate** Production Runtime Implementation Authorization review.

It does **not** authorize Sprint 1+ production implementation by itself.
