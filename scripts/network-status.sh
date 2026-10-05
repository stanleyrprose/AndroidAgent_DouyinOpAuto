#!/bin/bash
set -u

# Internet reachability for the remote development/control plane. Cloudflare is
# intentional here: if its edge cannot be reached, the named tunnel cannot be
# useful even if a local Wi-Fi interface happens to be associated.
PROBE_URL="${Y700_NETWORK_PROBE_URL:-https://www.cloudflare.com/cdn-cgi/trace}"
CONNECT_TIMEOUT="${Y700_NETWORK_CONNECT_TIMEOUT_SEC:-3}"
MAX_TIME="${Y700_NETWORK_MAX_TIME_SEC:-5}"

if curl -fsS --connect-timeout "$CONNECT_TIMEOUT" --max-time "$MAX_TIME" \
  "$PROBE_URL" >/dev/null 2>&1; then
  echo ONLINE
  exit 0
fi

echo OFFLINE
exit 1
