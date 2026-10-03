# Y700 Android Automation Core

PRD v0.5 Rev2 implementation.

## Architecture

- **Mac**: build/release only.
- **Y700**: independent runtime.
- **Cloud GPT**: orchestration/reasoning.
- **AndroidX UI Automator 2.4.0**: semantic UI core.
- **KernelSU/root bridge**: privileged control plane.
- **Filesystem job state**: durable SOT for runtime execution.

Mac is not a runtime dependency after the driver is installed.

## Implemented

### Sprint 0

- Legacy `uiautomator dump` baseline measured on Y700.
- Legacy P50 ≈ 2429 ms, P95 ≈ 2556 ms.
- AndroidX observe benchmark proved materially faster.
- Build toolchain installed on Mac: JDK 17, Android SDK 36, Build Tools 36.0.0.

### Sprint 1

- Workflow-scoped instrumentation runner.
- AndroidX UI Automator 2.4.0.
- Health / observe / screenshot.
- Atomic durable job runtime on Y700.
- Heartbeat / journal / checkpoint.
- Root-only runtime permissions.
- Driver health and permission probes.
- Direct Mac → Y700 deploy path via Cloudflare SSH.

### Sprint 2

- `find` / `findAll`.
- deterministic 0/1/many selector cardinality.
- `click` / `longClick`.
- `inputText` / `clearText`.
- `swipe` / `scroll`.
- `waitFor` / `assert`.
- semantic relation selectors:
  - `has_parent`
  - `has_ancestor`
  - `has_child`
  - `has_descendant`

### Sprint 3

- AndroidX `waitForStableInActiveWindow`.
- bounded retry/backoff.
- retry only for safe/idempotent actions unless explicitly overridden.
- latency per action.
- selector ambiguity returns `SELECTOR_AMBIGUOUS`; never silently selects the first match.

### Sprint 4

- driver health probe.
- permission probe.
- driver/session reset without workflow replay.
- unsafe checkpoint returns `RECONCILE_REQUIRED`.
- screen-off recovery.
- keyguard dismissal attempt.
- UI workflow blocks if keyguard remains active.

### Sprint 5

Settings acceptance is PASS on the real Y700:

```text
launch Settings
→ semantic search for 深色模式
→ read original checked state
→ switch to opposite mode
→ verify checked states
→ restore original mode
→ verify restoration
→ HOME
```

Acceptance result:

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

## Important regression fixed

On a two-pane tablet Settings UI, merely seeing the text `深色模式` is **not**
a valid postcondition because the left search pane may keep that text visible
while the right pane navigates elsewhere.

Correct acceptance uses explicit checked state:

```text
dark_mode_white_check.checked
dark_mode_black_check.checked
```

The test must prove state transition and restoration.

## Deploy

```bash
./scripts/deploy-y700.sh
```

Deployment flow:

```text
build
→ SCP through Cloudflare SSH
→ SHA256 verify on Y700
→ pm install
→ instrumentation registration verify
```

The deployment key is local to the Mac and is never committed.

## Runtime acceptance

Y700 can run Settings acceptance locally:

```bash
python3 tests/run_settings_acceptance.py
```

No Mac process is required after the driver has been installed.

## Still pending

- hard Mac-Off acceptance with the Mac physically powered down;
- TikTok controller migration to the generic core;
- 20 cold-start TikTok DRY_RUN regressions with >=95% success;
- optional persistent instrumentation benchmark only if workflow-scoped startup
  overhead proves material.
