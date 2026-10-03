#!/system/bin/sh
LOG=/data/local/y700-agent/runtime/network-cycle-v03.log
echo "START $(date '+%Y-%m-%dT%H:%M:%S%z')" > "$LOG"
svc wifi disable
echo "WIFI_OFF $(date '+%Y-%m-%dT%H:%M:%S%z')" >> "$LOG"
sleep 12
svc wifi enable
echo "WIFI_ON $(date '+%Y-%m-%dT%H:%M:%S%z')" >> "$LOG"
