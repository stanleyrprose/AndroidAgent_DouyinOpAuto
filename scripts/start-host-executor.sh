#!/system/bin/sh
set -eu
PIDFILE=/data/local/y700-agent/runtime/host-executor.pid
LOG=/data/local/y700-agent/runtime/host-executor-launch.log
SCRIPT=/data/local/y700-agent/workspaces/y700-agent/bridge/host-executor.sh
LOCK=/data/local/y700-agent/runtime/host-executor.lock

if [ "${Y700_BRIDGE_ONESHOT:-1}" = 1 ]; then
  # Manual one-shot trigger, with no idle process left behind.
  Y700_BRIDGE_ONESHOT=1 exec /system/bin/sh "$SCRIPT" >>"$LOG" 2>&1
fi

pid_matches() {
  p="$1"
  [ -r "/proc/$p/cmdline" ] || return 1
  tr '\000' ' ' < "/proc/$p/cmdline" | grep -q '/bridge/host-executor.sh'
}

owner="$(cat "$LOCK/pid" 2>/dev/null || true)"
if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null && pid_matches "$owner"; then
  printf '%s\n' "$owner" >"$PIDFILE"
  echo "ALREADY_RUNNING pid=$owner"
  exit 0
fi

rm -rf "$LOCK" 2>/dev/null || true
# Explicit legacy rollback is the only path that starts persistent polling.
Y700_BRIDGE_ONESHOT=0 nohup /system/bin/sh "$SCRIPT" >>"$LOG" 2>&1 </dev/null &
child=$!
sleep 1
owner="$(cat "$LOCK/pid" 2>/dev/null || true)"
if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null && pid_matches "$owner"; then
  echo "STARTED pid=$owner"
  exit 0
fi
if kill -0 "$child" 2>/dev/null; then
  echo "STARTING pid=$child"
  exit 0
fi
echo "HOST_EXECUTOR_START_FAILED" >&2
exit 1
