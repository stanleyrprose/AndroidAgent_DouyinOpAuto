#!/system/bin/sh
set -eu
PIDFILE=/data/local/y700-agent/runtime/host-executor.pid
LOG=/data/local/y700-agent/runtime/host-executor-launch.log
SCRIPT=/data/local/y700-agent/workspaces/y700-agent/bridge/host-executor.sh
old="$(cat "$PIDFILE" 2>/dev/null || true)"
[ -n "$old" ] || { echo "NO_OLD_PID"; exit 2; }
nohup /system/bin/sh -c "
  sleep 2
  kill $old 2>/dev/null || true
  sleep 1
  nohup /system/bin/sh '$SCRIPT' >>'$LOG' 2>&1 </dev/null &
  echo \$! > '$PIDFILE'
" >/dev/null 2>&1 &
echo "RESTART_SCHEDULED old=$old"
