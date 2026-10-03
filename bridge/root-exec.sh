#!/bin/bash
set -euo pipefail
umask 0077

if [ "$#" -lt 1 ]; then
  echo "usage: root-exec.sh <android-root-shell-command>" >&2
  exit 64
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JOBS="${Y700_BRIDGE_JOBS:-/opt/y700/jobs}"
RUNTIME="${Y700_RUNTIME:-/opt/y700/runtime}"
TIMEOUT_MS="${Y700_BRIDGE_TIMEOUT_MS:-90000}"
CMD="$*"

# Safe rolling migration: do not emit v2 jobs until the running host executor
# has durably advertised v2 support.
if [ -f "$JOBS/control/protocol.json" ] &&
   grep -q '"preferred_protocol_version"[[:space:]]*:[[:space:]]*2'      "$JOBS/control/protocol.json" 2>/dev/null; then
  exec python3 "$SCRIPT_DIR/bridge_client.py" exec-root     --timeout-ms "$TIMEOUT_MS" -- "$@"
fi

# Legacy v1 writer retained for the M0/M1 rollout window.
HISTORY="$RUNTIME/job-history"
JOB_ID="$(date +%s)-$(openssl rand -hex 4)"
DIR="$JOBS/$JOB_ID"
mkdir -p "$DIR/artifacts" "$HISTORY"
chmod 700 "$DIR" "$DIR/artifacts" "$HISTORY" 2>/dev/null || true
printf '{"status":"PENDING"}\n' >"$DIR/state.json.tmp"
chmod 600 "$DIR/state.json.tmp"
mv "$DIR/state.json.tmp" "$DIR/state.json"
B64="$(printf '%s' "$CMD" | base64 -w 0)"
printf '{"version":1,"action":"root_exec","command_b64":"%s"}\n' "$B64"   >"$DIR/request.json.tmp"
chmod 600 "$DIR/request.json.tmp"
mv "$DIR/request.json.tmp" "$DIR/request.json"

deadline=$((SECONDS + TIMEOUT_MS / 1000 + 1))
while [ ! -f "$DIR/result.json" ]; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "root_exec timeout job=$JOB_ID" >&2
    exit 124
  fi
  sleep 0.25
done

[ ! -s "$DIR/stdout.log" ] || cat "$DIR/stdout.log"
[ ! -s "$DIR/stderr.log" ] || cat "$DIR/stderr.log" >&2
rc="$(sed -n 's/.*"exit_code"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p'   "$DIR/result.json")"
[ -n "$rc" ] || rc=1
mv "$DIR" "$HISTORY/$JOB_ID"
exit "$rc"
