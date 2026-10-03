#!/bin/bash
set -euo pipefail
MIN_FREE_KB="${Y700_MIN_FREE_KB:-5242880}"
free_kb="$(df -Pk /opt/y700 | awk 'NR==2 {print $4}')"
if [ -z "$free_kb" ]; then
  echo "DISK_UNKNOWN" >&2
  exit 2
fi
if [ "$free_kb" -lt "$MIN_FREE_KB" ]; then
  echo "LOW_DISK free_kb=$free_kb min_free_kb=$MIN_FREE_KB" >&2
  exit 75
fi
echo "INTAKE_OK free_kb=$free_kb min_free_kb=$MIN_FREE_KB"
