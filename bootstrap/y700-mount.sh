#!/system/bin/sh
set -eu
ROOT=/data/local/y700-linux/rootfs
SHARED=/data/local/y700-agent
mkdir -p "$ROOT/proc" "$ROOT/sys" "$ROOT/dev/pts" "$ROOT/opt/y700"
mkdir -p "$SHARED/jobs" "$SHARED/runtime" "$SHARED/workspaces/y700-agent"
is_mounted() { grep -q " $1 " /proc/mounts; }
is_mounted "$ROOT/proc" || mount --bind /proc "$ROOT/proc"
is_mounted "$ROOT/sys" || mount --bind /sys "$ROOT/sys"
is_mounted "$ROOT/dev" || mount --bind /dev "$ROOT/dev"
is_mounted "$ROOT/dev/pts" || mount --bind /dev/pts "$ROOT/dev/pts"
is_mounted "$ROOT/opt/y700" || mount --bind "$SHARED" "$ROOT/opt/y700"
if [ -f /data/local/y700-linux/resolv.conf ]; then
  cat /data/local/y700-linux/resolv.conf > "$ROOT/etc/resolv.conf"
fi
