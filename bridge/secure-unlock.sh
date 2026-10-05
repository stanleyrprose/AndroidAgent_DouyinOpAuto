#!/bin/bash
set -euo pipefail
umask 0077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_EXEC="${Y700_ROOT_EXEC:-$SCRIPT_DIR/root-exec.sh}"
MAX_FAILURES="${Y700_UNLOCK_MAX_FAILURES:-2}"

case "$MAX_FAILURES" in *[!0-9]*|'') echo "invalid Y700_UNLOCK_MAX_FAILURES" >&2; exit 64 ;; esac
[ "$MAX_FAILURES" -ge 1 ] || { echo "Y700_UNLOCK_MAX_FAILURES must be >=1" >&2; exit 64; }

if [ "${1:-}" = "--status" ]; then
  exec "$ROOT_EXEC" '
set -eu
secret=/data/local/y700-agent/secrets/device_unlock.pin
fail=/data/local/y700-agent/runtime/device-unlock-failures
if [ -r "$secret" ]; then echo DEVICE_UNLOCK_SECRET=ENROLLED; else echo DEVICE_UNLOCK_SECRET=NOT_ENROLLED; fi
n=$(cat "$fail" 2>/dev/null || echo 0)
case "$n" in *[!0-9]*|"") n=0 ;; esac
echo DEVICE_UNLOCK_FAILURES="$n"
'
fi

[ "$#" -eq 0 ] || { echo "usage: $0 [--status]" >&2; exit 64; }

cmd=$(cat <<'ANDROID_SH'
set -eu
secret=/data/local/y700-agent/secrets/device_unlock.pin
fail=/data/local/y700-agent/runtime/device-unlock-failures
max_failures=__MAX_FAILURES__

keyguard_state() {
  dump="$(dumpsys window policy 2>/dev/null || true)"
  section="$(printf '%s\n' "$dump" | sed -n '/KeyguardStateMonitor/,+20p')"
  [ -n "$section" ] || section="$dump"

  if printf '%s\n' "$section" | grep -Eiq '(mIsShowing|isShowing|showing|mShowingLockscreen|keyguardShowing|isStatusBarKeyguard)[^A-Za-z0-9]*(true|1)'; then
    echo LOCKED
    return 0
  fi
  if printf '%s\n' "$section" | grep -Eiq '(mIsShowing|isShowing|showing|mShowingLockscreen|keyguardShowing|isStatusBarKeyguard)[^A-Za-z0-9]*(false|0)'; then
    echo CLEAR
    return 0
  fi
  echo UNKNOWN
}

state="$(keyguard_state)"
if [ "$state" = CLEAR ]; then
  rm -f "$fail"
  echo DEVICE_UNLOCK_ALREADY_CLEAR
  exit 0
fi
if [ "$state" = UNKNOWN ]; then
  echo DEVICE_UNLOCK_STATE_UNKNOWN >&2
  exit 70
fi

[ -r "$secret" ] || { echo DEVICE_UNLOCK_NOT_ENROLLED >&2; exit 78; }
pin="$(cat "$secret")"
case "$pin" in
  ""|*[!0-9]*) unset pin; echo DEVICE_UNLOCK_SECRET_INVALID >&2; exit 65 ;;
esac
[ "${#pin}" -ge 4 ] && [ "${#pin}" -le 16 ] || { unset pin; echo DEVICE_UNLOCK_SECRET_INVALID >&2; exit 65; }

n="$(cat "$fail" 2>/dev/null || echo 0)"
case "$n" in *[!0-9]*|"") n=0 ;; esac
if [ "$n" -ge "$max_failures" ]; then
  unset pin
  echo DEVICE_UNLOCK_BLOCKED_FAILURE_LATCH >&2
  exit 75
fi

input keyevent KEYCODE_WAKEUP >/dev/null 2>&1 || true
wm dismiss-keyguard >/dev/null 2>&1 || true
sleep 0.5

state="$(keyguard_state)"
if [ "$state" = CLEAR ]; then
  rm -f "$fail"
  unset pin
  echo DEVICE_UNLOCK_OK
  exit 0
fi

size="$(wm size 2>/dev/null | sed -n 's/.*Physical size: \([0-9][0-9]*x[0-9][0-9]*\).*/\1/p' | tail -1)"
case "$size" in
  *x*) w="${size%x*}"; h="${size#*x}" ;;
  *) w=1904; h=3040 ;;
esac
x=$((w / 2))
y1=$((h * 4 / 5))
y2=$((h / 3))
input swipe "$x" "$y1" "$x" "$y2" 250 >/dev/null 2>&1 || true
sleep 0.4

i=1
while [ "$i" -le "${#pin}" ]; do
  d="$(printf '%s' "$pin" | cut -c "$i")"
  input keyevent "KEYCODE_$d" >/dev/null 2>&1 || true
  i=$((i + 1))
  sleep 0.05
done
input keyevent KEYCODE_ENTER >/dev/null 2>&1 || true
unset pin
sleep 1.2

state="$(keyguard_state)"
if [ "$state" = CLEAR ]; then
  rm -f "$fail"
  echo DEVICE_UNLOCK_OK
  exit 0
fi

n=$((n + 1))
printf '%s\n' "$n" >"$fail.tmp"
chmod 600 "$fail.tmp" 2>/dev/null || true
mv -f "$fail.tmp" "$fail"
echo DEVICE_UNLOCK_FAILED >&2
exit 77
ANDROID_SH
)
cmd="${cmd/__MAX_FAILURES__/$MAX_FAILURES}"
exec "$ROOT_EXEC" "$cmd"
