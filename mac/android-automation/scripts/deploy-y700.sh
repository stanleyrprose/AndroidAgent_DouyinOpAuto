#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/env.sh"

HOST="${Y700_DEPLOY_HOST:-y700dev.stanleyxyz.com}"
USER="${Y700_DEPLOY_USER:-root}"
KEY="${Y700_DEPLOY_KEY:-$HOME/.ssh/id_ed25519_y700_deploy}"
CLOUDFLARED="${CLOUDFLARED_BIN:-/opt/homebrew/bin/cloudflared}"
REMOTE_DIR="/opt/y700/runtime/automation-driver"
DEPLOY_WORKSPACE="${Y700_DEPLOY_WORKSPACE:-/opt/y700/workspaces/y700-agent}"
PULLER="$DEPLOY_WORKSPACE/scripts/pull-artifact-bundle.py"
INSTALLER="$DEPLOY_WORKSPACE/scripts/install-apk-bundle.sh"
ARTIFACT_BASE_URL="${Y700_ARTIFACT_BASE_URL:-${Y700_MEDIA_BASE_URL:-https://y700media.stanleyxyz.com}}"
ARTIFACT_ROOT="${Y700_ARTIFACT_ROOT:-$HOME/Library/Application Support/Y700Media/exports}"
ARTIFACT_EXPORTER="$ROOT/../media-export/export_job.py"

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
JOB_ID="android-deploy-$(date +%Y%m%d-%H%M%S)-$$"

EXPORT_JSON="$(
  python3 "$ARTIFACT_EXPORTER"     --artifact "app.apk=$APP"     --artifact "test.apk=$TEST"     --job-id "$JOB_ID"     --ttl-seconds 1800     --root "$ARTIFACT_ROOT"     --base-url "$ARTIFACT_BASE_URL"
)"
MANIFEST_URL="$(printf '%s' "$EXPORT_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["manifest_url"])')"
BUNDLE_DIR="$REMOTE_DIR/bundles/$JOB_ID"

ssh "${SSH_OPTS[@]}" "$USER@$HOST" "
  set -eu
  test -f '$PULLER'
  test -f '$INSTALLER'
  mkdir -p '$REMOTE_DIR/bundles'
  python3 '$PULLER' --manifest-url '$MANIFEST_URL' --target-root '$REMOTE_DIR/bundles'
  bash '$INSTALLER' --bundle-dir '$BUNDLE_DIR' --app-sha '$APP_SHA' --test-sha '$TEST_SHA'
  rm -rf '$BUNDLE_DIR'
"

rm -rf "$ARTIFACT_ROOT/$JOB_ID"
echo "DEPLOY_PASS transport=artifact-pull app_sha=$APP_SHA test_sha=$TEST_SHA host=$HOST"
