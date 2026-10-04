#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/runtime/env.local"
if [ -r "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi
cd "$ROOT"
exec "$ROOT/.venv/bin/python" -m pipeline.telegram_notify "$@"
