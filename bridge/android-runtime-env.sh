#!/system/bin/sh
set -eu

TOYBOX=/system/bin/toybox

zygote_pids="$("$TOYBOX" pidof zygote64 2>/dev/null || true)"
zygote_pid="${zygote_pids%% *}"
if [ -z "$zygote_pid" ] || [ ! -r "/proc/$zygote_pid/environ" ]; then
  echo "ANDROID_RUNTIME_ENV_ZYGOTE_UNAVAILABLE" >&2
  exit 70
fi

ENV_SOURCE="/proc/$zygote_pid/environ"

read_env() {
  name="$1"
  "$TOYBOX" tr '\000' '\n' <"$ENV_SOURCE" |
    "$TOYBOX" sed -n "s/^${name}=//p" |
    "$TOYBOX" head -n 1
}

ANDROID_ROOT="$(read_env ANDROID_ROOT)"
ANDROID_DATA="$(read_env ANDROID_DATA)"
ANDROID_ART_ROOT="$(read_env ANDROID_ART_ROOT)"
ANDROID_I18N_ROOT="$(read_env ANDROID_I18N_ROOT)"
ANDROID_TZDATA_ROOT="$(read_env ANDROID_TZDATA_ROOT)"
ANDROID_STORAGE="$(read_env ANDROID_STORAGE)"
ANDROID_ASSETS="$(read_env ANDROID_ASSETS)"
BOOTCLASSPATH="$(read_env BOOTCLASSPATH)"
DEX2OATBOOTCLASSPATH="$(read_env DEX2OATBOOTCLASSPATH)"
SYSTEMSERVERCLASSPATH="$(read_env SYSTEMSERVERCLASSPATH)"
STANDALONE_SYSTEMSERVER_JARS="$(read_env STANDALONE_SYSTEMSERVER_JARS)"

for required in ANDROID_ROOT ANDROID_DATA ANDROID_ART_ROOT BOOTCLASSPATH DEX2OATBOOTCLASSPATH; do
  case "$required" in
    ANDROID_ROOT) value="$ANDROID_ROOT" ;;
    ANDROID_DATA) value="$ANDROID_DATA" ;;
    ANDROID_ART_ROOT) value="$ANDROID_ART_ROOT" ;;
    BOOTCLASSPATH) value="$BOOTCLASSPATH" ;;
    DEX2OATBOOTCLASSPATH) value="$DEX2OATBOOTCLASSPATH" ;;
  esac
  if [ -z "$value" ]; then
    echo "ANDROID_RUNTIME_ENV_MISSING_$required" >&2
    exit 71
  fi
done

export ANDROID_ROOT ANDROID_DATA ANDROID_ART_ROOT ANDROID_I18N_ROOT
export ANDROID_TZDATA_ROOT ANDROID_STORAGE ANDROID_ASSETS
export BOOTCLASSPATH DEX2OATBOOTCLASSPATH SYSTEMSERVERCLASSPATH
export STANDALONE_SYSTEMSERVER_JARS

exec "$@"
