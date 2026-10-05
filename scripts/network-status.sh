#!/bin/bash
set -u

# Y700 is a mobile node. A default route is the primary signal that the device
# currently has a network path worth attempting remote-plane recovery on.
# HTTP reachability is advisory only because some Myanmar networks may block or
# interfere with individual probe endpoints while Cloudflare Tunnel still works.
PROBE_URL="${Y700_NETWORK_PROBE_URL:-https://www.cloudflare.com/cdn-cgi/trace}"
CONNECT_TIMEOUT="${Y700_NETWORK_CONNECT_TIMEOUT_SEC:-3}"
MAX_TIME="${Y700_NETWORK_MAX_TIME_SEC:-5}"

has_default_route() {
  ip route show default 2>/dev/null | grep -q '^default '
}

http_probe_ok() {
  curl -fsS --connect-timeout "$CONNECT_TIMEOUT" --max-time "$MAX_TIME" \
    "$PROBE_URL" >/dev/null 2>&1
}

if has_default_route; then
  if http_probe_ok; then
    echo ONLINE
  else
    echo ONLINE_ROUTE_ONLY
  fi
  exit 0
fi

echo OFFLINE
exit 1
