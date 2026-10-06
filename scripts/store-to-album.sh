#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JOB_ID="${1:-}"
ALBUM="${2:-Y700Agent}"
if [ -z "$JOB_ID" ] || [[ ! "$JOB_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "usage: store-to-album.sh <job_id> [album]" >&2
  exit 2
fi
exec python3 "$ROOT/publisher/store_album_job.py" "$JOB_ID" --album "$ALBUM"
