#!/bin/bash
set -euo pipefail

SOT_ROOT="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_ROOT="${Y700_MEDIA_RUNTIME_ROOT:-$HOME/Library/Application Support/Y700Media}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-$(command -v cloudflared)}"
CONFIG_SOURCE="${Y700_MEDIA_CLOUDFLARED_CONFIG:-$SOT_ROOT/runtime/cloudflared.yml}"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
SERVER_LABEL="com.stanley.y700-media-server"
TUNNEL_LABEL="com.stanley.y700-media-tunnel"
SERVER_PLIST="$LAUNCH_DIR/$SERVER_LABEL.plist"
TUNNEL_PLIST="$LAUNCH_DIR/$TUNNEL_LABEL.plist"

mkdir -p "$LAUNCH_DIR" "$RUNTIME_ROOT/exports"
test -x "$PYTHON_BIN"
test -x "$CLOUDFLARED_BIN"
test -s "$CONFIG_SOURCE"
test -f "$SOT_ROOT/server.py"
test -f "$SOT_ROOT/export_job.py"

# Deploy generated runtime copies outside ~/Documents. macOS background
# LaunchAgents can otherwise stall on TCC-protected project paths.
install -m 755 "$SOT_ROOT/server.py" "$RUNTIME_ROOT/server.py"
install -m 755 "$SOT_ROOT/export_job.py" "$RUNTIME_ROOT/export_job.py"
install -m 600 "$CONFIG_SOURCE" "$RUNTIME_ROOT/cloudflared.yml"

python3 - "$SERVER_PLIST" "$RUNTIME_ROOT" "$PYTHON_BIN" <<'PY'
from pathlib import Path
import plistlib, sys
out, root, python = sys.argv[1:]
root = Path(root)
data = {
    "Label": "com.stanley.y700-media-server",
    "ProgramArguments": [
        python, str(root / "server.py"),
        "--root", str(root / "exports"),
        "--host", "127.0.0.1", "--port", "8790",
    ],
    "WorkingDirectory": str(root),
    "RunAtLoad": True,
    "KeepAlive": True,
    "ProcessType": "Background",
    "StandardOutPath": str(root / "server.log"),
    "StandardErrorPath": str(root / "server.err.log"),
}
Path(out).write_bytes(plistlib.dumps(data))
PY

python3 - "$TUNNEL_PLIST" "$RUNTIME_ROOT" "$CLOUDFLARED_BIN" <<'PY'
from pathlib import Path
import plistlib, sys
out, root, cloudflared = sys.argv[1:]
root = Path(root)
data = {
    "Label": "com.stanley.y700-media-tunnel",
    "ProgramArguments": [
        cloudflared,
        "--config", str(root / "cloudflared.yml"),
        "tunnel", "run", "y700-media-mac",
    ],
    "WorkingDirectory": str(root),
    "RunAtLoad": True,
    "KeepAlive": True,
    "ProcessType": "Background",
    "StandardOutPath": str(root / "tunnel.log"),
    "StandardErrorPath": str(root / "tunnel.err.log"),
}
Path(out).write_bytes(plistlib.dumps(data))
PY

chmod 600 "$SERVER_PLIST" "$TUNNEL_PLIST"

uid="$(id -u)"
for label in "$SERVER_LABEL" "$TUNNEL_LABEL"; do
  launchctl bootout "gui/$uid/$label" 2>/dev/null || true
done

# Stop manually launched canonical instances before launchd assumes ownership.
for pidfile in "$SOT_ROOT/runtime/server.pid" "$SOT_ROOT/runtime/cloudflared.pid"; do
  if [ -s "$pidfile" ]; then
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" || true
    fi
    rm -f "$pidfile"
  fi
done

# Refuse to steal 8790 from an unrelated service.
for pid in $(lsof -tiTCP:8790 -sTCP:LISTEN 2>/dev/null || true); do
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  case "$cmd" in
    *Y700Media/server.py*|*media-export/server.py*) kill "$pid" || true ;;
    *) echo "PORT_8790_OWNED_BY_OTHER_PROCESS pid=$pid cmd=$cmd" >&2; exit 2 ;;
  esac
done
sleep 1

launchctl bootstrap "gui/$uid" "$SERVER_PLIST"
launchctl bootstrap "gui/$uid" "$TUNNEL_PLIST"

launchctl print "gui/$uid/$SERVER_LABEL" >/dev/null
launchctl print "gui/$uid/$TUNNEL_LABEL" >/dev/null

server_ready=0
for _ in $(seq 1 30); do
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 1 http://127.0.0.1:8790/ 2>/dev/null || true)"
  if [ "$code" = "404" ]; then
    server_ready=1
    break
  fi
  sleep 0.5
done
if [ "$server_ready" -ne 1 ]; then
  echo "MEDIA_SERVER_HTTP_TIMEOUT" >&2
  exit 3
fi

tunnel_ready=0
for _ in $(seq 1 30); do
  if grep -q "Registered tunnel connection" "$RUNTIME_ROOT/tunnel.log" "$RUNTIME_ROOT/tunnel.err.log" 2>/dev/null; then
    tunnel_ready=1
    break
  fi
  sleep 0.5
done
if [ "$tunnel_ready" -ne 1 ]; then
  echo "MEDIA_TUNNEL_REGISTRATION_TIMEOUT" >&2
  exit 4
fi

echo "LAUNCHD_MEDIA_RUNTIME_PASS runtime_root=$RUNTIME_ROOT"
