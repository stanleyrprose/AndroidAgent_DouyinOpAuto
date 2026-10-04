# PRD v0.5 Rev2 — Implementation Status

Date: 2026-10-04

## Status

Sprint 0–5 are implemented and validated on the real Lenovo Y700.

Hard Mac-Off acceptance remains pending because the Mac has not been physically
powered down during a validation run. The runtime path itself no longer invokes
Mac services after the Automation Driver has been installed.

## Sprint 0 — Baseline

Legacy `uiautomator dump` on Y700:

- 10/10 PASS
- P50: ~2429 ms
- P95: ~2556 ms

AndroidX UI Automator observations:

- first observation on Settings: ~505–560 ms
- warm observation in the same workflow-scoped instrumentation session: ~41–99 ms
- full per-session end-to-end overhead remains larger, validating the decision to
  use one instrumentation session per workflow rather than one per action.

## Sprint 1 — Driver / IPC

Implemented:

- AndroidX UI Automator 2.4.0 instrumentation driver
- protocol/version handshake
- workflow-scoped instrumentation
- durable root-owned UI job directories
- atomic temp + fsync + rename writes
- heartbeat
- action journal
- checkpoint
- structured result
- screenshot evidence export
- permission probe
- driver health probe
- direct Mac build/release deployment over Cloudflare SSH

New job permissions:

- directories: 0700
- durable files: 0600

No 0777 runtime workaround is used for new jobs.

## Sprint 2 — Semantic Actions

Implemented:

- find / findAll
- click / longClick
- inputText / clearText
- swipe / scroll
- waitFor
- assert
- pressBack / pressHome
- resource-id, text, content-desc, class, package and state selectors
- relation selectors:
  - has_parent
  - has_ancestor
  - has_child
  - has_descendant

Cardinality is deterministic:

- find: 0 -> ELEMENT_NOT_FOUND
- find: 1 -> PASS
- find: >1 -> SELECTOR_AMBIGUOUS
- findAll may return zero or many elements

No implicit "first match" behavior is allowed.

## Sprint 3 — Wait / Retry

Implemented:

- AndroidX waitForStableInActiveWindow
- bounded retry
- explicit retry_backoff_ms
- default exponential backoff
- safe retry only for OBSERVE_ONLY / IDEMPOTENT actions unless explicitly marked
- action latency and attempts in results

Real validation:

- waitStable: PASS
- missing semantic element:
  - 3 attempts
  - 100 ms then 250 ms backoff
  - final ELEMENT_NOT_FOUND
- relation selector initially returned SELECTOR_AMBIGUOUS for 2 matches;
  refining by parent RecyclerView + descendant title produced exactly one match.

## Sprint 4 — Lifecycle / Recovery

Implemented:

- screen-off preflight
- automatic wake
- keyguard detection
- authorized keyguard dismissal attempt
- driver reset
- stale-session safety
- unsafe checkpoint -> RECONCILE_REQUIRED
- no workflow replay during driver reset

Real screen-off test:

- device changed Awake -> Asleep
- workflow detected screen_initially_on=false
- wake attempted
- keyguard initially blocking
- keyguard dismiss attempted
- final screen_on=true
- final keyguard_blocking=false
- UI Automator ready
- workflow PASS

Driver reset injection:

- safe checkpoint -> driver reset PASS, workflow_replayed=false
- next health -> HEALTHY
- unsafe checkpoint -> RECONCILE_REQUIRED, workflow_replayed=false
- next health -> HEALTHY

## Sprint 5 — Generic Settings Acceptance

The first non-TikTok application acceptance is PASS.

Flow:

```text
launch Settings
-> wait stable
-> semantic open search
-> Unicode input 深色模式
-> relation-selector search result
-> open Display & brightness
-> read original checked state
-> temporarily switch mode
-> verify checked-state transition
-> restore original mode
-> verify restoration
-> HOME
```

Result:

```json
{
  "status": "PASS",
  "initial_mode": "light",
  "temporary_mode": "dark",
  "restored_mode": "light",
  "mac_runtime_required": false,
  "selector_mode": "semantic",
  "absolute_coordinate_used": false
}
```

## Dark Mode False-Positive Fix

The Y700 Settings app uses a two-pane tablet layout.

The left search pane may continue showing the text `深色模式` while the right
pane has already navigated elsewhere. Therefore "text 深色模式 exists" is not
a valid postcondition.

The acceptance now uses explicit semantic state:

- `dark_mode_white_check.checked`
- `dark_mode_black_check.checked`

and proves both the transition and the restoration.

## Current Runtime Health

Latest validation:

- driver: HEALTHY
- UI Automator: ready
- root bridge: healthy
- keyguard: not blocking
- Gboard restored/default
- thermal status: normal
- filesystem permission probe: PASS

## TikTok Generic-Core Migration

PASS / frozen baseline on 2026-10-04.

- acceptance baseline: `4c19067bc63d43df1472668ec0abeff98bc82283`;
- TikTok DRY_RUN now uses the generic Android Automation Core;
- no final Publish action exists in the generic adapter;
- semantic selectors only, with deterministic cardinality;
- 20 real-Y700 cold-start DRY_RUN regressions: **20/20 PASS (100%)**;
- PRD threshold: >=19/20 PASS;
- host workflow P50: 41,217.9 ms;
- host workflow max: 49,640.7 ms;
- `home-create` max: 9,391 ms after bounding implicit UiAutomator idle waits.

Evidence: `docs/TIKTOK-GENERIC-DRYRUN-ACCEPTANCE-2026-10-04.md`.

The accepted TikTok DRY_RUN business path is frozen during the remaining Core
recovery/evidence work.

## Deployment Hardening

The Y700 deployment path now:

1. compares the built APK SHA-256 with the installed package SHA-256;
2. skips unchanged APKs;
3. installs changed APKs through stdin + `pm install -S`;
4. verifies the installed SHA-256 after install;
5. verifies instrumentation registration.

This replaces the ZUXOS-sensitive path-based `pm install <apk-path>` flow,
which was observed to hang inside PackageManager.

## Remaining PRD Work

1. Hard Mac-Off acceptance: physically power down the Mac and repeat an
   independent Y700 Settings workflow over an external network.
2. Complete and validate the generic Failure Evidence Contract for failed UI
   actions, including automatic screenshot and compact UI-tree/context capture.
3. Add a dedicated UI-observation-failure recovery injection acceptance.
4. Audit the remaining generic semantic actions for explicit real-Y700 evidence
   where implementation exists but acceptance evidence is not yet recorded.
5. Only benchmark a persistent instrumentation runner if workflow-scoped startup
   overhead becomes a proven bottleneck.
