#!/bin/bash
set -euo pipefail

AUTH_FILE="${CODEXPRO_AUTH_FILE:-/root/.config/codexpro/http-token}"
CP_PID=/opt/y700/runtime/codexpro.pid
CF_PID=/opt/y700/runtime/cloudflared.pid
CF_LOG=/opt/y700/runtime/cloudflared.log

pid_matches() {
  local p="$1"
  local needle="$2"
  [ -r "/proc/$p/cmdline" ] || return 1
  tr '\0' ' ' < "/proc/$p/cmdline" | grep -q "$needle"
}

if [ ! -s "$AUTH_FILE" ]; then
  echo "Missing local CodexPro auth file: $AUTH_FILE" >&2
  exit 2
fi
chmod 600 "$AUTH_FILE"

if [ -f "$CP_PID" ]; then
  old="$(cat "$CP_PID" 2>/dev/null || true)"
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null && pid_matches "$old" "codexpro"; then
    kill "$old" || true
    sleep 1
  fi
fi

nohup codexpro start \
  --root /opt/y700/workspaces/y700-agent \
  --allow-root /opt/y700/workspaces \
  --allow-root / \
  --host 127.0.0.1 \
  --port 8788 \
  --bash full \
  --write workspace \
  --tool-mode full \
  --tunnel none \
  --token-file "$AUTH_FILE" \
  --headless \
  --no-profile \
  >/opt/y700/runtime/codexpro.log 2>&1 </dev/null &
echo $! > "$CP_PID"
sleep 2

http_code="$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8788/healthz || true)"
if [ "$http_code" != "401" ] && [ "$http_code" != "200" ]; then
  echo "CodexPro local health endpoint unavailable (HTTP $http_code)" >&2
  exit 3
fi

if [ -f "$CF_PID" ]; then
  old="$(cat "$CF_PID" 2>/dev/null || true)"
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null && pid_matches "$old" "cloudflared"; then
    kill "$old" || true
    sleep 1
  fi
fi

cf_ok=0
attempt=1
while [ "$attempt" -le 12 ]; do
  echo "=== cloudflared attempt=$attempt $(date -Is) ===" >> "$CF_LOG"
  nohup /root/.codexpro/bin/cloudflared \
    --config /root/.cloudflared/config.yml \
    --metrics 127.0.0.1:20241 \
    tunnel run y700-codexpro \
    >>"$CF_LOG" 2>&1 </dev/null &
  cf_pid=$!
  echo "$cf_pid" > "$CF_PID"
  sleep 5

  if kill -0 "$cf_pid" 2>/dev/null && pid_matches "$cf_pid" "cloudflared"; then
    cf_ok=1
    break
  fi

  sleep $((attempt * 2))
  attempt=$((attempt + 1))
done

if [ "$cf_ok" -ne 1 ]; then
  echo "CLOUDFLARED_START_FAILED" >&2
  exit 4
fi

echo "CODEXPRO_PID=$(cat "$CP_PID")"
echo "CLOUDFLARED_PID=$(cat "$CF_PID")"
