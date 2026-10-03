#!/bin/bash
set -euo pipefail
PID=/opt/y700/runtime/cloudflared.pid
LOG=/opt/y700/runtime/cloudflared.log
if [ -f "$PID" ]; then
  old="$(cat "$PID" 2>/dev/null || true)"
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then kill "$old" || true; sleep 1; fi
fi
nohup /root/.codexpro/bin/cloudflared --config /root/.cloudflared/config.yml tunnel run y700-codexpro >"$LOG" 2>&1 </dev/null &
echo $! > "$PID"
sleep 5
echo "PID=$(cat "$PID")"
tail -30 "$LOG"
