#!/bin/bash
set -euo pipefail
umask 0077
if [ "$#" -lt 1 ]; then
  echo "usage: root-exec.sh <android-root-shell-command>" >&2
  exit 64
fi
JOBS=/opt/y700/jobs
HISTORY=/opt/y700/runtime/job-history
CMD="$*"
JOB_ID="$(date +%s)-$(openssl rand -hex 4)"
DIR="$JOBS/$JOB_ID"
mkdir -p "$DIR/artifacts" "$HISTORY"
printf '{"status":"PENDING"}\n' > "$DIR/state.json.tmp"
mv "$DIR/state.json.tmp" "$DIR/state.json"
B64="$(printf '%s' "$CMD" | base64 -w 0)"
printf '{"version":1,"action":"root_exec","command_b64":"%s"}\n' "$B64" > "$DIR/request.json.tmp"
mv "$DIR/request.json.tmp" "$DIR/request.json"
deadline=$((SECONDS + 90))
while [ ! -f "$DIR/result.json" ]; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "root_exec timeout job=$JOB_ID" >&2
    exit 124
  fi
  sleep 0.25
done
[ ! -s "$DIR/stdout.log" ] || cat "$DIR/stdout.log"
[ ! -s "$DIR/stderr.log" ] || cat "$DIR/stderr.log" >&2
rc="$(sed -n 's/.*"exit_code"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$DIR/result.json")"
[ -n "$rc" ] || rc=1
mv "$DIR" "$HISTORY/$JOB_ID"
exit "$rc"
