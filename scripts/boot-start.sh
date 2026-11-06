#!/system/bin/sh
LOG=/data/local/y700-agent/runtime/boot-start.log
mkdir -p /data/local/y700-agent/runtime
exec >>"$LOG" 2>&1

echo "=== boot-start $(date '+%Y-%m-%dT%H:%M:%S%z') pid=$$ ==="

i=0
while [ "$(getprop sys.boot_completed)" != "1" ] && [ "$i" -lt 120 ]; do
  sleep 2
  i=$((i + 1))
done

if [ "$(getprop sys.boot_completed)" != "1" ]; then
  echo "BOOT_COMPLETED_TIMEOUT"
  exit 1
fi

/data/local/y700-linux/mount.sh
# The bridge is on-demand: no resident executor or health-loop at boot.
# Android can suspend normally; existing cloudflared/CodexPro processes recover
# connectivity on screen wake, and the next bridge request launches one shot.
/data/local/y700-linux/exec.sh /bin/bash /opt/y700/workspaces/y700-agent/scripts/start-prod-runtime.sh
/data/local/y700-linux/exec.sh /bin/bash /opt/y700/workspaces/y700-agent/scripts/start-sshd.sh

echo "BOOT_START_OK"
