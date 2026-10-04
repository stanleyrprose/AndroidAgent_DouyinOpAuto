#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/env.sh"

HOST="${Y700_DEPLOY_HOST:-y700dev.stanleyxyz.com}"
USER="${Y700_DEPLOY_USER:-root}"
KEY="${Y700_DEPLOY_KEY:-$HOME/.ssh/id_ed25519_y700_deploy}"
CLOUDFLARED="${CLOUDFLARED_BIN:-/opt/homebrew/bin/cloudflared}"
REMOTE_DIR="/opt/y700/runtime/automation-driver"
ANDROID_REMOTE_DIR="/data/local/y700-agent/runtime/automation-driver"
ROOT_EXEC="/opt/y700/workspaces/y700-agent/bridge/root-exec.sh"

APP_PACKAGE="com.stanley.y700automation"
TEST_PACKAGE="com.stanley.y700automation.test"

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
  set -eu

  ROOT_EXEC='$ROOT_EXEC'
  REMOTE_DIR='$REMOTE_DIR'
  ANDROID_REMOTE_DIR='$ANDROID_REMOTE_DIR'

  printf '%s  %s\n' '$APP_SHA' "\$REMOTE_DIR/app-latest.apk" | sha256sum -c -
  printf '%s  %s\n' '$TEST_SHA' "\$REMOTE_DIR/test-latest.apk" | sha256sum -c -

  installed_sha() {
    pkg=\"\$1\"
    \$ROOT_EXEC \"P=\\\$(pm path \\\"\$pkg\\\" 2>/dev/null | sed -n '1s/^package://p'); [ -n \\\"\\\$P\\\" ] || exit 44; sha256sum \\\"\\\$P\\\" | awk '{print \\\$1}'\" 2>/dev/null || true
  }

  install_from_stdin() {
    host_apk=\"\$1\"
    Y700_BRIDGE_TIMEOUT_MS=60000 \$ROOT_EXEC \"P=\\\"\$host_apk\\\"; S=\\\$(stat -c %s \\\"\\\$P\\\"); cat \\\"\\\$P\\\" | pm install -r -t -S \\\"\\\$S\\\"\"
  }

  deploy_one() {
    label=\"\$1\"
    pkg=\"\$2\"
    expected=\"\$3\"
    host_apk=\"\$4\"

    current=\"\$(installed_sha \"\$pkg\" | tail -n 1)\"
    if [ \"\$current\" = \"\$expected\" ]; then
      echo \"DEPLOY_SKIP label=\$label package=\$pkg sha=\$expected reason=already-installed\"
      return 0
    fi

    echo \"DEPLOY_INSTALL label=\$label package=\$pkg previous_sha=\${current:-missing} target_sha=\$expected\"
    install_from_stdin \"\$host_apk\"

    verified=\"\$(installed_sha \"\$pkg\" | tail -n 1)\"
    if [ \"\$verified\" != \"\$expected\" ]; then
      echo \"DEPLOY_VERIFY_FAILED label=\$label package=\$pkg expected=\$expected actual=\${verified:-missing}\" >&2
      exit 65
    fi
    echo \"DEPLOY_VERIFIED label=\$label package=\$pkg sha=\$verified\"
  }

  deploy_one app '$APP_PACKAGE' '$APP_SHA' "\$ANDROID_REMOTE_DIR/app-latest.apk"
  deploy_one test '$TEST_PACKAGE' '$TEST_SHA' "\$ANDROID_REMOTE_DIR/test-latest.apk"

  \$ROOT_EXEC 'pm list instrumentation | grep com.stanley.y700automation'
"

echo "DEPLOY_PASS app_sha=$APP_SHA test_sha=$TEST_SHA host=$HOST"
