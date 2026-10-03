# Bridge v2 — Sprint 6A Real Y700 Acceptance

Date: 2026-10-04  
Target: Lenovo TB323FU / Android 16 / Debian 13 chroot  
Scope: frozen Bridge v2 Sprint 6A baseline plus implementation checklist

## Result

**PASS**

Sprint 6A is accepted on a real Y700 device. The filesystem remains the only
required durable source of truth. No Unix socket daemon, MQ, SQLite archive
index, or additional network service was introduced.

## Repository gates

Validated on the latest `main` implementation before this closure update:

- Bridge v2 client unit tests: 14/14 PASS;
- Python compile smoke for `bridge`, `automation`, and `publisher`: PASS;
- `bridge/host-executor.sh` syntax: PASS;
- `bridge/root-exec.sh` syntax: PASS.

## Real Android-host lifecycle

Validated against an isolated Bridge v2 runtime root on the real Y700:

- atomic `.staging -> active` submit -> execute -> `archive/succeeded`: PASS;
- non-zero child exit preserved into `archive/failed`: PASS;
- queued cancellation: `CANCELLED_BEFORE_CLAIM`, no side effect: PASS;
- claimed cancellation: `CANCELLED_BEFORE_START`, no side effect: PASS;
- running generic `root_exec` cancellation:
  - state entered `CANCELLING`;
  - child was not force-killed;
  - command was allowed to complete naturally;
  - real completion result was preserved: PASS;
- `CANCELLING` + execution timeout:
  - terminal state `RECONCILE_REQUIRED`;
  - reason `CANCELLATION_INCOMPLETE_TIMEOUT`;
  - `child_alive=true`;
  - no false `CANCELLED`: PASS.

## Crash / ambiguity injection

The host executor test failpoints were exercised on-device:

- crash after claim, before child start:
  - recovery reason `EXECUTOR_LOST_BEFORE_CHILD_START`;
  - command was not replayed;
  - side-effect marker remained absent: PASS;
- crash after result write, before archive rename:
  - existing result was archived on restart;
  - side-effect counter remained exactly one: PASS;
- crash after child start:
  - live child identity was matched using PID + process start ticks;
  - job became `RECONCILE_REQUIRED`;
  - reason `EXECUTOR_LOST_CHILD_STILL_RUNNING`;
  - durable `live-orphan.json` blocked conflicting dispatch;
  - child was not killed;
  - after test-controlled natural exit the block cleared;
  - side-effect counter remained exactly one: PASS.

## Integrity / corruption cases

- request mutation after claim:
  - request hash mismatch detected;
  - terminal state `RECONCILE_REQUIRED`;
  - reason `REQUEST_MUTATED_AFTER_CLAIM`;
  - side effect was not started: PASS;
- malformed durable `state.json`:
  - no delete-and-recreate;
  - no blind replay;
  - terminal state `RECONCILE_REQUIRED`;
  - reason `MALFORMED_STATE`: PASS;
- reserved job IDs, archive collisions, symlink job roots, bounded request size,
  duplicate cancel, corrupt control JSON, and stale staging handling are covered
  by repository tests: PASS.

## Android Automation Core regression

The generic Android Settings acceptance was run through Bridge v2 on the real
Y700:

```text
Light -> temporary Dark -> verified -> restored Light -> verified -> HOME
```

Result:

- status: PASS;
- Mac runtime required: false;
- selector mode: semantic;
- absolute coordinate use: false.

The cooperative UI cancellation acceptance also passed:

- cancellation requested after action execution began;
- final workflow status: `CANCELLED`;
- error code: `WORKFLOW_CANCELLED`;
- only 1 of 50 observation-only actions completed;
- checkpoint `safe_to_resume=true`.

The Android instrumentation driver uses the canonical Android-host cancellation
signal root under `/data/local/y700-agent/ui-cancel-signals`. Acceptance that
overrides the chroot cancellation-signal directory must map to that same host
location; arbitrary isolated overrides are not part of the Sprint 6A contract.

## Production runtime observation

Before closure:

- production Bridge protocol advertisement: v2;
- executor heartbeat interval: 2 s;
- lease timeout: 15 s;
- no unknown active v2 job;
- no incomplete legacy v1 job;
- no live orphan block;
- filesystem transport remains authoritative.

`active_scan_ms` was corrected during closure to measure only active-directory
discovery/stat cost, excluding command execution time. This prevents slow
commands from being misinterpreted as evidence for the Sprint 6B socket gate.

## Sprint 6B

Not started.

Unix socket remains measurement-gated. A later experiment must establish a
real latency/CPU/wakeup problem and explicit thresholds before Sprint 6B can be
opened. Filesystem durability remains authoritative even if a socket transport
is added later.
