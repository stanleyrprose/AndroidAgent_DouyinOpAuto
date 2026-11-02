#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${1:-}"
[[ -n "$URL" ]] || { echo 'usage: direct-download-to-tg.sh <url>' >&2; exit 2; }
response="$(bash "$ROOT/scripts/pipeline.sh" direct-download "$URL")" || { echo "$response" >&2; exit 3; }
job="$(python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("job_id", "") if d.get("status")=="EXPORTED" else "")' <<<"$response")"
[[ "$job" =~ ^dd-[0-9]{18,20}$ ]] || { echo "$response" >&2; exit 4; }
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/deliver-video-tg.py" "$job" original
