#!/system/bin/sh
BOOT=/data/local/y700-agent/runtime/boot-start.sh
if [ -x "$BOOT" ]; then
  nohup /system/bin/sh "$BOOT" >/dev/null 2>&1 &
fi
