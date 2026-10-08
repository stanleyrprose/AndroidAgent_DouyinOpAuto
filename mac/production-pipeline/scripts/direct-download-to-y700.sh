#!/bin/bash
set -euo pipefail
PIPE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${1:-}"
ALBUM="${2:-Y700Agent}"
if [ -z "$URL" ]; then
  echo "usage: direct-download-to-y700.sh <douyin_url> [album]" >&2
  exit 2
fi

set +e
out="$(bash "$PIPE_ROOT/scripts/pipeline.sh" direct-download "$URL")"
rc=$?
set -e
status="$(python3 - "$out" <<'PY'
import json,sys
try: d=json.loads(sys.argv[1])
except Exception: print('INVALID')
else: print(d.get('status',''))
PY
)"
job_id="$(python3 - "$out" <<'PY'
import json,sys
try: d=json.loads(sys.argv[1])
except Exception: print('')
else: print(d.get('job_id',''))
PY
)"

if [ "$status" = "EXISTING_DIRECT_JOB" ] && [ -n "$job_id" ]; then
  state="$(python3 - "$out" <<'PY'
import json,sys
d=json.loads(sys.argv[1]); print(d.get('state',''))
PY
)"
  intent="$(python3 - "$out" <<'PY'
import json,sys
d=json.loads(sys.argv[1]); print(d.get('workflow_intent',''))
PY
)"
  if [ "$intent" != "DIRECT_DOWNLOAD" ]; then
    echo "existing job intent mismatch" >&2
    exit 4
  fi
  if [ "$state" = "DIRECT_DOWNLOADED" ]; then
    printf '{"status":"ALREADY_COMPLETE","job_id":"%s"}\n' "$job_id"
    exit 0
  fi
  if [ "$state" = "EXPORTED" ]; then
    exec bash "$PIPE_ROOT/scripts/complete-direct-download.sh" "$job_id" "$ALBUM"
  fi
  echo "existing direct job is not resumable from state=$state; use Resume Task / 继续任务" >&2
  exit 5
fi

if [ "$rc" -ne 0 ] || [ "$status" != "EXPORTED" ] || [ -z "$job_id" ]; then
  printf '%s\n' "$out" >&2
  exit 3
fi
exec bash "$PIPE_ROOT/scripts/complete-direct-download.sh" "$job_id" "$ALBUM"
