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

count_host_executors() {
  local count=0 f arg
  for f in /proc/[0-9]*/cmdline; do
    [ -r "$f" ] || continue
    while IFS= read -r arg; do
      case "$arg" in
        */bridge/host-executor.sh)
          count=$((count + 1))
          break
          ;;
      esac
    done < <(tr '\0' '\n' <"$f" 2>/dev/null || true)
  done
  echo "$count"
}

codex=$(status_pid /opt/y700/runtime/codexpro.pid codexpro)
tunnel=$(status_pid /opt/y700/runtime/cloudflared.pid cloudflared)
bridge=$(status_pid /opt/y700/runtime/host-executor.pid host-executor.sh)
bridge_instances=$(count_host_executors)

network=UNKNOWN
remote_plane=UNKNOWN
tunnel_connections=0
if [ -s /opt/y700/runtime/state/connectivity.json ]; then
  read -r network remote_plane tunnel_connections < <(python3 - <<'PY2'
import json
try:
    d=json.load(open('/opt/y700/runtime/state/connectivity.json'))
    print(d.get('network','UNKNOWN'), d.get('remote_plane','UNKNOWN'), d.get('tunnel_connections',0))
except Exception:
    print('UNKNOWN UNKNOWN 0')
PY2
  )
fi
if [ "$network" = UNKNOWN ]; then
  if /opt/y700/workspaces/y700-agent/scripts/network-status.sh >/dev/null 2>&1; then
    network=ONLINE
  else
    network=OFFLINE
  fi
fi
if [ "$remote_plane" = UNKNOWN ]; then
  if [ "$network" = OFFLINE ]; then
    remote_plane=SUSPENDED_NO_NETWORK
  elif [ "$codex" = HEALTHY ] && [ "$tunnel" = HEALTHY ]; then
    remote_plane=READY
  else
    remote_plane=DEGRADED
  fi
fi

if [ -w /opt/y700/jobs ]; then jobs=HEALTHY; else jobs=BLOCKED; fi

production_sot=UNKNOWN
set +e
production_sot=$(/opt/y700/workspaces/y700-agent/scripts/production-sot-status.sh 2>/dev/null)
production_sot_rc=$?
set -e
case "$production_sot" in
  HEALTHY|DRIFT|UNKNOWN) ;;
  *) production_sot=UNKNOWN ;;
esac

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

temp_tenths=""
for temp_path in /sys/class/power_supply/battery/temp /sys/class/power_supply/bms/temp; do
  if [ -r "$temp_path" ]; then
    temp_tenths="$(cat "$temp_path" 2>/dev/null || true)"
    [ -n "$temp_tenths" ] && break
  fi
done
if [[ "$temp_tenths" =~ ^[0-9]+$ ]] && [ "$temp_tenths" -le 1000 ]; then
  temp_c=$(python3 -c "print(round($temp_tenths/10,1))")
else
  temp_c=null
fi

overall=HEALTHY
if [ "$bridge" = OFFLINE ] || [ "$jobs" = BLOCKED ]; then overall=BLOCKED
elif [ "$disk_rc" -ne 0 ]; then overall=DEGRADED
elif [ "$production_sot" = DRIFT ]; then overall=DEGRADED
elif [ "$bridge_instances" -ne 1 ]; then overall=DEGRADED
elif [ "$network" = ONLINE ] && { [ "$codex" = OFFLINE ] || [ "$tunnel" = OFFLINE ]; }; then overall=DEGRADED
fi

python3 - "$TMP" "$overall" "$codex" "$tunnel" "$bridge" "$jobs" "$publisher" "$temp_c" "$disk_json" "$network" "$remote_plane" "$tunnel_connections" "$production_sot" "$bridge_instances" <<'PY'
import json,sys,datetime
out,overall,codex,tunnel,bridge,jobs,publisher,temp,disk,network,remote_plane,tunnel_connections,production_sot,bridge_instances=sys.argv[1:]
obj={
 "updated_at":datetime.datetime.now().astimezone().isoformat(),
 "overall":overall,
 "network":network,
 "remote_plane":remote_plane,
 "tunnel_connections":int(tunnel_connections),
 "codexpro":codex,
 "tunnel":tunnel,
 "android_bridge":bridge,
 "android_bridge_instances":int(bridge_instances),
 "job_directory":jobs,
 "production_sot":production_sot,
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
