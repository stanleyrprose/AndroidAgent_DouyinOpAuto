#!/bin/bash
set -u
PID=/opt/y700/runtime/health-loop.pid
LOG=/opt/y700/runtime/logs/health-loop.log
echo $$ > "$PID"
trap 'rm -f "$PID"' EXIT
while true; do
  /opt/y700/workspaces/y700-agent/scripts/health-check.sh >>"$LOG" 2>&1 || true
  sleep 60
done
