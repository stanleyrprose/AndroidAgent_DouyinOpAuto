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
/data/local/y700-agent/runtime/start-host-executor.sh
/data/local/y700-linux/exec.sh /bin/bash /opt/y700/runtime/y700-prod-init.sh
/data/local/y700-linux/exec.sh /bin/bash /opt/y700/workspaces/y700-agent/scripts/start-sshd.sh
/data/local/y700-linux/exec.sh /bin/bash /opt/y700/workspaces/y700-agent/scripts/start-health-loop.sh

echo "BOOT_START_OK"
