#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME=/opt/y700/runtime/publish-runs
STATE=/opt/y700/runtime/state/publisher.json
JOB_ID="${1:-}"
MODE="${2:-}"

if [ -z "$JOB_ID" ]; then
  echo "usage: publish-async.sh <job_id> [--commit]" >&2
  exit 2
fi

READY="/opt/y700/media/ready/$JOB_ID"
PUBLISHED="/opt/y700/media/published/$JOB_ID"
RUN_DIR="$RUNTIME/$JOB_ID"
PID_FILE="$RUN_DIR/pid"
LOG_FILE="$RUN_DIR/run.log"

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
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    printf '{"status":"ALREADY_RUNNING","job_id":"%s","pid":%s}\n' "$JOB_ID" "$OLD_PID"
    exit 0
  fi
fi

ARGS=("$ROOT/publisher/publish_job.py" "$JOB_ID")
if [ "$MODE" = "--commit" ]; then
  ARGS+=("--commit")
elif [ -n "$MODE" ]; then
  echo "unsupported mode: $MODE" >&2
  exit 2
fi

: > "$LOG_FILE"
RUN_TIMEOUT="${Y700_PUBLISH_RUN_TIMEOUT:-300}"
nohup timeout --signal=TERM "$RUN_TIMEOUT" python3 "${ARGS[@]}" >>"$LOG_FILE" 2>&1 </dev/null &
PID=$!
printf '%s\n' "$PID" > "$PID_FILE"

python3 - "$RUN_DIR/meta.json" "$JOB_ID" "$PID" "$MODE" <<'PY'
import json, os, sys, time
path,job,pid,mode=sys.argv[1:]
tmp=path+".tmp"
with open(tmp,"w",encoding="utf-8") as f:
    json.dump({
        "job_id":job,
        "pid":int(pid),
        "commit":mode=="--commit",
        "started_at":time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    },f,ensure_ascii=False,indent=2)
    f.write("\n")
os.replace(tmp,path)
PY

printf '{"status":"STARTED","job_id":"%s","pid":%s,"commit":%s}\n'   "$JOB_ID" "$PID" "$([ "$MODE" = "--commit" ] && echo true || echo false)"
