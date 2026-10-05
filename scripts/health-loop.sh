#!/bin/bash
set -u
PID=/opt/y700/runtime/health-loop.pid
LOG=/opt/y700/runtime/logs/health-loop.log
STATE_DIR=/opt/y700/runtime/state
CONNECTIVITY_STATE="$STATE_DIR/connectivity.json"
CF_PID=/opt/y700/runtime/cloudflared.pid
CF_RESTART=/opt/y700/workspaces/y700-agent/bootstrap/restart-cloudflared-y700.sh
NETWORK_STATUS=/opt/y700/workspaces/y700-agent/scripts/network-status.sh
BASE_BACKOFF_SEC="${Y700_CLOUDFLARED_BACKOFF_BASE_SEC:-60}"
MAX_BACKOFF_SEC="${Y700_CLOUDFLARED_BACKOFF_MAX_SEC:-900}"

mkdir -p "$(dirname "$LOG")" "$STATE_DIR"
echo $$ > "$PID"
trap 'rm -f "$PID"' EXIT

pid_matches() {
  local pid_file="$1"
  local needle="$2"
  [ -s "$pid_file" ] || return 1
  local p
  p="$(cat "$pid_file" 2>/dev/null || true)"
  [ -n "$p" ] || return 1
  kill -0 "$p" 2>/dev/null || return 1
  [ -r "/proc/$p/cmdline" ] || return 1
  tr '\0' ' ' <"/proc/$p/cmdline" | grep -q "$needle"
}

write_connectivity_state() {
  local network="$1" tunnel_process="$2" remote_plane="$3" failures="$4" next_retry_epoch="$5"
  python3 - "$CONNECTIVITY_STATE.tmp" "$network" "$tunnel_process" "$remote_plane" "$failures" "$next_retry_epoch" <<'PY'
import datetime, json, sys
out, network, tunnel_process, remote_plane, failures, next_retry_epoch = sys.argv[1:]
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

failures=0
next_retry_epoch=0
last_network=""

while true; do
  now="$(date +%s)"
  if network="$($NETWORK_STATUS 2>/dev/null)"; then
    network=ONLINE
  else
    network=OFFLINE
  fi

  if [ "$network" = OFFLINE ]; then
    if [ "$last_network" != OFFLINE ]; then
      echo "$(date -Is) NETWORK_OFFLINE remote-plane-suspended" >>"$LOG"
    fi
    failures=0
    next_retry_epoch=0
    if pid_matches "$CF_PID" cloudflared; then
      tunnel_process=HEALTHY
    else
      tunnel_process=OFFLINE
    fi
    write_connectivity_state OFFLINE "$tunnel_process" SUSPENDED_NO_NETWORK 0 0
  else
    if [ "$last_network" = OFFLINE ]; then
      echo "$(date -Is) NETWORK_ONLINE remote-plane-resume" >>"$LOG"
    fi

    if pid_matches "$CF_PID" cloudflared; then
      failures=0
      next_retry_epoch=0
      write_connectivity_state ONLINE HEALTHY READY 0 0
    elif [ "$now" -ge "$next_retry_epoch" ]; then
      echo "$(date -Is) CLOUDFLARED_SELF_HEAL_START failures=$failures" >>"$LOG"
      if "$CF_RESTART" >>"$LOG" 2>&1; then
        failures=0
        next_retry_epoch=0
        echo "$(date -Is) CLOUDFLARED_SELF_HEAL_OK" >>"$LOG"
        write_connectivity_state ONLINE HEALTHY READY 0 0
      else
        failures=$((failures + 1))
        shift=$((failures - 1))
        [ "$shift" -le 10 ] || shift=10
        backoff=$((BASE_BACKOFF_SEC * (1 << shift)))
        [ "$backoff" -le "$MAX_BACKOFF_SEC" ] || backoff="$MAX_BACKOFF_SEC"
        next_retry_epoch=$((now + backoff))
        echo "$(date -Is) CLOUDFLARED_SELF_HEAL_FAILED failures=$failures backoff_sec=$backoff" >>"$LOG"
        write_connectivity_state ONLINE OFFLINE DEGRADED "$failures" "$next_retry_epoch"
      fi
    else
      write_connectivity_state ONLINE OFFLINE BACKOFF "$failures" "$next_retry_epoch"
    fi
  fi

  last_network="$network"
  /opt/y700/workspaces/y700-agent/scripts/health-check.sh >>"$LOG" 2>&1 || true
  sleep 60
done
