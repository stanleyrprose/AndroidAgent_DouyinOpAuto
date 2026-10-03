#!/system/bin/sh
set -eu
/data/local/y700-linux/mount.sh
ROOT=/data/local/y700-linux/rootfs
exec /system/bin/chroot "$ROOT" /usr/bin/env -i HOME=/root USER=root LOGNAME=root PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin LANG=C.UTF-8 TERM=xterm-256color "$@"
