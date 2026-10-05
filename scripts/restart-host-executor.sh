#!/system/bin/sh
set -eu
PIDFILE=/data/local/y700-agent/runtime/host-executor.pid
LOG=/data/local/y700-agent/runtime/host-executor-launch.log
SCRIPT=/data/local/y700-agent/workspaces/y700-agent/bridge/host-executor.sh

old="$(cat "$PIDFILE" 2>/dev/null || true)"
nohup /system/bin/sh -c '
  sleep 2
  self=$$
  for proc in /proc/[0-9]*; do
    pid=${proc#/proc/}
    [ "$pid" = "$self" ] && continue
    [ -r "$proc/cmdline" ] || continue
    cmd=$(tr "\000" " " <"$proc/cmdline" 2>/dev/null || true)
    case "$cmd" in
      *"/bridge/host-executor.sh"*) kill "$pid" 2>/dev/null || true ;;
    esac
  done
  sleep 1
  rm -rf /data/local/y700-agent/runtime/host-executor.lock 2>/dev/null || true
  nohup /system/bin/sh /data/local/y700-agent/workspaces/y700-agent/bridge/host-executor.sh \
    >>/data/local/y700-agent/runtime/host-executor-launch.log 2>&1 </dev/null &
' >/dev/null 2>&1 &
echo "RESTART_SCHEDULED old=${old:-none}"
