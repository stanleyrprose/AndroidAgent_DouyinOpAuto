# Android Automation Core v0.5 — Final Acceptance

Date: 2026-10-04  
Target: Lenovo Y700 / Android 16 / Debian 13 chroot  
Runtime/code acceptance baseline: `6285a6d23b4d33118e0db2cc25f5838d54551644`  
Bridge v2 accepted baseline: Sprint 6A frozen filesystem SOT  
TikTok DRY_RUN frozen baseline: `4c19067bc63d43df1472668ec0abeff98bc82283`

## Decision

**PASS WITH PHYSICAL MAC-OFF / EXTERNAL-NETWORK GATE DEFERRED**

The Android Automation Core, Bridge v2 integration, generic Settings workflow,
failure evidence/recovery, semantic action surface, cooperative cancellation,
and TikTok DRY_RUN migration satisfy the v0.5 functional acceptance criteria
covered by this run.

Per explicit project decision, the physical Mac-Off acceptance and its paired
external Wi-Fi / hotspot scenario are deferred. They are not marked PASS and
do not invalidate the technical acceptance completed here.

## Final real-Y700 acceptance results

### Generic semantic action surface

PASS on the real Y700:

- semantic selector/cardinality;
- click;
- longClick;
- inputText with Unicode `深色模式`;
- IME dismiss path;
- semantic scroll with visible-tree change;
- normalized swipe with visible-tree change and no absolute pixel coordinates;
- waitFor;
- waitStable;
- assertion;
- screenshot;
- unknown selector key fails closed with `JOB_PAYLOAD_INVALID`;
- failure evidence is emitted for selector-contract failures.

### Failure Evidence Contract

PASS.

For an injected terminal UI-observation failure, durable evidence contained:

- screenshot;
- compact UI tree;
- activity;
- package;
- timestamp;
- action;
- selector;
- postcondition;
- error.

Evidence is stored under the UI job's `evidence/` directory and referenced from
the durable workflow result.

### UI observation recovery

PASS.

Injected two transient failures:

```text
attempt 1 -> LEVEL_0_REOBSERVE
attempt 2 -> LEVEL_1_WAIT_STABLE
attempt 3 -> observe PASS
```

Injected three failures:

```text
LEVEL_0_REOBSERVE
-> LEVEL_1_WAIT_STABLE
-> LEVEL_7_BLOCKED_EVIDENCE
-> BLOCKED / UI_OBSERVATION_FAILED
```

No destructive action replay is authorized by observation failure.

### Settings generic-app acceptance

PASS.

Final flow is session-independent:

```text
launch Settings
-> wait package=com.android.settings
-> semantic search
-> Unicode input 深色模式
-> open Display & brightness
-> read original checked state
-> restart/re-navigate independently for the mutation session
-> switch to the opposite light/dark mode
-> verify checked-state transition
-> restore original mode
-> verify restoration
-> HOME
```

Final result:

- initial mode: light;
- temporary mode: dark;
- restored mode: light;
- semantic selector mode;
- no absolute-coordinate fallback;
- Mac runtime required: false.

Two acceptance-harness races were fixed during final validation:

1. wait for Settings to become the foreground package instead of relying on a
   fixed launch sleep;
2. do not assume an embedded SubSettings page survives across instrumentation
   sessions; re-navigate semantically in the mutation session.

These fixes modify the acceptance harness, not TikTok business behavior.

### Driver reset / stale-session safety

PASS on the current accepted code:

- safe checkpoint -> driver reset PASS;
- `workflow_replayed=false`;
- health after reset -> HEALTHY;
- unsafe checkpoint -> `RECONCILE_REQUIRED`;
- `workflow_replayed=false`;
- durable state -> BLOCKED / RECONCILE_REQUIRED;
- health after reset -> HEALTHY.

### Screen-off / keyguard recovery

PASS from the previously recorded real-Y700 acceptance evidence:

- Awake -> Asleep;
- `screen_initially_on=false` detected;
- wake attempted;
- keyguard blocking detected;
- dismiss attempted;
- final `screen_on=true`;
- final `keyguard_blocking=false`;
- workflow PASS.

A closure-time attempt to reproduce the exact initial-off timing was
inconclusive because instrumentation startup itself woke the display before
preflight. No screen/keyguard-preflight code changed after the accepted real
screen-off evidence, so the existing real-device acceptance remains valid.

### Cooperative cancellation

PASS.

- cancellation requested after action execution began;
- Bridge/UI state entered CANCELLING;
- final workflow status CANCELLED;
- error `WORKFLOW_CANCELLED`;
- 1 of 50 observation-only actions completed;
- `safe_to_resume=true`.

### Driver/runtime health

PASS.

