#!/bin/bash
set -euo pipefail
/opt/y700/workspaces/y700-agent/scripts/disk-guard.sh >/tmp/y700-disk-preflight.json
temp=$(/opt/y700/workspaces/y700-agent/bridge/root-exec.sh "dumpsys battery | sed -n 's/^[[:space:]]*temperature: //p' | head -1" | tail -1)
max_temp_tenths=${Y700_MAX_TEMP_TENTHS:-450}
if [[ "$temp" =~ ^[0-9]+$ ]] && [ "$temp" -ge "$max_temp_tenths" ]; then
  echo "THERMAL_BLOCK temperature_tenths=$temp max_temp_tenths=$max_temp_tenths" >&2
  exit 4
fi
/opt/y700/workspaces/y700-agent/bridge/androidctl.sh wake >/dev/null
/opt/y700/workspaces/y700-agent/bridge/androidctl.sh unlock >/dev/null
echo "PREFLIGHT_PASS"
