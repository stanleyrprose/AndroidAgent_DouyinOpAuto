# PRD v0.5 Rev2 — Implementation Status

Date: 2026-10-03

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

## Remaining PRD Work

1. Hard Mac-Off acceptance: physically power down the Mac and repeat an
   independent Y700 Settings workflow over an external network.
2. Migrate the TikTok controller to the generic Android Automation Core without
   rewriting the TikTok business state machine.
3. Run 20 TikTok cold-start DRY_RUN regressions and achieve >= 19/20 PASS.
4. Only benchmark a persistent instrumentation runner if workflow-scoped startup
   overhead becomes a proven bottleneck.
