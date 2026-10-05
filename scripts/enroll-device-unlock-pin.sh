#!/bin/bash
set -euo pipefail
umask 0077

HOST_ROOT="${Y700_HOST_ROOT:-/proc/1/root}"
SECRET_DIR="$HOST_ROOT/data/local/y700-agent/secrets"
RUNTIME_DIR="$HOST_ROOT/data/local/y700-agent/runtime"
SECRET_FILE="$SECRET_DIR/device_unlock.pin"
FAIL_FILE="$RUNTIME_DIR/device-unlock-failures"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_root() {
  [ "$(id -u)" -eq 0 ] || die "run this command as root on Y700"
}

prepare_dirs() {
  [ -d "$HOST_ROOT/data/local/y700-agent" ] || die "Android host root is not available at $HOST_ROOT"
  install -d -m 700 "$SECRET_DIR" "$RUNTIME_DIR"
  chown 0:0 "$SECRET_DIR" "$RUNTIME_DIR" 2>/dev/null || true
}

show_status() {
  if [ -f "$SECRET_FILE" ]; then
    mode="$(stat -c '%a' "$SECRET_FILE" 2>/dev/null || echo unknown)"
    size="$(stat -c '%s' "$SECRET_FILE" 2>/dev/null || echo unknown)"
    echo "device unlock PIN: ENROLLED"
    echo "secret file mode: $mode"
    echo "secret file bytes: $size"
  else
    echo "device unlock PIN: NOT_ENROLLED"
  fi
  failures="$(cat "$FAIL_FILE" 2>/dev/null || echo 0)"
  case "$failures" in *[!0-9]*|'') failures=0 ;; esac
  echo "automatic unlock failures: $failures"
}

delete_secret() {
  rm -f "$SECRET_FILE" "$FAIL_FILE"
  echo "device unlock PIN removed"
}

enroll() {
  [ -r /dev/tty ] && [ -w /dev/tty ] || die "interactive TTY required; SSH into Y700 and run this command directly"

  pin=""
  confirm=""
  printf 'Enter Y700 lock-screen PIN (4-16 digits): ' >/dev/tty
  IFS= read -r -s pin </dev/tty
  printf '\n' >/dev/tty

  case "$pin" in
    ''|*[!0-9]*) unset pin; die "PIN must contain digits only" ;;
  esac
  [ "${#pin}" -ge 4 ] && [ "${#pin}" -le 16 ] || { unset pin; die "PIN length must be 4-16 digits"; }

  printf 'Confirm PIN: ' >/dev/tty
  IFS= read -r -s confirm </dev/tty
  printf '\n' >/dev/tty

  [ "$pin" = "$confirm" ] || { unset pin confirm; die "PIN confirmation does not match"; }

  tmp="$SECRET_DIR/.device_unlock.pin.$$"
  trap 'rm -f "$tmp" 2>/dev/null || true; unset pin confirm' EXIT HUP INT TERM
  printf '%s\n' "$pin" >"$tmp"
  chmod 600 "$tmp"
  chown 0:0 "$tmp" 2>/dev/null || true
  mv -f "$tmp" "$SECRET_FILE"
  chmod 600 "$SECRET_FILE"
  chown 0:0 "$SECRET_FILE" 2>/dev/null || true
  rm -f "$FAIL_FILE"
  unset pin confirm
  trap - EXIT HUP INT TERM

  echo "device unlock PIN enrolled locally on Y700"
  echo "secret content was not sent through Git, ChatGPT, Telegram, or bridge job payloads"
  echo "run: /opt/y700/workspaces/y700-agent/bridge/androidctl.sh unlock-secret-status"
}

require_root
prepare_dirs

case "${1:-}" in
  --status)
    show_status
    ;;
  --delete)
    delete_secret
    ;;
  "")
    enroll
    ;;
  *)
    echo "usage: $0 [--status|--delete]" >&2
    exit 64
    ;;
esac
