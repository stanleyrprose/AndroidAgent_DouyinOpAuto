#!/bin/bash
set -euo pipefail
JOB_ID="${1:-}"
if [ -z "$JOB_ID" ]; then
  echo "usage: publish-status.sh <job_id>" >&2
  exit 2
fi

RUN_DIR="/opt/y700/runtime/publish-runs/$JOB_ID"
PID=""
RUNNING=false
if [ -s "$RUN_DIR/pid" ]; then
  PID="$(cat "$RUN_DIR/pid" 2>/dev/null || true)"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    RUNNING=true
  fi
fi

python3 - "$JOB_ID" "$PID" "$RUNNING" <<'PY'
import json,sys
from pathlib import Path
job,pid,running=sys.argv[1:]
running=running.lower()=="true"
state_path=Path("/opt/y700/runtime/state/publisher.json")
state={}
if state_path.exists():
    try: state=json.load(open(state_path))
    except Exception: state={"status":"STATE_INVALID"}

published=Path("/opt/y700/media/published")/job
ready=Path("/opt/y700/media/ready")/job
mode=None
manifest=ready/"manifest.json"
if manifest.exists():
    try: mode=json.load(open(manifest)).get("publish_mode")
    except Exception: pass

current=state if state.get("job_id")==job else {"status":"OTHER_JOB","current":state.get("job_id")}
st=current.get("status")
if published.is_dir() or st=="PUBLISHED":
    derived="PUBLISHED"
elif running:
    derived="RUNNING"
elif st=="READY_TO_COMMIT" and mode=="DRY_RUN":
    derived="DRY_RUN_PASS"
elif st=="FAILED":
    derived="FAILED"
elif st=="COMMITTING":
    derived="AMBIGUOUS_COMMIT_NEEDS_RECONCILE"
elif st=="READY_TO_COMMIT":
    derived="READY_TO_COMMIT"
elif st and st!="OTHER_JOB":
    derived=f"STOPPED_{st}"
else:
    derived="IDLE"

out={
    "job_id":job,
    "status":derived,
    "runner_pid":int(pid) if pid.isdigit() else None,
    "runner_running":running,
    "ready":ready.is_dir(),
    "published":published.is_dir(),
    "publish_mode":mode,
    "publisher_state":current,
}
print(json.dumps(out,ensure_ascii=False,indent=2))
PY
