#!/bin/bash
set -euo pipefail
PID=/opt/y700/runtime/health-loop.pid
SCRIPT=/opt/y700/workspaces/y700-agent/scripts/health-loop.sh
process_matches() {
  local p="$1"
  case "$p" in
    ''|*[!0-9]*) return 1 ;;
  esac
  [ -r "/proc/$p/cmdline" ] || return 1
  tr '\0' ' ' <"/proc/$p/cmdline" 2>/dev/null | grep -q '/scripts/health-loop.sh'
}

if [ -s "$PID" ]; then
  p=$(cat "$PID" 2>/dev/null || true)
  if process_matches "$p"; then
    echo "ALREADY_RUNNING pid=$p"
    exit 0
  fi
fi

found=""
for proc in /proc/[0-9]*/cmdline; do
  [ -r "$proc" ] || continue
  p="${proc#/proc/}"
  p="${p%/cmdline}"
  if process_matches "$p"; then
    if [ -n "$found" ] && [ "$found" != "$p" ]; then
      echo "MULTIPLE_HEALTH_LOOPS pids=$found,$p" >&2
      exit 75
    fi
    found="$p"
  fi
done
if [ -n "$found" ]; then
  printf '%s\n' "$found" >"$PID.tmp.$$"
  mv "$PID.tmp.$$" "$PID"
  echo "RECOVERED_RUNNING pid=$found"
  exit 0
fi

nohup "$SCRIPT" >/opt/y700/runtime/logs/health-loop-launch.log 2>&1 </dev/null &
sleep 1
echo "STARTED pid=$(cat "$PID")"
