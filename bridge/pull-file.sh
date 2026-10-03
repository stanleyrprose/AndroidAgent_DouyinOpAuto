#!/bin/bash
set -euo pipefail
[ "$#" -eq 2 ] || { echo "usage: pull-file.sh <android-src> <chroot-dst>" >&2; exit 64; }
src="$1"; dst="$2"
name="pull-$(date +%s)-$$"
host_tmp="/data/local/y700-agent/runtime/tmp/$name"
chroot_tmp="/opt/y700/runtime/tmp/$name"
qsrc=$(printf '%q' "$src")
qtmp=$(printf '%q' "$host_tmp")
/opt/y700/workspaces/y700-agent/bridge/root-exec.sh "cp $qsrc $qtmp; chmod 600 $qtmp"
mkdir -p "$(dirname "$dst")"
cp "$chroot_tmp" "$dst"
rm -f "$chroot_tmp"
stat -c '%s %a %U:%G %n' "$dst"
