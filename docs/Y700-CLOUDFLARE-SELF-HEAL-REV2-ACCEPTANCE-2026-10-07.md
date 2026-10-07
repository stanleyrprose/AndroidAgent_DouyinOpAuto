# Y700 Cloudflare Tunnel Self-Heal Rev2 Acceptance

Date: 2026-10-07


## Y700 Cloudflare Remote-Control Self-Heal Closure Rev2 (2026-10-07)

Status: **PASS / CLOSED for process-death, live-but-stalled cloudflared, transient remote-path loss, and health-loop PID ownership race.**

This section refines the earlier self-heal closure. The earlier `de1302f` acceptance was valid for the reproduced process-death/sleep failure mode, but later real-device testing exposed additional failure modes that were not covered by that gate.

Additional failures reproduced during Rev2 closure:

- a natural remote-plane loss returned HTTP 530 for roughly 67 seconds before the existing health loop recovered it without human intervention;
- a deliberate `SIGSTOP` of a live cloudflared process showed that the old restart helper used TERM without proving the stopped process had exited; recovery in that first test depended on the 45-second local failsafe and therefore did **not** qualify as closure;
- the first stalled-process fix was written with Git mode `100644`, so the health loop hit `Permission denied` instead of executing the restart helper;
- the same file-mode class later affected `scripts/health-loop.sh`; launcher/self-update paths therefore had to become executable-bit independent as well;
- runtime logs also observed intermittent resolver/path loss, including timeouts against the historical `114.114.114.114` resolver and later a transient `8.8.4.4` timeout. The mobile network itself remains capable of brief path flaps; the acceptance target is bounded autonomous recovery rather than claiming the underlying carrier path is lossless.

Accepted hardening now in Git SOT:

- managed chroot DNS baseline with `8.8.8.8` + `8.8.4.4`, while retaining explicit override support;
- remote-probe hysteresis for transient probe failures when HA connections are still live, while process-dead / zero-connection faults retain the fast recovery path;
- cloudflared restart verifies PID identity, performs bounded TERM, escalates to KILL when the old cloudflared remains live/stopped, proves the old instance is gone, then starts the replacement;
- health-loop invokes the restart helper with explicit `/bin/bash`, so recovery is not dependent on helper executable mode;
- health-loop launcher and self-update also use explicit `/bin/bash`, while the canonical scripts remain Git `100755`;
- health-loop PID cleanup is generation-safe: an exiting old generation removes the PID file only when it still owns that PID record;
- self-heal, supervision, DNS/hysteresis contracts are enforced by GitHub Actions.

Real-Y700 acceptance evidence:

- candidate `d775909` live-but-stalled test: old cloudflared PID was deliberately `SIGSTOP` at 2026-10-07T03:10:51Z; health-loop entered self-heal at 03:10:58Z; replacement cloudflared started at 03:11:01Z; `CLOUDFLARED_SELF_HEAL_PROCESS_RESTARTED` at 03:11:06Z; `CLOUDFLARED_SELF_HEAL_OK connections=4 probe_http=200` at 03:11:09Z;
- the 90-second safety script recorded `TEST_OLD_PID_GONE`, not `TEST_FAILSAFE_SIGCONT`; old PID was replaced and final remote state was HTTP 200;
- external HTTP sampling during that stalled-process test remained 200 throughout, meaning replacement completed before the edge exposed a visible outage;
- final-main process-death smoke: old cloudflared PID was deliberately killed at 2026-10-07T03:15:59Z; health-loop started recovery at 03:16:06Z and reached `SELF_HEAL_OK connections=4 probe_http=200` at 03:16:15Z; replacement PID differed from the killed PID;
- the 90-second process-death failsafe later recorded `FAILSAFE_NO_ACTION http=200`, proving it did not perform the recovery;
- PR #28 candidate CI run `37565347094`: PASS;
- PR #29 post-merge main CI run `37566020593`: PASS;
- final canonical baseline: `99cecd73db39f8d6dab8d458164273dd167e9ecd`;
- final Y700 self-heal contract suite: **34/34 PASS**;
- final live state: `overall=HEALTHY`, `production_sot=HEALTHY`, remote plane `READY`, 4 Cloudflare HA connections, managed resolver file present, and health-loop PID/version/heartbeat mutually consistent.

Operational decision:

- the Y700 Cloudflare remote-control self-heal blocker is **CLOSED** for the accepted failure classes above;
- brief carrier/Wi-Fi path loss can still occur and is not claimed eliminated;
- no second tunnel daemon, MQ/DB, or active-active failover was added;
- this platform reliability closure does **not** grant or widen Android Automation Core v0.6 Production Runtime Implementation Authorization and does not change publish/COMMIT authorization boundaries.

