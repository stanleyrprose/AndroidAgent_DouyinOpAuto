#!/bin/bash
set -euo pipefail

ROOT="${Y700_STABLE_ROOT:-/opt/y700/workspaces/y700-agent}"
MAIN_REF="${Y700_MAIN_REF:-origin/main}"

runtime_paths=(
  apps
  automation
  bootstrap
  bridge
  config
  publisher
  scripts
  mac/android-automation
)

if [ -L "$ROOT" ]; then
  stable_target="$(readlink "$ROOT" 2>/dev/null || true)"
  case "$stable_target" in
    /*)
      echo DRIFT
      exit 1
      ;;
  esac
fi

stable_head="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
main_head="$(git -C "$ROOT" rev-parse "$MAIN_REF" 2>/dev/null || true)"

if [ -z "$stable_head" ] || [ -z "$main_head" ]; then
  echo UNKNOWN
  exit 2
fi

if git -C "$ROOT" diff --quiet "$stable_head" "$main_head" -- "${runtime_paths[@]}"; then
  echo HEALTHY
  exit 0
fi

echo DRIFT
exit 1
