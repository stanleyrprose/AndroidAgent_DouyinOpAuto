#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JOB_ID="${1:-}"
if [ -z "$JOB_ID" ]; then
  echo "usage: reconcile-public-async.sh <job_id>" >&2
  exit 2
fi

RUN_DIR="/opt/y700/runtime/publish-runs/$JOB_ID"
PID_FILE="$RUN_DIR/reconcile.pid"
LOG_FILE="$RUN_DIR/reconcile.log"
READY="/opt/y700/media/ready/$JOB_ID"
PUBLISHED="/opt/y700/media/published/$JOB_ID"

if [ -d "$PUBLISHED" ]; then
  printf '{"status":"ALREADY_PUBLISHED","job_id":"%s"}\n' "$JOB_ID"
  exit 0
fi
if [ ! -d "$READY" ]; then
  printf '{"status":"NOT_READY","job_id":"%s"}\n' "$JOB_ID" >&2
  exit 3
fi

mkdir -p "$RUN_DIR"
if [ -s "$PID_FILE" ]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
    printf '{"status":"ALREADY_RUNNING","job_id":"%s","pid":%s}\n' "$JOB_ID" "$old_pid"
    exit 0
  fi
fi

: > "$LOG_FILE"
export Y700_RECONCILE_ROOT="$ROOT"
export Y700_RECONCILE_JOB_ID="$JOB_ID"
nohup bash -c '
  set -euo pipefail
  root="$Y700_RECONCILE_ROOT"
  job="$Y700_RECONCILE_JOB_ID"
  cd "$root"
  old_timeout="$($root/bridge/root-exec.sh "settings get system screen_off_timeout" 2>/dev/null | tail -1 | tr -d "\r" || true)"
  case "$old_timeout" in (*[!0-9]*|"") old_timeout=30000;; esac
  restore_timeout() {
    "$root/bridge/root-exec.sh" "settings put system screen_off_timeout $old_timeout" >/dev/null 2>&1 || true
  }
  trap restore_timeout EXIT
  "$root/bridge/androidctl.sh" unlock-secure
  "$root/bridge/root-exec.sh" "settings put system screen_off_timeout 300000" >/dev/null
  timeout --signal=TERM 240 python3 "$root/publisher/reconcile_public.py" "$job"
' >>"$LOG_FILE" 2>&1 </dev/null &
pid=$!
printf '%s\n' "$pid" > "$PID_FILE"
printf '{"status":"STARTED","job_id":"%s","pid":%s,"action":"RECONCILE_ONLY"}\n' "$JOB_ID" "$pid"
