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
- `scripts/v07/probe-android-frame-context.py` adds a zero-click, zero-pixel-retention read-only capture with before/after boot, foreground, display rotation, geometry, screen state and input-restriction comparison. Raw foreground identifiers are not included in JSON reports. This is deliberately **not** a frame-token issuer, locator, or D-G3 acceptance; the keyguard observation is incomplete, and state epoch/revision is unavailable from this independent Android probe. `tests/test_rev37_frame_context_probe.py` checks drift, invalid/duplicate fields, boot and timestamp failures.
- Core v2 now also treats `vision_recovery` on a mutating action as a visual execution path even if its primary selector is semantic, aligning with the Java Driver hard-stop. The route remains blocked.

## Offline Frame Token / Locator receipt and independent release authority

- `automation/visual_route_gate.py` keeps `DG3_PRODUCTION_ENABLED=False` as the code-owned deployment baseline. A caller, environment variable or `visual_evidence_provider` response with `dg3_accepted=true` cannot authorize production visual mutation: the Core v2 JIT boundary rejects the request before calling the provider, before MUTATION_PREPARED, and before Android Driver dispatch. Synthetic unit tests explicitly mock the release gate only for verifying downstream guard ordering.
- `automation/visual_receipt.py` implements a **read-only, in-memory candidate receipt** for `capture -> frame token -> locate(frame_id) -> independent current state read -> CLOCK_BOOTTIME JIT verification`. It does not click or persist pixels. Frame age starts at the **beginning** of capture, never the end (conservative). Epoch/revision are derived from the semantic proof rather than untrusted capture metadata. Locator must return an exact matching frame_id. Fixture-only versioned route calibration is required even to run the read-only harness.
- The fixture verdict `VERIFIED_READ_ONLY` **never** means D-G3 acceptance: it retains `production_gate_passed=false`, `visual_dispatch_allowed=false`, `dg3_status=OPEN`, and zero UI mutation attempts. The positive locator tests use a **synthetic fixture adapter**, not live OCR/Template Locator. No production provider is registered, and the Java interactive Android Driver independently refuses visual mutation.
- Full real-device D-G3 still requires a pixel-backed capture receipt from the Android instrumentation clock, a locator result from exactly those pixels, independent post-locator device state/overlay observation at the dispatch boundary, measured end-to-end age, a reviewed route calibration/acceptance artifact, and its own Android Driver JIT verifier. Neither provider self-attestation nor these offline tests close that gate.

## Read-only real-pixel Android instrumentation candidate (2026-10-09)

- Added `mac/android-automation/app/src/androidTest/java/com/stanley/y700automation/vision/Rev37ReadOnlyFrameReceiptInstrumentedTest.java`, a **separate** test entrypoint; it does not invoke the old `VisionV0BenchmarkInstrumentedTest`, which contains `device.click` and launches a benchmark activity.
- Reads the **currently visible** Android screenshot via existing `VisionV0Harness.capture`; stamps the frame at `SystemClock.elapsedRealtimeNanos()` **before** capture; selects a bounded high-variance patch from that exact screenshot, then performs an in-memory OpenCV match against the **same** screenshot/ROI. All candidate templates and screenshot Bitmaps are recycled; no screen pixels or fingerprint are written to disk, result bundles or logs.
- The in-memory ephemeral `frame-UUID` and `VisionTarget.frameGeneration` must match in the same invocation. Reobserves screen wakefulness, keyguard state, current package, rotation and display geometry after locator completion. Outputs capture/locator/observation age metrics and no raw package, screenshot or target bounds. Test contains no input, press, activity launch, wake or unlock API.
- **Limited scope**: the matched patch is derived from the same screenshot, so it tests real-pixel provenance and exact binding rather than production target recognition. Android boot ID, authoritative semantic state epoch/revision, activity, overlay and contract-calibrated max-age/JIT action boundary remain unverified; all emitted evidence says `production_dg3_passed=false` and `visual_dispatch_allowed=false`.
- Mac Android SDK/JDK17 `compileDebugAndroidTestJavaWithJavac --offline` succeeds. `tests/test_rev37_real_pixel_readonly_source.py` adds five CI-level source safety checks. **This test has not been executed on Y700**: executing it requires installation of a new Android instrumentation APK, which is not authorized against the existing production tablet release. It is staged in the isolated Git branch, not deployed.
- Proposed subsequent acceptance uses an isolated instrumentation/staging package and only the named read-only test method, and requires separate verification of app/install namespace isolation and the no-input instrumentation runner. Do not run the older mutating benchmark as a shortcut.