- driver version: 0.5.0;
- driver ready: true;
- UI Automator ready: true;
- screen on: true;
- keyguard blocking: false;
- instrumentation registered: true;
- Gboard/default IME available;
- thermal status normal;
- runtime filesystem permissions: directories 0700 / files 0600.

### Bridge v2 integration

PASS / previously frozen Sprint 6A acceptance remains valid.

Closure health:

- protocol version 2;
- filesystem transport authoritative;
- active jobs: 0;
- queued jobs: 0;
- running jobs: 0;
- cancelling jobs: 0;
- orphaned jobs: 0;
- dispatch blocked by live orphan: false;
- active scan: approximately 10 ms;
- root round-trip: PASS.

One archived `RECONCILE_REQUIRED` record remains intentionally durable:

`root-1791090522091-8b7350dc`

It records the earlier ZUXOS path-based PackageManager install hang
(`EXECUTION_TIMEOUT_CHILD_STILL_RUNNING`). The stuck process group was
explicitly recovered, the live-orphan block cleared, and the deployment path
was subsequently replaced with SHA-aware stdin + `pm install -S`. The archived
record is historical evidence, not a current runtime blocker.

### APK deployment

PASS.

- build APK SHA-256 is compared with installed package SHA-256;
- unchanged APKs are skipped;
- changed APKs use stdin + `pm install -S`;
- installed SHA is verified after install;
- instrumentation registration is checked.

### TikTok generic-core DRY_RUN

PASS / FROZEN.

- generic Android Automation Core path;
- semantic selectors only;
- no implicit `index` / first-match selection;
- PRIVATE visibility verified;
- final Publish control asserted but never clicked;
- generic adapter exposes no COMMIT/publish API;
- 20 real-Y700 cold-start runs: 20/20 PASS (100%);
- PRD threshold: >=19/20;
- host workflow P50: 41,217.9 ms;
- host workflow maximum: 49,640.7 ms;
- `home-create` maximum after idle-wait fix: 9,391 ms.

Remaining Core failure/recovery work did not modify the frozen TikTok DRY_RUN
business path; the 20-run gate therefore remains valid.

## PRD Definition-of-Done matrix

| DoD item | Status | Evidence / note |
| --- | --- | --- |
| AndroidX UI Automator 2.4 driver builds on Mac | PASS | Gradle app + androidTest build |
| Driver installs on Y700 | PASS | installed / instrumentation registered |
| Y700 runtime does not require Mac | PASS | real workflows run from Y700 runtime |
| observe API | PASS | generic/observation acceptance |
| semantic selector | PASS | Settings, semantic-actions, TikTok |
| click | PASS | real Settings/TikTok flows |
| long click | PASS | semantic-actions acceptance |
| swipe / scroll | PASS | normalized swipe + semantic scroll acceptance |
| Unicode input | PASS | exact `深色模式` actual-state verification |
| waitFor | PASS | Settings + semantic flows |
| waitStable | PASS | Settings + observation recovery |
| assertion | PASS | Settings/TikTok/action acceptance |
| evidence capture | PASS | screenshot + compact tree + full failure context |
| recovery framework | PASS | observation ladder, screen/keyguard, driver reset |
| root bridge integration | PASS | Bridge v2 health + root round-trip |
| Settings workflow | PASS | real reversible flow |
| reversible settings change | PASS | light -> dark -> light restored |
| Mac powered-off acceptance | DEFERRED | explicitly deferred by project owner |
| external Wi-Fi / hotspot acceptance | DEFERRED | paired with physical Mac-Off gate |
| TikTok controller migrated | PASS | generic-core DRY_RUN |
| 20 cold-start TikTok DRY_RUNs | PASS | 20/20 |
| >=95% TikTok regression success | PASS | 100% |
| no duplicate production action | PASS | Bridge crash/replay acceptance; no DRY_RUN publish |
| commit boundary preserved | PASS | DRY_RUN cannot call final publish; COMMIT still explicit |
| legacy coordinate path fallback only | PASS | accepted generic flows semantic; normalized swipe only |
| health/checkpoint updated | PASS | final closure update |
| Git SOT updated | PASS after closure commit | this report + CHECKPOINT + implementation status |

## Bridge v2 Sprint 6B

**NOT ACTIVATED / NOT REQUIRED.**

Filesystem mode remains healthy and authoritative. No measured latency, CPU, or
wakeup problem currently justifies adding the optional Unix-socket daemon.

## Deferred gate

The only intentionally deferred hard PRD scenario is:

```text
Mac physically powered off
Y700 on external Wi-Fi / phone hotspot
Cloud-side control executes the complete Settings acceptance
```

When that scenario is eventually run, it should append evidence to this
acceptance record; it should not reopen already-passed Core/TikTok functional
tests unless the runtime code changes.
