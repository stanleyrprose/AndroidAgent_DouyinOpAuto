#!/bin/bash
set -euo pipefail

ROOT_EXEC="${Y700_ROOT_EXEC:-/opt/y700/workspaces/y700-agent/bridge/root-exec.sh}"
APP_PACKAGE="com.stanley.y700automation"
TEST_PACKAGE="com.stanley.y700automation.test"
BUNDLE_DIR=""
APP_SHA=""
TEST_SHA=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --bundle-dir) BUNDLE_DIR="$2"; shift 2 ;;
    --app-sha) APP_SHA="$2"; shift 2 ;;
    --test-sha) TEST_SHA="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 64 ;;
  esac
done

case "$BUNDLE_DIR" in
  /opt/y700/*) ;;
  *) echo "bundle dir must be under /opt/y700" >&2; exit 64 ;;
esac
[ -n "$APP_SHA" ] && [ -n "$TEST_SHA" ]
[ -f "$BUNDLE_DIR/.complete" ]
[ -f "$BUNDLE_DIR/app.apk" ]
[ -f "$BUNDLE_DIR/test.apk" ]

printf '%s  %s\n' "$APP_SHA" "$BUNDLE_DIR/app.apk" | sha256sum -c -
printf '%s  %s\n' "$TEST_SHA" "$BUNDLE_DIR/test.apk" | sha256sum -c -

ANDROID_BUNDLE_DIR="/data/local/y700-agent/${BUNDLE_DIR#/opt/y700/}"

installed_sha() {
  local pkg="$1"
  "$ROOT_EXEC" "P=\$(pm path \"$pkg\" 2>/dev/null | sed -n '1s/^package://p'); [ -n \"\$P\" ] || exit 44; sha256sum \"\$P\" | cut -d' ' -f1" 2>/dev/null || true
}

install_from_stdin() {
  local host_apk="$1"
  Y700_BRIDGE_TIMEOUT_MS=60000 "$ROOT_EXEC" "P=\"$host_apk\"; S=\$(stat -c %s \"\$P\"); cat \"\$P\" | pm install -r -t -S \"\$S\""
}

deploy_one() {
  local label="$1"
  local pkg="$2"
  local expected="$3"
  local host_apk="$4"
  local current verified

  current="$(installed_sha "$pkg" | tail -n 1)"
  if [ "$current" = "$expected" ]; then
    echo "DEPLOY_SKIP label=$label package=$pkg sha=$expected reason=already-installed"
    return 0
  fi

  echo "DEPLOY_INSTALL label=$label package=$pkg previous_sha=${current:-missing} target_sha=$expected"
  install_from_stdin "$host_apk"

  verified="$(installed_sha "$pkg" | tail -n 1)"
  if [ "$verified" != "$expected" ]; then
    echo "DEPLOY_VERIFY_FAILED label=$label package=$pkg expected=$expected actual=${verified:-missing}" >&2
    exit 65
  fi
  echo "DEPLOY_VERIFIED label=$label package=$pkg sha=$verified"
}

deploy_one app "$APP_PACKAGE" "$APP_SHA" "$ANDROID_BUNDLE_DIR/app.apk"
deploy_one test "$TEST_PACKAGE" "$TEST_SHA" "$ANDROID_BUNDLE_DIR/test.apk"

"$ROOT_EXEC" 'pm list instrumentation | grep com.stanley.y700automation'
echo "APK_BUNDLE_INSTALL_PASS app_sha=$APP_SHA test_sha=$TEST_SHA"
