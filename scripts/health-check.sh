#!/bin/bash
set -euo pipefail
STATE_DIR=/opt/y700/runtime/state
OUT="$STATE_DIR/health.json"
TMP="$OUT.tmp"
mkdir -p "$STATE_DIR"

status_pid() {
  local f="$1" needle="$2"
  if [ -s "$f" ]; then
    local p
    p=$(cat "$f" 2>/dev/null || true)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null && tr '\0' ' ' <"/proc/$p/cmdline" 2>/dev/null | grep -q "$needle"; then
      echo HEALTHY
      return
    fi
  fi
  echo OFFLINE
}

codex=$(status_pid /opt/y700/runtime/codexpro.pid codexpro)
tunnel=$(status_pid /opt/y700/runtime/cloudflared.pid cloudflared)
bridge=$(status_pid /opt/y700/runtime/host-executor.pid host-executor.sh)

if [ -w /opt/y700/jobs ]; then jobs=HEALTHY; else jobs=BLOCKED; fi

set +e
disk_json=$(/opt/y700/workspaces/y700-agent/scripts/disk-guard.sh 2>/dev/null)
disk_rc=$?
set -e
[ -n "$disk_json" ] || disk_json='{"status":"UNKNOWN"}'

publisher=IDLE
if [ -s /opt/y700/runtime/state/publisher.json ]; then
  publisher=$(python3 - <<'PY'
import json
try:
    d=json.load(open('/opt/y700/runtime/state/publisher.json'))
    print(d.get('status','UNKNOWN'))
except Exception:
    print('UNKNOWN')
PY
)
fi

temp_tenths=$(/opt/y700/workspaces/y700-agent/bridge/root-exec.sh "dumpsys battery | sed -n 's/^[[:space:]]*temperature: //p' | head -1" 2>/dev/null | tail -1 || true)
if [[ "$temp_tenths" =~ ^[0-9]+$ ]]; then
  temp_c=$(python3 -c "print(round($temp_tenths/10,1))")
else
  temp_c=null
fi

overall=HEALTHY
if [ "$codex" = OFFLINE ] || [ "$bridge" = OFFLINE ] || [ "$jobs" = BLOCKED ]; then overall=BLOCKED
elif [ "$tunnel" = OFFLINE ] || [ "$disk_rc" -ne 0 ]; then overall=DEGRADED
fi

python3 - "$TMP" "$overall" "$codex" "$tunnel" "$bridge" "$jobs" "$publisher" "$temp_c" "$disk_json" <<'PY'
import json,sys,datetime
out,overall,codex,tunnel,bridge,jobs,publisher,temp,disk=sys.argv[1:]
obj={
 "updated_at":datetime.datetime.now().astimezone().isoformat(),
 "overall":overall,
 "codexpro":codex,
 "tunnel":tunnel,
 "android_bridge":bridge,
 "job_directory":jobs,
 "publisher":publisher,
 "battery_temperature_c":None if temp=="null" else float(temp),
 "disk":json.loads(disk),
}
with open(out,'w') as f:
    json.dump(obj,f,ensure_ascii=False,indent=2)
    f.write("\n")
PY
mv "$TMP" "$OUT"
cat "$OUT"
