# Android Automation Core v0.6 Rev3.6 — Production Runtime Implementation Authorization Review

Date: 2026-10-07

Review status: **AFFECTED-PATH REAL-DEVICE REVALIDATION PASS / AWAITING EXPLICIT AUTHORIZATION**

Current production authorization: **NO**

## Basis

- Rev3.6 Frozen remains the canonical implementation-input SOT.
- Rev3.6 Phase 0A/0B prerequisite gate passed on real Y700 evidence and was accepted in Git SOT.
- Phase 0 acceptance validation baseline was `abc5333864a9b928ce16bfcecf157a7081e623e0`.
- Accepted affected-path revalidation baseline is `c8bae36daea200c9c427330bfdfc4cdf8766d80b`; the exact immutable Y700 release was clean and GitHub CI was green.
- Between the Phase 0 validation baseline and current `main`, Vision Locator V3 landed and changed `automation/ui_job.py`, `automation/vision_policy.py`, Android instrumentation click/vision routing, Vision benchmark support and related tests/docs.

## Independent authorization review

Architecture review result: **no new Critical/High architecture inconsistency identified**.

The post-Phase-0 Vision V3 delta does not introduce a second ownership/state authority, a new daemon, MQ/DB, detached execution model or alternate mutation executor. It remains inside the existing shared Action Executor / Bridge v2 workflow model.

However, the delta **does change the mutating click execution path** by adding deterministic semantic -> template -> OCR fallback, stale-target bounded re-resolution, and package/context-bound known-popup recovery. Therefore the Phase 0 empirical evidence collected on the earlier baseline cannot be treated as fully fresh for Production Runtime Implementation Authorization without affected-path real-device revalidation on current `main`.

Vision V3's own real-device acceptance is relevant supporting evidence: the frozen gate reports 20/20 cold-start mixed workflows PASS, zero duplicate target actions, zero duplicate commit actions, stale-target pre-action re-resolution PASS, package/context-bound popup recovery PASS and external irreversible Vision denial PASS. This reduces risk but does not replace the Rev3.6 authorization-specific revalidation.

## Completed final revalidation on current-main baseline

Executed from clean immutable Y700 release `/opt/y700/workspaces/y700-agent-release-c8bae36` at exact `c8bae36daea200c9c427330bfdfc4cdf8766d80b`. Durable evidence summary: `/opt/y700/runtime/v06-phase0b-evidence/revalidation-c8bae36-20261007/summary.json`.

1. `preflight-baseline` — clean Git, device health/root, APK SHA evidence, no current durable android_ui claim, quiescent Bridge active set.
2. `runtime-permissions` — owner/mode/symlink integrity still PASS.
3. `ui-mutation-inventory` — inventory remains complete and any newly introduced direct mutation is visible.
4. `presshome-back-migration` fixture remains executable and still identifies pressHome/pressBack as Sprint-1 mutation work.
5. `semantic-vectors` and `fingerprint-profiles` remain exact PASS.
6. `proc-visibility` and same-boot clock/suspend evidence remain valid on the current device boot/runtime.
7. `app-ui-contract` and ZUI/Android overlay evidence remain PASS for the current installed app/firmware state.
8. `suspend-wakelock-policy` remains characterized fail-closed.
9. representative `admission-lock-load` remains PASS with the frozen candidate set and no material regression.
10. `fault-injection-harness` remains PASS.

## Authorization recommendation

**REVALIDATION PASS. RECOMMEND EXPLICIT AUTHORIZATION FOR PHASE 1 / SPRINT 1 ONLY; CURRENT AUTHORIZATION REMAINS NO UNTIL THAT EXPLICIT AUTHORIZATION IS GIVEN.**

If all listed checks PASS on the then-current canonical `main`, this review recommends setting:

`Production Runtime Implementation Authorization = YES for Phase 1 / Sprint 1 only`

with the following scope lock:

- shared `android_ui` arbiter and canonical lock/claim;
- protocol-v2 `resource_guard` enforcement;
- legacy TikTok mutator migration to the shared arbiter;
- no nested ownership reacquisition;
- `device-state.json`, state token and AUTO guard;
- pressHome/pressBack reclassification as LOCAL_UI_MUTATION;
- MUTATION_PREPARED / COMMITTED durability and revision ordering;
- stale/manual-drift/direct-bypass rejection.

Still not authorized by this review:

- BUSINESS capability activation;
- Sprint 2 admission production implementation;
- Sprint 3 coordinator/backend binding;
- Sprint 4 approval/effect-boundary implementation;
- new daemon/service, MQ/DB or detached execution;
- weakening Bridge v2 frozen guarantees or Vision external-irreversible deny policy.

## Revalidation result and remaining authorization boundary

The Cloudflare control-plane blocker is resolved and separately closed in `CHECKPOINT.md`. All required affected-path real-device revalidation checks passed on the accepted current-main baseline:

- preflight baseline: PASS after confirming the Bridge active set was quiescent (`active_bridge_jobs=0`) and no current durable `android_ui` claim existed;
- runtime permissions: PASS;
- UI mutation inventory: PASS and remains complete, including the expected Sprint-1 legacy/direct mutation findings;
- pressHome/pressBack migration fixture: PASS and still classifies both as Sprint-1 `LOCAL_UI_MUTATION` work;
- semantic vectors and fingerprint profiles: PASS;
- `/proc` visibility, same-boot clock and controlled-suspend evidence: PASS;
- installed app/UI contract and ZUI/Android overlay evidence: PASS;
- suspend/wakelock policy: PASS for the Android Automation workflow contract; the separate control-plane wakelock does not relax AUTO/state-token semantics;
- representative admission/load: PASS, 48 samples, P99 approximately 22.155 ms against the frozen 5000 ms candidate rule;
- fault-injection harness: PASS, 3/3 tests.

Production Runtime Implementation Authorization is still **NO** because the review requires a separate explicit authorization decision after revalidation. No Sprint 1 production implementation may begin merely from this PASS result.
