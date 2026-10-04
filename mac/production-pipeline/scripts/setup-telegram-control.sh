#!/bin/bash
set -euo pipefail

PIPE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$PIPE_ROOT/../.." && pwd)"
PROFILE="${Y700_HERMES_PROFILE:-y700automation}"
TIMEZONE="${Y700_AUTOMATION_TIMEZONE:-Asia/Yangon}"
HERMES_BIN="${HERMES_BIN:-$(command -v hermes || true)}"
WRAPPER="${Y700_HERMES_WRAPPER:-$HOME/.local/bin/$PROFILE}"
PROFILE_ROOT="$HOME/.hermes/profiles/$PROFILE"
SKILL_URL="${Y700_SKILL_URL:-https://raw.githubusercontent.com/stanleyrprose/chatgpt-skills/main/skills/productivity/douyin-tiktok-publish/SKILL.md}"
SOUL_SOURCE="$REPO_ROOT/config/hermes-y700automation-SOUL.md"

if [ -z "$HERMES_BIN" ] || [ ! -x "$HERMES_BIN" ]; then
  echo "HERMES_NOT_FOUND" >&2
  exit 2
fi

if [ ! -x "$WRAPPER" ]; then
  "$HERMES_BIN" profile create "$PROFILE" --no-skills --description "Dedicated Telegram-controlled Y700 automation profile for Douyin to Burmese TikTok publishing."
fi

test -x "$WRAPPER"
test -f "$SOUL_SOURCE"

"$WRAPPER" config set terminal.cwd "$REPO_ROOT"
"$WRAPPER" config set timezone "$TIMEZONE"

mkdir -p "$PROFILE_ROOT/skills/productivity/douyin-tiktok-publish"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
curl --fail --silent --show-error --location --retry 2 "$SKILL_URL" -o "$tmp"
grep -q '^name: douyin-tiktok-publish$' "$tmp"
install -m 644 "$tmp" "$PROFILE_ROOT/skills/productivity/douyin-tiktok-publish/SKILL.md"
install -m 600 "$SOUL_SOURCE" "$PROFILE_ROOT/SOUL.md"

"$WRAPPER" tools enable --platform telegram terminal file vision skills todo clarify
"$WRAPPER" tools disable --platform telegram web browser code_execution image_gen video_gen x_search tts stt memory session_search connections delegation cronjob computer_use homeassistant spotify yuanbao context_engine a2a || true

if [ "${Y700_INSTALL_GATEWAY_SERVICE:-0}" = "1" ]; then
  "$WRAPPER" gateway install --no-start-now --start-on-login
fi

echo "Y700_TELEGRAM_PROFILE_READY profile=$PROFILE secrets_configured=false"
echo "Next: configure dedicated TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_USERS, then start the gateway."
