#!/bin/bash
set -u
PID=/opt/y700/runtime/health-loop.pid
LOG=/opt/y700/runtime/logs/health-loop.log
CF_PID=/opt/y700/runtime/cloudflared.pid
CF_RESTART=/opt/y700/workspaces/y700-agent/bootstrap/restart-cloudflared-y700.sh

echo $$ > "$PID"
trap 'rm -f "$PID"' EXIT

pid_matches() {
  local pid_file="$1"
  local needle="$2"
  [ -s "$pid_file" ] || return 1
  local p
  p="$(cat "$pid_file" 2>/dev/null || true)"
  [ -n "$p" ] || return 1
  kill -0 "$p" 2>/dev/null || return 1
  [ -r "/proc/$p/cmdline" ] || return 1
  tr '\0' ' ' <"/proc/$p/cmdline" | grep -q "$needle"
}

while true; do
  if ! pid_matches "$CF_PID" cloudflared; then
    echo "$(date -Is) CLOUDFLARED_SELF_HEAL_START" >>"$LOG"
    if "$CF_RESTART" >>"$LOG" 2>&1; then
      echo "$(date -Is) CLOUDFLARED_SELF_HEAL_OK" >>"$LOG"
    else
      echo "$(date -Is) CLOUDFLARED_SELF_HEAL_FAILED" >>"$LOG"
    fi
  fi

  /opt/y700/workspaces/y700-agent/scripts/health-check.sh >>"$LOG" 2>&1 || true
  sleep 60
done
