# Rev3.7 Sprint 1 / 1A source coverage — 2026-10-12

**Basis:** Frozen PRD §40.2 and §40.2A; source inventory on `feat/aac-rev37-sprint1a`.
**Evidence type:** source inspection only. No tests/build/device verification in this batch.
**Authority:** Frozen PRD currently authorizes Sprint 1 and Sprint 1A only.

| PRD deliverable | Candidate source | Current assessment / acceptance gap |
|---|---|---|
| Shared Android UI arbiter, durable Claim and owner guard | `automation/resource_arbiter.py`, `automation/canonical_ui_resource.py` | Source present; concurrent/rotation/crash hardware gate unverified |
| Boot-aware State Integrity epoch/revision/hash | `automation/state_integrity.py`, `automation/authoritative_state_reader.py` | Source present; device provenance and external UI drift gate unverified |
| semantic-v1 exact fingerprint and vectors | `automation/state_integrity.py`, `scripts/v07/delta_contracts.py` | Source present; consolidated vectors deferred |
| mutation journal prepare/commit and revision order | `automation/state_integrity.py`, `automation/ui_core_v2.py`, `automation/ui_job.py` | Source present; fault-injection and crash replay gates deferred |
| Legacy home/back reclassification | Android `AutomationInstrumentedTest.java`, `automation/ui_core_v2.py` | Requires consolidated bypass inventory and regression verification |
| Deterministic versioned route / no unsafe fallback | `automation/route_selection.py`, `automation/frozen_route_contracts.py` | Read-only candidate; no production visual route accepted |
| Verified target no-op | `automation/route_selection.py`, `automation/frozen_route_contracts.py` | Selection contract exists; positive device target-state proof unverified |
| FrameToken, exact locator identity and one-shot consumption | `Rev37NativeFrameRegistry.java`, `Rev37NativeTemplateRoute.java` | In-process source present; TikTok template/hash NOT accepted |
| JIT state, foreground, rotation, window and frame age | `Rev37NativeStateObserver.java`, `Rev37NativeMutationBoundary.java`, `automation/frame_guard.py` | Candidate present; native route max age uncalibrated, modal selectors unaccepted |
| Stale frame, boot/revision drift zero-attempt denial | `Rev37NativeFrameRegistry.java`, `Rev37NativeMutationBoundary.java` | Source gate present; native integration/latency/device fault-injection deferred |
| Native single input boundary | `AutomationInstrumentedTest.java`, `Rev37NativeMutationBoundary.java` | Hard-closed; D-G3 OPEN, no mutation acceptance |

## Blocking gates before Sprint 1 / 1A acceptance

1. Compile Android instrumentation source and run affected-path tests **only after user authorizes consolidated testing**.
2. Verify real Y700 boot/epoch/revision/Claim concurrency, process death, PREPARE-without-COMMIT and resource reclamation without fabricated positive receipts.
3. Calibrate frame capture-to-dispatch age on the real device; accept a versioned TikTok package/signature/modal contract and immutable template digest. Until then native visual click is unavailable.
4. Prove all legacy mutating entrypoints are routed through the same resource/state journal; demonstrate stale-frame and ownership zero-attempt rejection.
5. Reconcile PRD authorization for any later Sprint 2–6 production work separately; no source presence implies activation approval.

**Status: SOURCE CANDIDATE ONLY. Sprint 1 / 1A NOT ACCEPTED. Code Complete = NO. D-G3 = OPEN; BUSINESS COMMIT = CLOSED; release switch = CLOSED.**
