#!/bin/bash
set -euo pipefail

WORKSPACES_ROOT="${Y700_WORKSPACES_ROOT:-/opt/y700/workspaces}"
STABLE_LINK="${Y700_STABLE_LINK:-$WORKSPACES_ROOT/y700-agent}"
ROLLBACK_FILE="${Y700_ROLLBACK_FILE:-/opt/y700/runtime/deploy-previous-release}"

usage() {
  echo "usage: $0 <release-basename>" >&2
  exit 64
}

[ "$#" -eq 1 ] || usage
release="$1"

case "$release" in
  ""|.*|*/*|*\\*|*[!A-Za-z0-9._-]*)
    echo "INVALID_RELEASE_BASENAME" >&2
    exit 65
    ;;
esac

target="$WORKSPACES_ROOT/$release"
if [ ! -d "$target" ]; then
  echo "RELEASE_NOT_FOUND: $target" >&2
  exit 66
fi

if ! git -C "$target" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "RELEASE_NOT_GIT_WORKTREE: $target" >&2
  exit 67
fi

if [ -n "$(git -C "$target" status --porcelain --untracked-files=no)" ]; then
  echo "RELEASE_NOT_CLEAN: $target" >&2
  exit 68
fi

current=""
if [ -L "$STABLE_LINK" ] || [ -e "$STABLE_LINK" ]; then
  resolved="$(readlink -f "$STABLE_LINK" 2>/dev/null || true)"
  if [ -n "$resolved" ]; then
    current="$(basename "$resolved")"
  fi
fi

mkdir -p "$(dirname "$ROLLBACK_FILE")"
if [ -n "$current" ] && [ "$current" != "$release" ]; then
  tmp="$ROLLBACK_FILE.tmp.$$"
  printf '%s\n' "$current" >"$tmp"
  chmod 600 "$tmp" 2>/dev/null || true
  mv "$tmp" "$ROLLBACK_FILE"
fi

# Critical invariant: the stable target must be relative. The Android host
# sees the same workspace directory through the chroot backing path, so an
# absolute /opt/... target is broken outside the chroot.
ln -sfn "$release" "$STABLE_LINK"

actual="$(readlink "$STABLE_LINK" 2>/dev/null || true)"
if [ "$actual" != "$release" ]; then
  echo "PROMOTION_VERIFY_FAILED: expected=$release actual=$actual" >&2
  exit 69
fi

echo "PROMOTED release=$release previous=${current:-none}"
