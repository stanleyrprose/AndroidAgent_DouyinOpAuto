# Y700 on-demand Android Bridge / low-power operating contract

## Goal and boundaries

- **Goal:** Eliminate idle `host-executor.sh` polling and its supervision of `health-loop.sh`; retain safe Android host execution via the existing v2 filesystem protocol, with an explicitly available v1 fallback.
- **Observable success:** No host-executor or health-loop is started by normal boot; each authorized request launches a serialized one-shot executor, writes its durable result and exits; an asleep display is never woken merely to process a request. A subsequent request after screen-on can dispatch queued asynchronous jobs.
- **Non-goals:** No new Webhook/server/daemon, no Android partition modifications, no changes to TikTok publication approval/commit semantics, and no claim that this alone fixes Qualcomm Wi-Fi/PCIe suspend failures.

## Execution model

1. Existing CodexPro/CLI submits a complete `/opt/y700/jobs/.staging/<job>` and atomically publishes it to `active`. The existing authenticated remote access boundary is unchanged.
2. On the real Y700, `bridge_client.py` dispatches one temporary Android host executor via `flock` + `chroot /proc/1/root`. This is **not** an externally exposed HTTP endpoint.
3. `flock` serializes independent callers. Each accepted request produces an independent trigger, preventing a race when the preceding worker exits. The host keeps existing claim, request hash, durable journal, cancellation, result-marker-last, reconciliation and non-replay controls.
4. If backlight `bl_power=4`, **synchronous `exec-root` refuses before writing a job** (exit 75). Explicit asynchronous `submit-root` may durably queue a request but does not launch Android execution. The Android host checks the display again before claiming jobs.
5. After physical screen-on, the existing Cloudflare/CodexPro process may reconnect as Android permits Wi-Fi and CPU activity. The next explicit Bridge request triggers the one-shot executor; a queued asynchronous job can also be triggered with `python3 bridge/bridge_client.py dispatch-pending`. An idle device does **not** run a timer or watcher solely to drain pending jobs.
6. Idle is reported as `android_bridge=IDLE`, not a failure. The host executor and health-loop no longer supervise or restart each other.

The existing Cloudflare connector process and SSH listener remain configured at boot; **this change removes CF self-heal polling but does not kill the tunnel on screen-off**. Doing that without a proven independent screen-on event receiver and authenticated fallback could strand the remote node. The Android kernel retains suspend ownership: default wake-lock policy is `external`. A configured `persistent` wake-lock remains an explicit rollback, not the low-power default.

## Safety and recovery

- **Ambiguous commits:** A lost executor with a claimed job is reconciled, never automatically executed a second time. Timed-out child processes are recorded as live-orphan / reconciliation-required; they are not force-killed by the one-shot path.
- **Concurrent requests:** The temporary dispatcher takes `/opt/y700/runtime/host-executor-dispatch.lock`; an in-flight worker runs to completion before the next begins.
- **Display race:** An Android host executor must independently recheck screen state; already-running operations are not force-killed when the display is turned off.
- **Legacy rollback:** Set `Y700_BRIDGE_DISPATCH_MODE=legacy`, explicitly start a host executor with `Y700_BRIDGE_ONESHOT=0`, and use the existing `start-health-loop.sh` manually only if continuous supervision is specifically required. Restore prior boot wiring and wake-lock policy only as a separately authorized rollback.
- **Missing backlight sensor:** Explicit requests remain recoverable rather than being silently and permanently rejected; this is a deliberate fail-open *availability* choice, not an assertion that the screen is on.
- **No queue auto-replay:** Explicit asynchronous queue entries are replayed only if unclaimed; reconciliation-required jobs remain blocked pending review.

## Later validation and production migration (not performed during development)

1. Run only affected tests for Bridge v1/v2, on-demand dispatch, singleton/orphans, health reporting and boot startup; static syntax checks; verify the known Android host paths and lock permissions.
2. With a physically awake Y700 and authenticated secondary recovery path, deploy *only* affected files and preserve originals. The Android boot copy at `/data/local/y700-agent/runtime/boot-start.sh` must be updated separately from Git.
3. Confirm no active job or live orphan before stopping **old** resident `host-executor` and `health-loop`. Leave CodexPro, cloudflared and SSH alive during first rollout.
4. Verify one-shot execution, concurrent submissions, standby refusal, screen-on recovery, cancellation, legacy read, and rollback. Do not publish a TikTok post as a diagnostic.
5. Compare at least 60 minutes of screen-off `mAh/h`, CPU uptime, suspend success/fail, `qcom_rx_wakelock` and `timerfd` activity against the current baseline. Success in functional gates is not proof of lower battery drain.

**Phase D status:** source implementation only. No tests, PR/CI, merge, device deployment or runtime-service stop.
