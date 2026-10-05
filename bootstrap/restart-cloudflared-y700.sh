#!/bin/bash
set -euo pipefail
PID=/opt/y700/runtime/cloudflared.pid
LOG=/opt/y700/runtime/cloudflared.log
if [ -f "$PID" ]; then
  old="$(cat "$PID" 2>/dev/null || true)"
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then kill "$old" || true; sleep 1; fi
fi
nohup /root/.codexpro/bin/cloudflared --config /root/.cloudflared/config.yml --metrics 127.0.0.1:20241 tunnel run y700-codexpro >"$LOG" 2>&1 </dev/null &
new_pid=$!
echo "$new_pid" > "$PID"
sleep 5
if ! kill -0 "$new_pid" 2>/dev/null || ! tr '\0' ' ' <"/proc/$new_pid/cmdline" 2>/dev/null | grep -q cloudflared; then
  echo "CLOUDFLARED_START_FAILED pid=$new_pid" >&2
  tail -30 "$LOG" >&2 || true
  exit 1
fi
echo "PID=$new_pid"
tail -30 "$LOG"
