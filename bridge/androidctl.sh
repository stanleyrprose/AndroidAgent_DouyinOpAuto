#!/bin/bash
set -euo pipefail
ROOT_EXEC=/opt/y700/workspaces/y700-agent/bridge/root-exec.sh
RUNTIME_HOST=/data/local/y700-agent/runtime

usage() {
  cat <<'USAGE'
usage:
  androidctl status
  androidctl activity
  androidctl screenshot [name]
  androidctl dump-ui [name]
  androidctl launch <package>
  androidctl tap <x> <y>
  androidctl swipe <x1> <y1> <x2> <y2> [duration_ms]
  androidctl text <text>
  androidctl back
  androidctl home
  androidctl wake
  androidctl screen-state
  androidctl keyguard-state
  androidctl unlock
  androidctl unlock-secure
  androidctl unlock-secret-status
USAGE
}

require_int() { [[ "$1" =~ ^[0-9]+$ ]]; }
quote_sh() { printf "%q" "$1"; }

cmd="${1:-}"
case "$cmd" in
  status)
    "$ROOT_EXEC" 'id; getprop ro.product.model; getprop ro.build.version.release; getprop sys.boot_completed'
    ;;
  activity)
    "$ROOT_EXEC" 'dumpsys window windows | grep -m1 -E "mCurrentFocus|mFocusedApp" || dumpsys activity activities | grep -m1 -E "mResumedActivity|topResumedActivity|ResumedActivity"'
    ;;
  screenshot)
    name="${2:-screen-$(date +%Y%m%d-%H%M%S).png}"
    [[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid name" >&2; exit 64; }
    "$ROOT_EXEC" "screencap -p $RUNTIME_HOST/$name; ls -l $RUNTIME_HOST/$name"
    echo "/opt/y700/runtime/$name"
    ;;
  dump-ui)
    name="${2:-ui-$(date +%Y%m%d-%H%M%S).xml}"
    [[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid name" >&2; exit 64; }
    "$ROOT_EXEC" "rm -f $RUNTIME_HOST/$name; i=0; while [ \$i -lt 2 ]; do if toybox timeout 6 uiautomator dump $RUNTIME_HOST/$name >/dev/null 2>&1 && [ -s $RUNTIME_HOST/$name ]; then break; fi; i=\$((i+1)); sleep 0.5; done; [ -s $RUNTIME_HOST/$name ] || { echo UI_DUMP_FAILED >&2; exit 1; }; ls -l $RUNTIME_HOST/$name"
    echo "/opt/y700/runtime/$name"
    ;;
  launch)
    pkg="${2:-}"
    [[ "$pkg" =~ ^[A-Za-z0-9._]+$ ]] || { echo "invalid package" >&2; exit 64; }
    "$ROOT_EXEC" "component=\$(cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER $pkg 2>/dev/null | tail -1); [ -n \"\$component\" ] || { echo LAUNCHER_ACTIVITY_NOT_FOUND >&2; exit 1; }; su 2000 -c \"am start -W --user 0 -n \\\"\$component\\\"\""
    ;;
  tap)
    [ "$#" -eq 3 ] && require_int "$2" && require_int "$3" || { usage >&2; exit 64; }
    "$ROOT_EXEC" "input tap $2 $3"
    ;;
  swipe)
    [ "$#" -ge 5 ] || { usage >&2; exit 64; }
    require_int "$2" && require_int "$3" && require_int "$4" && require_int "$5" || { usage >&2; exit 64; }
    dur="${6:-300}"
    require_int "$dur" || { usage >&2; exit 64; }
    "$ROOT_EXEC" "input swipe $2 $3 $4 $5 $dur"
    ;;
  text)
    shift
    [ "$#" -ge 1 ] || { usage >&2; exit 64; }
    text="$*"
    text="${text// /%s}"
    q="$(quote_sh "$text")"
    "$ROOT_EXEC" "input text $q"
    ;;
  back)
    "$ROOT_EXEC" 'input keyevent KEYCODE_BACK'
    ;;
  home)
    "$ROOT_EXEC" 'input keyevent KEYCODE_HOME'
    ;;
  wake)
    "$ROOT_EXEC" 'input keyevent KEYCODE_WAKEUP'
    ;;
  screen-state)
    "$ROOT_EXEC" 'dumpsys power | grep -m1 -E "mWakefulness|Display Power"'
    ;;
  keyguard-state)
    "$ROOT_EXEC" 'dumpsys window policy | grep -A5 -i "KeyguardStateMonitor"'
    ;;
  unlock)
    "$ROOT_EXEC" 'input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard; sleep 1; dumpsys window policy | grep -A5 -i "KeyguardStateMonitor"'
    ;;
  unlock-secure)
    exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/secure-unlock.sh"
    ;;
  unlock-secret-status)
    exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/secure-unlock.sh" --status
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac
