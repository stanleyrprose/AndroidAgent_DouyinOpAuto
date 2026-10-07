#!/bin/bash
set -euo pipefail
PID=/opt/y700/runtime/cloudflared.pid
LOG=/opt/y700/runtime/cloudflared.log
STOP_TERM_ATTEMPTS="${Y700_CLOUDFLARED_STOP_TERM_ATTEMPTS:-20}"
STOP_KILL_ATTEMPTS="${Y700_CLOUDFLARED_STOP_KILL_ATTEMPTS:-20}"
STOP_POLL_SEC="${Y700_CLOUDFLARED_STOP_POLL_SEC:-0.1}"

pid_is_cloudflared() {
  local p="$1" cmdline
  case "$p" in
    ''|*[!0-9]*) return 1 ;;
  esac
  [ -r "/proc/$p/cmdline" ] || return 1
  cmdline="$(tr '\0' ' ' <"/proc/$p/cmdline" 2>/dev/null || true)"
  case "$cmdline" in
    *"/root/.codexpro/bin/cloudflared "*"tunnel run y700-codexpro"*) return 0 ;;
    *) return 1 ;;
  esac
}

old_still_cloudflared() {
  local p="$1"
  kill -0 "$p" 2>/dev/null && pid_is_cloudflared "$p"
}

stop_old_cloudflared() {
  local old="" i=0
  [ -f "$PID" ] || return 0
  old="$(cat "$PID" 2>/dev/null || true)"
  [ -n "$old" ] || return 0

  if ! kill -0 "$old" 2>/dev/null; then
    return 0
  fi

  if ! pid_is_cloudflared "$old"; then
    echo "CLOUDFLARED_PID_MISMATCH pid=$old refusing_kill" >&2
    return 0
  fi

  kill -TERM "$old" 2>/dev/null || true
  while old_still_cloudflared "$old" && [ "$i" -lt "$STOP_TERM_ATTEMPTS" ]; do
    i=$((i + 1))
    sleep "$STOP_POLL_SEC"
  done

  if old_still_cloudflared "$old"; then
    echo "$(date -Is) CLOUDFLARED_STOP_ESCALATE pid=$old signal=KILL" >>"$LOG"
    kill -KILL "$old" 2>/dev/null || true
    i=0
    while old_still_cloudflared "$old" && [ "$i" -lt "$STOP_KILL_ATTEMPTS" ]; do
      i=$((i + 1))
      sleep "$STOP_POLL_SEC"
    done
  fi

  if old_still_cloudflared "$old"; then
    echo "CLOUDFLARED_STOP_FAILED pid=$old" >&2
    return 2
  fi

  echo "$(date -Is) CLOUDFLARED_OLD_STOPPED pid=$old" >>"$LOG"
}

stop_old_cloudflared

nohup /root/.codexpro/bin/cloudflared --config /root/.cloudflared/config.yml --metrics 127.0.0.1:20241 tunnel run y700-codexpro >"$LOG" 2>&1 </dev/null &
new_pid=$!
echo "$new_pid" > "$PID"
sleep 5
if ! kill -0 "$new_pid" 2>/dev/null || ! pid_is_cloudflared "$new_pid"; then
  echo "CLOUDFLARED_START_FAILED pid=$new_pid" >&2
  tail -30 "$LOG" >&2 || true
  exit 1
fi
echo "PID=$new_pid"
tail -30 "$LOG"