## What still blocks enablement / merge

1. **D-G3 real Y700 acceptance**: integrate trusted device capture + locator result with JIT live Android state reader and real route-versioned, measured `max_frame_age_ms`. There is no production provider today, and the Android driver refuses visual mutation unconditionally in interactive v2 until its own trusted verifier exists. Capture and locator latency, age at locator and dispatch, recapture metrics must come from real device; no hardcoded acceptance from fixture timings.
2. **Visual route cutover**: independently verify that the Android driver cannot execute a vision fallback outside the guarded path, including legacy internal backend boundaries; evaluate app/UI contract drift and simultaneous semantic guard.
3. **PR CI and affected-path regression**: full GitHub Actions validation and target Linux/Y700 tests, including concurrent ownership, crash, token stale, Settings controls and TikTok DRY_RUN.
4. **No production deployment until acceptance**. Existing immutable Y700 runtime release and dirty legacy workspace must remain untouched.
5. D-G1/D-G2/D-G5 production obligations are not satisfied by freeze-contract fixture checks. D-G4 is reserved for later PATCH_SAFE auto-activation.

## Y700 read-only capture latency baseline (2026-10-08)

### Initial exploratory run (3 samples)
Android host `screencap -p` with screenshot bytes discarded to `/dev/null`: **328, 364, 320 ms**; exit codes all 0. This was not a statistically defensible calibration.

### Repeatable Y700 read-only probe (current branch, 2026-10-08)

`python3 scripts/v07/probe-android-frame-latency.py --samples 20` captured 20 frames without saving pixels or sending click commands. Android `/proc/uptime` (centisecond-resolution boot-elapsed proxy) was sampled immediately around each `screencap` call. Results: **min 880 ms, median 970 ms, P95 1,070 ms, P99 1,080 ms, max 1,080 ms**. Independent 5-sample repeat: **min 720 ms, median 930 ms, P95/max 1,080 ms**. Both executions returned `MEASURED_READ_ONLY` and explicitly `production_gate_passed=false`.

The observed much slower repeated captures versus the exploratory run are **unexplained**; possible load/screen/compression/thermal impacts have not been isolated. Neither run measures template/OCR latency, frame-age-at-locator/dispatch, Android instrumentation `CLOCK_BOOTTIME` timing, post-capture activity drift, or an actual frame-id-bound locator. Therefore **do not derive or enable a production 1,200 ms freshness threshold from these captures**. D-G3 remains **OPEN**, and the Java Driver maintains a hard-stop until a verified on-device D-G3 guard is developed and accepted.

## Y700 pre/post read-only context probe (2026-10-08)

Isolated Y700 checkout `f46decd` ran `python3 scripts/v07/probe-android-frame-context.py` over existing Host Bridge. Result: **OBSERVED_READ_ONLY**; screencap **980 ms**; pre-capture context read **60 ms**, post-capture context read **30 ms**; no detected change in foreground identity, rotation, display geometry, screen wakefulness or `mInputRestricted`; **zero UI actions and no screenshot retained**. Both screen observations indicated interactive. The device probe does not prove keyguard fully unlocked (only the limited `mInputRestricted` reading), nor observe authoritative state epoch/revision, emit frame tokens, localize a target or measure JIT dispatch age. Accordingly `production_gate_passed=false`, `dg3_status=OPEN` and visual route remains hard-disabled. Y700 focused regression 52/52 PASS, PR CI PASS at this commit.

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
