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
DNS_OVERRIDE=/data/local/y700-linux/resolv.conf.override
DNS_MANAGED="$SHARED/workspaces/y700-agent/config/y700-resolv.conf"
DNS_LEGACY=/data/local/y700-linux/resolv.conf
if [ -s "$DNS_OVERRIDE" ]; then
  cat "$DNS_OVERRIDE" > "$ROOT/etc/resolv.conf"
elif [ -s "$DNS_MANAGED" ]; then
  cat "$DNS_MANAGED" > "$ROOT/etc/resolv.conf"
elif [ -s "$DNS_LEGACY" ]; then
  # Backward-compatible fallback only. A managed Git config wins by default so
  # stale host DNS from an old install cannot silently re-enter the chroot.
  cat "$DNS_LEGACY" > "$ROOT/etc/resolv.conf"
fi
