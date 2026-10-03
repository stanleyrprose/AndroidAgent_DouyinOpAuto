#!/bin/bash
set -euo pipefail
PID=/opt/y700/runtime/health-loop.pid
SCRIPT=/opt/y700/workspaces/y700-agent/scripts/health-loop.sh
if [ -s "$PID" ]; then
  p=$(cat "$PID" 2>/dev/null || true)
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null && tr '\0' ' ' <"/proc/$p/cmdline" | grep -q health-loop.sh; then
    echo "ALREADY_RUNNING pid=$p"
    exit 0
  fi
fi
nohup "$SCRIPT" >/opt/y700/runtime/logs/health-loop-launch.log 2>&1 </dev/null &
sleep 1
echo "STARTED pid=$(cat "$PID")"
