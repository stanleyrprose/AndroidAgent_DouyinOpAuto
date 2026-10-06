#!/bin/bash
set -euo pipefail
umask 0077

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
READY_ROOT="${Y700_READY_ROOT:-/opt/y700/media/ready}"
PUBLISHED_ROOT="${Y700_PUBLISHED_ROOT:-/opt/y700/media/published}"
RUN_ROOT="${Y700_PUBLISH_RUN_ROOT:-/opt/y700/runtime/publish-runs}"
STATE_PATH="${Y700_PUBLISH_STATE:-/opt/y700/runtime/state/publisher.json}"
ROOT_EXEC="${Y700_ROOT_EXEC:-$ROOT/bridge/root-exec.sh}"
JOB_ID="${1:-}"

if [ -z "$JOB_ID" ] || [[ ! "$JOB_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "usage: restore-initial-power-state.sh <job_id>" >&2
  exit 2
fi

marker=""
if [ -f "$PUBLISHED_ROOT/$JOB_ID/initial-power-state.json" ]; then
  marker="$PUBLISHED_ROOT/$JOB_ID/initial-power-state.json"
elif [ -f "$READY_ROOT/$JOB_ID/initial-power-state.json" ]; then
  marker="$READY_ROOT/$JOB_ID/initial-power-state.json"
fi

if [ -z "$marker" ]; then
  printf '{"status":"RESTORE_NOT_REQUIRED_NO_MARKER","job_id":"%s"}\n' "$JOB_ID"
  exit 0
fi

read_marker() {
  python3 - "$marker" "$1" <<'PY'
import json,sys
path,key=sys.argv[1:]
try:
    d=json.load(open(path,encoding="utf-8"))
except Exception:
    print("")
else:
    value=d.get(key,"")
    if isinstance(value,bool):
        print("true" if value else "false")
    else:
        print(value)
PY
}

initial="$(read_marker initial_power_state)"
restored_at="$(read_marker restored_at)"
if [ -n "$restored_at" ]; then
  printf '{"status":"ALREADY_RESTORED","job_id":"%s","initial_power_state":"%s"}\n' "$JOB_ID" "$initial"
  exit 0
fi
if [ "$initial" != "ASLEEP" ]; then
  printf '{"status":"RESTORE_NOT_REQUIRED","job_id":"%s","initial_power_state":"%s"}\n' "$JOB_ID" "${initial:-UNKNOWN}"
  exit 0
fi

if [ ! -f "$STATE_PATH" ]; then
  printf '{"status":"RESTORE_DEFERRED_NO_PUBLISHER_STATE","job_id":"%s"}\n' "$JOB_ID"
  exit 6
fi
read -r state_job state_status < <(python3 - "$STATE_PATH" <<'PY'
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding="utf-8"))
except Exception:
    print(" ")
else:
    print(str(d.get("job_id","")),str(d.get("status","")))
PY
)
if [ "$state_job" != "$JOB_ID" ] || [[ "$state_status" != "PUBLISHED" && "$state_status" != "FAILED" ]]; then
  printf '{"status":"RESTORE_DEFERRED_STATE_MISMATCH","job_id":"%s","publisher_job_id":"%s","publisher_status":"%s"}\n' "$JOB_ID" "$state_job" "$state_status"
  exit 6
fi

for pidfile in "$RUN_ROOT"/*/pid; do
  [ -f "$pidfile" ] || continue
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  [ -n "$pid" ] || continue
  case "$pid" in *[!0-9]*) continue ;; esac
  if kill -0 "$pid" 2>/dev/null; then
    owner="$(basename "$(dirname "$pidfile")")"
    printf '{"status":"RESTORE_DEFERRED_PUBLISHER_RUNNING","job_id":"%s","active_job_id":"%s"}\n' "$JOB_ID" "$owner"
    exit 5
  fi
done

if ! "$ROOT_EXEC" 'input keyevent KEYCODE_SLEEP'; then
  printf '{"status":"RESTORE_FAILED","job_id":"%s","reason":"KEYCODE_SLEEP_FAILED"}\n' "$JOB_ID" >&2
  exit 7
fi

python3 - "$marker" <<'PY'
import json,os,sys,time
path=sys.argv[1]
d=json.load(open(path,encoding="utf-8"))
d["restored_at"]=time.strftime("%Y-%m-%dT%H:%M:%S%z")
d["restore_action"]="KEYCODE_SLEEP"
tmp=path+".tmp"
with open(tmp,"w",encoding="utf-8") as f:
    json.dump(d,f,ensure_ascii=False,indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())
os.replace(tmp,path)
os.chmod(path,0o600)
PY
printf '{"status":"RESTORED_ASLEEP","job_id":"%s","initial_power_state":"ASLEEP"}\n' "$JOB_ID"
