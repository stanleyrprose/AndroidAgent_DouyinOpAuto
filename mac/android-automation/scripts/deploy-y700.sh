#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/env.sh"

HOST="${Y700_DEPLOY_HOST:-y700dev.stanleyxyz.com}"
USER="${Y700_DEPLOY_USER:-root}"
KEY="${Y700_DEPLOY_KEY:-$HOME/.ssh/id_ed25519_y700_deploy}"
CLOUDFLARED="${CLOUDFLARED_BIN:-/opt/homebrew/bin/cloudflared}"
REMOTE_DIR="/opt/y700/runtime/automation-driver"

SSH_OPTS=(
  -i "$KEY"
  -o IdentitiesOnly=yes
  -o BatchMode=yes
  -o ConnectTimeout=15
  -o "ProxyCommand=$CLOUDFLARED access ssh --hostname %h"
)

"$ROOT/scripts/build.sh"

APP="$ROOT/app/build/outputs/apk/debug/app-debug.apk"
TEST="$ROOT/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"

APP_SHA="$(shasum -a 256 "$APP" | awk '{print $1}')"
TEST_SHA="$(shasum -a 256 "$TEST" | awk '{print $1}')"

ssh "${SSH_OPTS[@]}" "$USER@$HOST" "mkdir -p '$REMOTE_DIR' && chmod 700 '$REMOTE_DIR'"

scp "${SSH_OPTS[@]}" "$APP" "$USER@$HOST:$REMOTE_DIR/app-latest.apk"
scp "${SSH_OPTS[@]}" "$TEST" "$USER@$HOST:$REMOTE_DIR/test-latest.apk"

ssh "${SSH_OPTS[@]}" "$USER@$HOST" "
  set -e
  printf '%s  %s\n' '$APP_SHA' '$REMOTE_DIR/app-latest.apk' | sha256sum -c -
  printf '%s  %s\n' '$TEST_SHA' '$REMOTE_DIR/test-latest.apk' | sha256sum -c -
  /opt/y700/workspaces/y700-agent/bridge/root-exec.sh 'pm install -r -t /data/local/y700-agent/runtime/automation-driver/app-latest.apk'
  /opt/y700/workspaces/y700-agent/bridge/root-exec.sh 'pm install -r -t /data/local/y700-agent/runtime/automation-driver/test-latest.apk'
  /opt/y700/workspaces/y700-agent/bridge/root-exec.sh 'pm list instrumentation | grep com.stanley.y700automation'
"

echo "DEPLOY_PASS app_sha=$APP_SHA test_sha=$TEST_SHA host=$HOST"
