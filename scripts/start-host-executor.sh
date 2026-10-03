#!/system/bin/sh
PIDFILE=/data/local/y700-agent/runtime/host-executor.pid
LOG=/data/local/y700-agent/runtime/host-executor-launch.log
SCRIPT=/data/local/y700-agent/workspaces/y700-agent/bridge/host-executor.sh

pid_matches() {
  p="$1"
  needle="$2"
  [ -r "/proc/$p/cmdline" ] || return 1
  tr '\000' ' ' < "/proc/$p/cmdline" | grep -q "$needle"
}

if [ -f "$PIDFILE" ]; then
  old="$(cat "$PIDFILE" 2>/dev/null)"
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null && pid_matches "$old" "host-executor.sh"; then
    echo "ALREADY_RUNNING pid=$old"
    exit 0
  fi
fi

nohup /system/bin/sh "$SCRIPT" >>"$LOG" 2>&1 </dev/null &
echo $! > "$PIDFILE"
sleep 1
echo "STARTED pid=$(cat "$PIDFILE")"
