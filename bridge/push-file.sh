#!/bin/bash
set -euo pipefail
[ "$#" -eq 2 ] || { echo "usage: push-file.sh <chroot-src> <android-dst>" >&2; exit 64; }
src="$1"; dst="$2"
[ -f "$src" ] || { echo "source not found: $src" >&2; exit 66; }
tmp="/opt/y700/runtime/tmp/push-$(date +%s)-$$"
cp "$src" "$tmp"
qtmp=$(printf '%q' "/data/local/y700-agent/runtime/tmp/$(basename "$tmp")")
qdst=$(printf '%q' "$dst")
/opt/y700/workspaces/y700-agent/bridge/root-exec.sh "mkdir -p \$(dirname $qdst); cp $qtmp $qdst; stat -c '%s %a %U:%G %n' $qdst 2>/dev/null || ls -l $qdst"
rm -f "$tmp"
