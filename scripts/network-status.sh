#!/bin/bash
set -u

# Y700 is a mobile node running inside Android's network namespace. Android
# policy routing can provide working Internet access without exposing a classic
# Linux default route to the chroot, so a real HTTP probe is authoritative when
# it succeeds. A visible default route remains a useful fallback when the probe
# endpoint itself is blocked.
PROBE_URL="${Y700_NETWORK_PROBE_URL:-https://www.cloudflare.com/cdn-cgi/trace}"
FALLBACK_PROBE_URL="${Y700_NETWORK_FALLBACK_PROBE_URL:-https://1.1.1.1/cdn-cgi/trace}"
CONNECT_TIMEOUT="${Y700_NETWORK_CONNECT_TIMEOUT_SEC:-3}"
MAX_TIME="${Y700_NETWORK_MAX_TIME_SEC:-5}"

has_default_route() {
  ip route show default 2>/dev/null | grep -q '^default '
}

http_probe_ok() {
  local url="${1:-$PROBE_URL}"
  curl -fsS --connect-timeout "$CONNECT_TIMEOUT" --max-time "$MAX_TIME" \
    "$url" >/dev/null 2>&1
}

if http_probe_ok; then
  echo ONLINE
  exit 0
fi

# A blocked probe host does not prove that the Android network is offline.
if [ "$FALLBACK_PROBE_URL" != "$PROBE_URL" ] && http_probe_ok "$FALLBACK_PROBE_URL"; then
  echo ONLINE
  exit 0
fi

if has_default_route; then
  echo ONLINE_ROUTE_ONLY
  exit 0
fi

echo OFFLINE
exit 1
