# AAC Rev3.7 Sprint 1A — Execution Boundary Implementation Evidence

Date: 2026-10-08
Branch: `feat/aac-rev37-sprint1a`
Authority: `docs/PRD-Y700-AAC-v0.6-Rev3.7-Frozen.md` §§18.8, 39.2A, 40.2A

## Status: IMPLEMENTATION IN PROGRESS (not accepted, not enabled)

Implemented within authorized Sprint 1/1A:
- `automation/resource_arbiter.py`, `state_integrity.py`, `ui_core_v2.py`: Sprint 1 ownership, semantic state guard, prepared/commit ordering and revision safety.
- `automation/route_selection.py`: deterministic local route decisions; not an alternate scheduler or business runtime.
- `automation/frame_guard.py`: independently checks exact frame and locator binding, boot, epoch, revision, display, rotation, geometry, foreground, keyguard/overlay and route age.
- `ui_core_v2._run_mutation`: vision-capable mutators cannot reach `MUTATION_PREPARED` unless trusted `visual_evidence_provider` passes JIT guard. Any selector containing an implicit vision fallback is also protected. No provider is supplied by production `automation/ui_job.py`; visual mutation therefore fails closed by default.
- `VISUAL_DISPATCH_BLOCKED` and `FRAME_FRESHNESS_VERIFIED` phases in existing job journal; no new daemon, queue, database or scheduler.
- `scripts/v07/check-frame-freshness.py` and `check-conditional-dispatch.py`: deterministic, machine-readable fixture checks. Output explicitly says `production_gate_passed: false`.
- No `EXTERNAL_IRREVERSIBLE` mutation may be dispatched through the visual route.
- `AutomationInstrumentedTest.runInteractiveCoreV2`: Android Java driver adds an independent `VISION_DRIVER_GATE_CLOSED` hard-stop with `attempts=0` for visual mutation, visual fallback, and popup-recovery mutation. It rejects *before* `executeWithRetry`, even if the host callback later becomes permissive. A future on-device D-G3 verifier is required to replace this hard-stop; Java debugAndroidTest compilation PASS locally using JDK 17 + Android SDK (no APK deployment).
- `scripts/v07/probe-android-frame-latency.py`: read-only bounded 3–30 sample Android screencap timing over existing Host Bridge. Screenshot bytes go to `/dev/null` on Android; output contains numeric performance only, `production_gate_passed=false`. Device `/proc/uptime` is only a boot-elapsed timing proxy, NOT the final instrumentation `CLOCK_BOOTTIME`/JIT frame receipt.
- `tests/test_rev37_driver_visual_gate.py` + `tests/test_rev37_frame_latency_probe.py` are CI regression checks; the former is a source-contract test, not a replacement for Android instrumentation runtime acceptance.

## What still blocks enablement / merge

1. **D-G3 real Y700 acceptance**: integrate trusted device capture + locator result with JIT live Android state reader and real route-versioned, measured `max_frame_age_ms`. There is no production provider today, and the Android driver refuses visual mutation unconditionally in interactive v2 until its own trusted verifier exists. Capture and locator latency, age at locator and dispatch, recapture metrics must come from real device; no hardcoded acceptance from fixture timings.
2. **Visual route cutover**: independently verify that the Android driver cannot execute a vision fallback outside the guarded path, including legacy internal backend boundaries; evaluate app/UI contract drift and simultaneous semantic guard.
3. **PR CI and affected-path regression**: full GitHub Actions validation and target Linux/Y700 tests, including concurrent ownership, crash, token stale, Settings controls and TikTok DRY_RUN.
4. **No production deployment until acceptance**. Existing immutable Y700 runtime release and dirty legacy workspace must remain untouched.
5. D-G1/D-G2/D-G5 production obligations are not satisfied by freeze-contract fixture checks. D-G4 is reserved for later PATCH_SAFE auto-activation.

## Y700 read-only capture latency baseline (2026-10-08)

A 3-sample Android host `screencap -p` benchmark discarded all screenshot bytes to `/dev/null`. Measured capture durations: **328 ms, 364 ms, 320 ms** (all exit code 0). This samples only screenshot capture, not OCR/locator or action-dispatch latency, and does **not** calibrate or approve a route `max_frame_age_ms`. Real latency p95/p99 and end-to-end D-G3 remain OPEN.

## Reproduction

```sh
python3 -m unittest tests.test_rev37_runtime_foundation tests.test_rev37_visual_dispatch_boundary -v
python3 scripts/v07/check-frame-freshness.py
python3 scripts/v07/check-conditional-dispatch.py
python3 scripts/v07/delta-freeze-check.py
python3 -m unittest tests.test_rev37_driver_visual_gate tests.test_rev37_frame_latency_probe -v
# Only on Y700, read-only; do not run in CI or interpret as D-G3 PASS:
python3 scripts/v07/probe-android-frame-latency.py --samples 20
```

The machine-checkers are **fixture-only** evidence, not an attestation of production D-G3.
