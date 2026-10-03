# Bridge v2 — Sprint 6A Implementation

Date: 2026-10-03

This document is the implementation companion for the frozen Bridge v2 Sprint 6
baseline. It does not change the frozen architectural decisions.

## Runtime contract

Bridge v2 keeps the filesystem as the only required durable source of truth.

```text
/opt/y700/jobs/
├── .staging/
├── active/
├── archive/
│   ├── succeeded/
│   ├── failed/
│   ├── cancelled/
│   └── reconcile_required/
└── control/
```

The Android-host view is the corresponding
`/data/local/y700-agent/jobs` tree.

New v2 jobs are fully written and fsynced under `.staging/<job_id>`, then
become executable only after a same-filesystem atomic rename to
`active/<job_id>`. The Android-host executor never scans `.staging`.

## v1/v2 rolling migration

The host executor is a dual reader during the migration window:

- v1: `/opt/y700/jobs/<job_id>`;
- v2: `/opt/y700/jobs/active/<job_id>`.

`bridge/root-exec.sh` remains capable of writing v1. It switches to the v2
client only after the running executor has durably published
`control/protocol.json` with preferred protocol version 2. This prevents a
code-first deployment from stranding v2 jobs before the executor is restarted.

Legacy completed v1 jobs remain under `/opt/y700/runtime/job-history`; they are
not bulk-migrated.

## Lifecycle and recovery

The v2 lifecycle is:

```text
QUEUED -> CLAIMED -> RUNNING -> SUCCEEDED | FAILED
                     |
                     +-> CANCELLING -> terminal
                     |
                     +-> ORPHANED classification -> RECONCILE_REQUIRED
```

`result.json` is the terminal completion marker and is published only after
terminal state and logs are durable. A terminal v2 job is then atomically moved
from `active` to the corresponding archive class.

Generic `root_exec` has replay policy `NEVER`. It cannot self-declare
`SAFE_IDEMPOTENT`.

## Cancellation

Cancellation is cooperative.

- before claim/start/side effect: the job may become `CANCELLED`;
- while generic `root_exec` is running: state becomes `CANCELLING`;
- generic `root_exec` is never automatically SIGTERM/SIGKILLed;
- a running command that exceeds its timeout while still alive becomes
  `RECONCILE_REQUIRED`, not falsely `CANCELLED`.

Repeated cancel requests are idempotent at the semantic level. The latest
`cancel.json` is authoritative and journal entries preserve the request
history.

## Orphan safety

Claim ownership records include executor identity and, after child start:

- child PID;
- PGID;
- process session/job ID;
- `/proc/<pid>/stat` start ticks;
- command start time;
- SHA-256 of the immutable request.

PID/PGID alone is never treated as sufficient process identity.

If a restarted executor proves that an orphan child is still running, the job
is archived as `RECONCILE_REQUIRED`, a durable
`control/live-orphan.json` record is written, and privileged dispatch stays
blocked until that exact process identity exits. No blind replay or generic
force-kill is performed.

A claim for which no child was ever persisted is not replayed; it is closed as
a deterministic pre-child failure.

## Status lookup

The v2 client performs bounded direct lookup:

1. the four known archive classes;
2. `active/<job_id>`;
3. 100 ms grace;
4. one repeat of the same lookup;
5. v1 compatibility lookup.

It does not scan the archive and does not introduce SQLite.

## Timing defaults

Initial operational defaults:

```text
executor heartbeat: 2 s
lease timeout:      15 s
reconcile cadence:  30 s
poll cadence:       250 ms
```

Lease expiry is liveness evidence only and never authorizes replay.

## Size and disk guards

Implementation defaults:

```text
request.json       <= 256 KiB
cancel.json        <= 16 KiB
durable state JSON <= 64 KiB
journal row        <= 64 KiB
```

New v2 submission is blocked by the existing storage safety policy when free
space is below the configured threshold. Stale staging cleanup is an explicit
maintenance operation, never part of the executor hot loop.

`archive/reconcile_required` is not automatically deleted.

## Client commands

```bash
python3 bridge/bridge_client.py health
python3 bridge/bridge_client.py submit-root -- <command>
python3 bridge/bridge_client.py status <job_id>
python3 bridge/bridge_client.py cancel <job_id> --reason <reason>
python3 bridge/bridge_client.py wait <job_id> --timeout <seconds>
python3 bridge/bridge_client.py reconcile [job_id]
python3 bridge/bridge_client.py cleanup-staging --ttl-seconds 86400
```

Existing callers may continue using:

```bash
bridge/root-exec.sh '<android-root-shell-command>'
```

The wrapper chooses v1 or v2 according to the executor's durable protocol
advertisement.

## Unix socket

Sprint 6A adds no Unix socket daemon. A socket remains a Sprint 6B
measurement-gated optimization only. If ever added, filesystem state remains
authoritative and socket failure must degrade latency rather than correctness.

## Acceptance

Repository tests cover the client contract, including atomic submission,
archive lookup, duplicate cancellation, malformed state, bounded request size,
v1 lookup, staging cleanup, corrupt control data, reserved IDs, archive ID
collision, symlink rejection, and CLI separator handling.

Real Y700 acceptance must additionally exercise executor crash/restart,
live-orphan behavior, cancellation during execution, timeout behavior,
result-before-archive recovery, permissions, archive scale, v1 regression, and
the generic Settings workflow before Sprint 6A is marked closed.
