#!/bin/bash
set -euo pipefail
PID=/opt/y700/runtime/health-loop.pid
VERSION=/opt/y700/runtime/state/health-loop.version
HEARTBEAT=/opt/y700/runtime/state/health-loop.heartbeat
HEARTBEAT_STALE_SEC="${Y700_HEALTH_LOOP_HEARTBEAT_STALE_SEC:-35}"
SCRIPT=/opt/y700/workspaces/y700-agent/scripts/health-loop.sh
CURRENT_SHA="$(sha256sum "$SCRIPT" 2>/dev/null | awk '{print $1}')"
process_matches() {
  local p="$1"
  case "$p" in
    ''|*[!0-9]*) return 1 ;;
  esac
  [ -r "/proc/$p/cmdline" ] || return 1
  tr '\0' ' ' <"/proc/$p/cmdline" 2>/dev/null | grep -q '/scripts/health-loop.sh'
}

monotonic_sec() {
  awk '{print int($1)}' /proc/uptime 2>/dev/null || date +%s
}

version_matches() {
  local p="$1" version_pid version_sha
  [ -n "$CURRENT_SHA" ] || return 1
  [ -r "$VERSION" ] || return 1
  read -r version_pid version_sha <"$VERSION" || return 1
  [ "$version_pid" = "$p" ] && [ "$version_sha" = "$CURRENT_SHA" ]
}

heartbeat_fresh() {
  local p="$1" hb_pid hb_mono hb_sha now age
  [ -r "$HEARTBEAT" ] || return 1
  read -r hb_pid hb_mono hb_sha <"$HEARTBEAT" || return 1
  [ "$hb_pid" = "$p" ] && [ "$hb_sha" = "$CURRENT_SHA" ] || return 1
  case "$hb_mono" in ''|*[!0-9]*) return 1 ;; esac
  now="$(monotonic_sec)"
  case "$now" in ''|*[!0-9]*) return 1 ;; esac
  [ "$now" -ge "$hb_mono" ] || return 1
  age=$((now - hb_mono))
  [ "$age" -le "$HEARTBEAT_STALE_SEC" ]
}

stop_stale() {
  local p="$1" i=0
  echo "STALE_HEALTH_LOOP pid=$p expected_sha=$CURRENT_SHA"
  kill "$p" 2>/dev/null || true
  while kill -0 "$p" 2>/dev/null && [ "$i" -lt 50 ]; do
    i=$((i + 1))
    sleep 0.1
  done
  if kill -0 "$p" 2>/dev/null; then
    echo "STALE_HEALTH_LOOP_WONT_EXIT pid=$p" >&2
    return 75
  fi
  rm -f "$PID"
  return 0
}

if [ -s "$PID" ]; then
  p=$(cat "$PID" 2>/dev/null || true)
  if process_matches "$p"; then
    if version_matches "$p" && heartbeat_fresh "$p"; then
      echo "ALREADY_RUNNING pid=$p sha=$CURRENT_SHA"
      exit 0
    fi
    stop_stale "$p"
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
  if version_matches "$found" && heartbeat_fresh "$found"; then
    printf '%s\n' "$found" >"$PID.tmp.$$"
    mv "$PID.tmp.$$" "$PID"
    echo "RECOVERED_RUNNING pid=$found sha=$CURRENT_SHA"
    exit 0
  fi
  stop_stale "$found"
fi

nohup "$SCRIPT" >/opt/y700/runtime/logs/health-loop-launch.log 2>&1 </dev/null &
sleep 1
p="$(cat "$PID" 2>/dev/null || true)"
if ! process_matches "$p" || ! version_matches "$p"; then
  echo "HEALTH_LOOP_START_UNVERIFIED pid=${p:-none} expected_sha=$CURRENT_SHA" >&2
  exit 76
fi
echo "STARTED pid=$p sha=$CURRENT_SHA"
