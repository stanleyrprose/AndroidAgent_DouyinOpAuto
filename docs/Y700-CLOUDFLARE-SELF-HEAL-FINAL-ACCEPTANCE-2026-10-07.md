# Y700 Cloudflare Remote-Control Self-Heal — Final Acceptance

Date: 2026-10-07

Status: **PASS / CLOSED**

Accepted baseline:

`99cecd73db39f8d6dab8d458164273dd167e9ecd`

## Why this final acceptance was required

An earlier closure at `de1302f` passed one controlled fault test, but a later real-world recurrence disproved completeness: the Cloudflare Tunnel again reached zero active connections and remained unavailable beyond the 75-second target while self-heal did not recover it.

The project therefore reopened the connectivity blocker and required another root-cause cycle plus repeated real-device acceptance.

## Final failure modes closed

### 1. Stale / unreachable chroot DNS

The chroot resolver was repeatedly repopulated from the Android-host file and reintroduced `114.114.114.114`.

On the affected network:

- `8.8.8.8`: reachable;
- `8.8.4.4`: reachable;
- `114.114.114.114`: timeout;
- `1.1.1.1`: timeout;
- `9.9.9.9`: timeout;
- `223.5.5.5`: timeout.

The final design makes the Git-managed resolver baseline authoritative, with an explicit local override path. After repair, `github.com` resolution and Git fetch recovered immediately.

### 2. Remote-probe restart churn

A single remote-probe failure could previously restart cloudflared even while the process was alive with healthy HA connections.

Final behavior:

- process dead or HA connections = 0: fast recovery path;
- process alive and HA connections > 0: require consecutive remote-probe failures before restart.

Observed soft-fault evidence:

`CLOUDFLARED_REMOTE_PROBE_GRACE connections=4 cycles=1 required=2 probe_http=000`

The external control endpoint remained HTTP 200 during that first failed probe.

### 3. Stalled cloudflared process replacement

The restart helper now performs bounded identity-checked termination and escalates TERM -> KILL only when necessary before spawning the replacement process.

### 4. Script executable-mode dependence

Health-loop startup, self-update and cloudflared restart now invoke managed shell scripts through explicit `/bin/bash`. The scripts also retain Git executable mode, but self-heal no longer depends on that metadata being preserved by every deployment/write path.

### 5. Health-loop PID-file ownership race

Repeated testing reproduced a race where an older health-loop instance could exit after a newer instance had already published its PID, and the old EXIT trap could delete the new PID file.

Final cleanup is ownership-safe: it removes the PID file only if the file still contains the exiting process's own `BASHPID`.

## Regression / CI evidence

- Y700 self-heal test suite: **34/34 PASS**.
- Shell syntax: PASS.
- Key self-heal scripts: mode `0755`.
- Self-heal contract tests are wired into GitHub Actions.
- Post-merge GitHub Actions `validate` run for `main@99cecd7`: **SUCCESS**.

## Final real-device Hard Fault

Precondition:

- stable runtime = `y700-agent-release-99cecd7`;
- health-loop PID/version/heartbeat SHA aligned to the final script;
- remote plane READY;
- cloudflared HA connections = 4.

Fault:

- deliberately terminate the active cloudflared process;
- do not touch health-loop or the network path.

External observation:

`530 -> 530 -> 530 -> 200 -> 200 -> 200`

Measured recovery to first HTTP 200: **10.0 seconds**.

Internal evidence:

- 04:16:52 UTC — `CLOUDFLARED_SELF_HEAL_START`;
- 04:16:57 UTC — `CLOUDFLARED_SELF_HEAL_PROCESS_RESTARTED`;
- 04:17:00 UTC — `CLOUDFLARED_SELF_HEAL_OK connections=4 probe_http=200`.

A prior hard-fault run on the same remediation lineage recovered in **9.8 seconds**.

Both are well inside the 75-second acceptance target.

## Final state

- remote plane: READY;
- remote probe HTTP: 200;
- tunnel HA connections: 4;
- restart failures: 0;
- pending retry backoff: none;
- health-loop PID/version/heartbeat: aligned;
- stable immutable release: `y700-agent-release-99cecd7`.

## Boundary

This acceptance closes the Y700 Cloudflare remote-control self-heal blocker only.

It does **not** authorize Android Automation Core v0.6 production implementation, does not widen BUSINESS capability authorization, and does not change TikTok publish/COMMIT approval boundaries.
