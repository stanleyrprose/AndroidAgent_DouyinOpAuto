#!/bin/bash
set -euo pipefail

PIPE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JOB_ID="${1:-}"
if [ -z "$JOB_ID" ] || [[ ! "$JOB_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "usage: start-publication-closure.sh <job_id>" >&2
  exit 2
fi

RUNTIME_ROOT="${Y700_PIPE_RUNTIME_ROOT:-$PIPE_ROOT/runtime}"
RUN_DIR="$RUNTIME_ROOT/jobs/$JOB_ID/closure"
PID_FILE="$RUN_DIR/pid"
LOG_FILE="$RUN_DIR/run.log"
mkdir -p "$RUN_DIR"

if [ -s "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    printf '{"status":"ALREADY_RUNNING","job_id":"%s","pid":%s}\n' "$JOB_ID" "$pid"
    exit 0
  fi
fi

: > "$LOG_FILE"
nohup bash "$PIPE_ROOT/scripts/close-y700-publication.sh" "$JOB_ID" >>"$LOG_FILE" 2>&1 </dev/null &
pid=$!
printf '%s\n' "$pid" > "$PID_FILE"
printf '{"status":"STARTED","job_id":"%s","pid":%s,"action":"PUBLICATION_CLOSURE"}\n' "$JOB_ID" "$pid"
