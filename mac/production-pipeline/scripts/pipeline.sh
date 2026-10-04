#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/runtime/env.local"
if [ -r "$ENV_FILE" ]; then
  set -a
  # Deployment-local settings only; runtime/ is excluded from Git.
  source "$ENV_FILE"
  set +a
fi
exec "$ROOT/.venv/bin/python" -m pipeline.cli "$@"
