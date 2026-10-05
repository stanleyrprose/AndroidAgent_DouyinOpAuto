#!/bin/bash
set -u
PID=/opt/y700/runtime/health-loop.pid
LOG=/opt/y700/runtime/logs/health-loop.log
STATE_DIR=/opt/y700/runtime/state
CONNECTIVITY_STATE="$STATE_DIR/connectivity.json"
CF_PID=/opt/y700/runtime/cloudflared.pid
CF_RESTART=/opt/y700/workspaces/y700-agent/bootstrap/restart-cloudflared-y700.sh
CF_METRICS_URL="${Y700_CLOUDFLARED_METRICS_URL:-http://127.0.0.1:20241/metrics}"
NETWORK_STATUS=/opt/y700/workspaces/y700-agent/scripts/network-status.sh
BASE_BACKOFF_SEC="${Y700_CLOUDFLARED_BACKOFF_BASE_SEC:-60}"
MAX_BACKOFF_SEC="${Y700_CLOUDFLARED_BACKOFF_MAX_SEC:-900}"
DISCONNECTED_GRACE_CYCLES="${Y700_CLOUDFLARED_DISCONNECTED_GRACE_CYCLES:-2}"

mkdir -p "$(dirname "$LOG")" "$STATE_DIR"
echo $$ > "$PID"
trap 'rm -f "$PID"' EXIT

pid_matches() {
  local pid_file="$1" needle="$2"
  [ -s "$pid_file" ] || return 1
  local p
  p="$(cat "$pid_file" 2>/dev/null || true)"
  [ -n "$p" ] || return 1
  kill -0 "$p" 2>/dev/null || return 1
  [ -r "/proc/$p/cmdline" ] || return 1
  tr '\0' ' ' <"/proc/$p/cmdline" | grep -q "$needle"
}

tunnel_connection_count() {
  local metrics count
  metrics="$(curl -fsS --connect-timeout 2 --max-time 3 "$CF_METRICS_URL" 2>/dev/null || true)"
  count="$(printf '%s\n' "$metrics" | awk '$1=="cloudflared_tunnel_ha_connections" {print int($2); exit}')"
  if [[ "$count" =~ ^[0-9]+$ ]]; then
    echo "$count"
  else
    echo 0
  fi
}

write_connectivity_state() {
  local network="$1" tunnel_process="$2" connections="$3" remote_plane="$4" failures="$5" next_retry_epoch="$6"
  python3 - "$CONNECTIVITY_STATE.tmp" "$network" "$tunnel_process" "$connections" "$remote_plane" "$failures" "$next_retry_epoch" <<'PY'
import datetime, json, sys
out, network, tunnel_process, connections, remote_plane, failures, next_retry_epoch = sys.argv[1:]
next_retry = None
if next_retry_epoch not in {"", "0"}:
    try:
        next_retry = datetime.datetime.fromtimestamp(int(next_retry_epoch), datetime.timezone.utc).astimezone().isoformat()
    except Exception:
        next_retry = None
obj = {
    "updated_at": datetime.datetime.now().astimezone().isoformat(),
    "network": network,
    "tunnel_process": tunnel_process,
    "tunnel_connections": int(connections),
    "remote_plane": remote_plane,
    "restart_failures": int(failures),
    "next_retry_at": next_retry,
}
with open(out, "w") as f:
    json.dump(obj, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY
  mv "$CONNECTIVITY_STATE.tmp" "$CONNECTIVITY_STATE"
}

schedule_backoff() {
  failures=$((failures + 1))
  local shift=$((failures - 1))
  [ "$shift" -le 10 ] || shift=10
  local backoff=$((BASE_BACKOFF_SEC * (1 << shift)))
  [ "$backoff" -le "$MAX_BACKOFF_SEC" ] || backoff="$MAX_BACKOFF_SEC"
  next_retry_epoch=$((now + backoff))
  echo "$(date -Is) CLOUDFLARED_SELF_HEAL_FAILED failures=$failures backoff_sec=$backoff" >>"$LOG"
}

restart_cloudflared() {
  echo "$(date -Is) CLOUDFLARED_SELF_HEAL_START failures=$failures disconnected_cycles=$disconnected_cycles" >>"$LOG"
  if "$CF_RESTART" >>"$LOG" 2>&1; then
    failures=0
    next_retry_epoch=0
    disconnected_cycles=0
    echo "$(date -Is) CLOUDFLARED_SELF_HEAL_PROCESS_RESTARTED" >>"$LOG"
    return 0
  fi
  schedule_backoff
  return 1
}

failures=0
next_retry_epoch=0
disconnected_cycles=0
last_network=""

while true; do
  now="$(date +%s)"
  if network="$($NETWORK_STATUS 2>/dev/null)"; then
    case "$network" in
      ONLINE|ONLINE_ROUTE_ONLY) ;;
      *) network=ONLINE_ROUTE_ONLY ;;
    esac
  else
    network=UNKNOWN
  fi

  # The chroot may not expose Android's default route. Tunnel health is therefore
  # authoritative when edge connections exist. When they do not, UNKNOWN network
  # must not suppress recovery; bounded restart/backoff is safer for a mobile node.
  if pid_matches "$CF_PID" cloudflared; then
    tunnel_process=HEALTHY
    connections="$(tunnel_connection_count)"
  else
    tunnel_process=OFFLINE
    connections=0
  fi

  if [ "$connections" -gt 0 ]; then
    failures=0
    next_retry_epoch=0
    disconnected_cycles=0
    write_connectivity_state "$network" "$tunnel_process" "$connections" READY 0 0
  else
    disconnected_cycles=$((disconnected_cycles + 1))
    if [ "$last_network" = OFFLINE ] && [ "$network" != OFFLINE ]; then
      echo "$(date -Is) NETWORK_PATH_AVAILABLE mode=$network remote-plane-resume" >>"$LOG"
    fi
    if [ "$disconnected_cycles" -lt "$DISCONNECTED_GRACE_CYCLES" ]; then
      write_connectivity_state "$network" "$tunnel_process" 0 RECOVERING "$failures" "$next_retry_epoch"
    elif [ "$now" -ge "$next_retry_epoch" ]; then
      if restart_cloudflared; then
        tunnel_process=HEALTHY
        connections="$(tunnel_connection_count)"
        if [ "$connections" -gt 0 ]; then
          write_connectivity_state "$network" HEALTHY "$connections" READY 0 0
          echo "$(date -Is) CLOUDFLARED_SELF_HEAL_OK connections=$connections" >>"$LOG"
        else
          disconnected_cycles=1
          write_connectivity_state "$network" HEALTHY 0 RECOVERING 0 0
        fi
      else
        write_connectivity_state "$network" OFFLINE 0 DEGRADED "$failures" "$next_retry_epoch"
      fi
    else
      write_connectivity_state "$network" "$tunnel_process" 0 BACKOFF "$failures" "$next_retry_epoch"
    fi
  fi

  last_network="$network"
  /opt/y700/workspaces/y700-agent/scripts/health-check.sh >>"$LOG" 2>&1 || true
  sleep 60
done
