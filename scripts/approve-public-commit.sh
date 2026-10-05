#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
READY_ROOT="${Y700_READY_ROOT:-/opt/y700/media/ready}"
PUBLISHED_ROOT="${Y700_PUBLISHED_ROOT:-/opt/y700/media/published}"
RUN_ROOT="${Y700_PUBLISH_RUN_ROOT:-/opt/y700/runtime/publish-runs}"
STATE="${Y700_PUBLISH_STATE:-/opt/y700/runtime/state/publisher.json}"
PUBLISH_ASYNC="${Y700_PUBLISH_ASYNC:-$ROOT/scripts/publish-async.sh}"
JOB_ID="${1:-}"
APPROVAL_NOTE="${2:-standing workflow authorization}"

if [ -z "$JOB_ID" ] || [[ ! "$JOB_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "usage: approve-public-commit.sh <job_id> [approval-note]" >&2
  exit 2
fi

READY="$READY_ROOT/$JOB_ID"
PUBLISHED="$PUBLISHED_ROOT/$JOB_ID"
RUN_DIR="$RUN_ROOT/$JOB_ID"
MANIFEST="$READY/manifest.json"
PID_FILE="$RUN_DIR/pid"
APPROVAL="$RUN_DIR/approval.json"
LOCK_DIR="$RUN_DIR/commit-transition.lock"

if [ -d "$PUBLISHED" ]; then
  printf '{"status":"ALREADY_PUBLISHED","job_id":"%s"}\n' "$JOB_ID"
  exit 0
fi
if [ ! -f "$MANIFEST" ] || [ ! -f "$STATE" ]; then
  printf '{"status":"NOT_READY","job_id":"%s"}\n' "$JOB_ID" >&2
  exit 3
fi

mkdir -p "$RUN_DIR"
chmod 700 "$RUN_DIR" 2>/dev/null || true

acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$LOCK_DIR/pid"
    return 0
  fi
  local owner=""
  owner="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [ -n "$owner" ] && ! kill -0 "$owner" 2>/dev/null; then
    rm -rf "$LOCK_DIR"
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      printf '%s\n' "$$" > "$LOCK_DIR/pid"
      return 0
    fi
  fi
  return 1
}

if ! acquire_lock; then
  printf '{"status":"COMMIT_TRANSITION_BUSY","job_id":"%s"}\n' "$JOB_ID" >&2
  exit 4
fi
cleanup_lock() { rm -rf "$LOCK_DIR" 2>/dev/null || true; }
trap cleanup_lock EXIT INT TERM

if [ -s "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    printf '{"status":"PUBLISHER_ALREADY_RUNNING","job_id":"%s","pid":%s}\n' "$JOB_ID" "$OLD_PID" >&2
    exit 5
  fi
fi

python3 - "$MANIFEST" "$STATE" "$APPROVAL" "$JOB_ID" "$APPROVAL_NOTE" <<'PY'
import json, os, sys, time
manifest_path, state_path, approval_path, job_id, note = sys.argv[1:]
with open(state_path, encoding="utf-8") as f:
    state = json.load(f)
with open(manifest_path, encoding="utf-8") as f:
    manifest = json.load(f)

if state.get("job_id") != job_id:
    raise SystemExit(f"publisher state belongs to another job: {state.get('job_id')}")
if state.get("status") != "READY_TO_COMMIT":
    raise SystemExit(f"publisher is not READY_TO_COMMIT: {state.get('status')}")
if str(state.get("visibility", "")).upper() != "PUBLIC":
    raise SystemExit(f"publisher visibility is not PUBLIC: {state.get('visibility')}")
if manifest.get("job_id") != job_id:
    raise SystemExit(f"manifest job mismatch: {manifest.get('job_id')}")
if str(manifest.get("visibility", "")).upper() != "PUBLIC":
    raise SystemExit(f"manifest visibility is not PUBLIC: {manifest.get('visibility')}")
mode = manifest.get("publish_mode")
if mode != "DRY_RUN":
    if mode == "COMMIT":
        raise SystemExit("manifest is already COMMIT; reconcile before any retry")
    raise SystemExit(f"unexpected publish_mode: {mode}")

manifest["publish_mode"] = "COMMIT"
manifest_tmp = manifest_path + ".tmp"
with open(manifest_tmp, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
    f.write("\n")
    f.flush()
    os.fsync(f.fileno())
os.replace(manifest_tmp, manifest_path)

approval = {
    "job_id": job_id,
    "approval": "explicit_workflow_authorization",
    "visibility": "PUBLIC",
    "scope": "one_commit_attempt",
    "note": note[:240],
    "approved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
}
approval_tmp = approval_path + ".tmp"
with open(approval_tmp, "w", encoding="utf-8") as f:
    json.dump(approval, f, ensure_ascii=False, indent=2)
    f.write("\n")
    f.flush()
    os.fsync(f.fileno())
os.replace(approval_tmp, approval_path)
os.chmod(approval_path, 0o600)
print(json.dumps({"status":"COMMIT_ARMED","job_id":job_id,"visibility":"PUBLIC"}, ensure_ascii=False))
PY

"$PUBLISH_ASYNC" "$JOB_ID" --commit
