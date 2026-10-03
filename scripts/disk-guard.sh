#!/bin/bash
set -euo pipefail
TARGET=${1:-/opt/y700/media}
MIN_FREE_MB=${Y700_MIN_FREE_MB:-5120}
read -r _ blocks used avail pct _ < <(df -Pk "$TARGET" | tail -1)
free_mb=$((avail / 1024))
used_pct=${pct%%%}
free_pct=$((100 - used_pct))
status=PASS
rc=0
if [ "$free_mb" -lt "$MIN_FREE_MB" ] || [ "$free_pct" -lt 5 ]; then
  status=BLOCKED
  rc=3
fi
printf '{"status":"%s","target":"%s","free_mb":%d,"free_percent":%d,"min_free_mb":%d}\n' "$status" "$TARGET" "$free_mb" "$free_pct" "$MIN_FREE_MB"
exit "$rc"
