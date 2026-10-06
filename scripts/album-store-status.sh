#!/bin/bash
set -euo pipefail
JOB_ID="${1:-}"
if [ -z "$JOB_ID" ] || [[ ! "$JOB_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "usage: album-store-status.sh <job_id>" >&2
  exit 2
fi
RESULT="/opt/y700/runtime/album-store/$JOB_ID/result.json"
POWER="/opt/y700/runtime/album-store/$JOB_ID/power-restore.json"
STATE="/opt/y700/runtime/state/album-store.json"
if [ -f "$RESULT" ]; then
  python3 - "$RESULT" "$POWER" <<'PY'
import json,sys
result=json.load(open(sys.argv[1],encoding='utf-8'))
power={}
if len(sys.argv)>2:
    try: power=json.load(open(sys.argv[2],encoding='utf-8'))
    except Exception: pass
result['power_restore']=power
print(json.dumps(result,ensure_ascii=False))
PY
elif [ -f "$STATE" ]; then
  cat "$STATE"
else
  printf '{"status":"UNKNOWN","job_id":"%s"}\n' "$JOB_ID"
fi
