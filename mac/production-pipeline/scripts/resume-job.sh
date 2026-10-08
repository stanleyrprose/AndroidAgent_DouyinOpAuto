#!/bin/bash
set -euo pipefail
umask 0077

PIPE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JOB_ID="${1:-}"
if [ -z "$JOB_ID" ] || [[ ! "$JOB_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "usage: resume-job.sh <job_id>" >&2
  exit 2
fi

RUNTIME_ROOT="${Y700_PIPE_RUNTIME_ROOT:-$PIPE_ROOT/runtime}"
JOB_DIR="$RUNTIME_ROOT/jobs/$JOB_ID"
STATE="$JOB_DIR/state.json"
HANDOFF="$JOB_DIR/export/handoff.json"
PIPELINE_CMD="${Y700_PIPELINE_CMD:-$PIPE_ROOT/scripts/pipeline.sh}"
ALBUM_CMD="${Y700_ALBUM_STORE_CMD:-$PIPE_ROOT/scripts/store-to-y700-album.sh}"
DIRECT_CMD="${Y700_DIRECT_DOWNLOAD_CMD:-$PIPE_ROOT/scripts/complete-direct-download.sh}"
CLOSURE_CMD="${Y700_CLOSURE_START_CMD:-$PIPE_ROOT/scripts/start-publication-closure.sh}"
TG_NOTIFY="${Y700_TG_NOTIFY:-$PIPE_ROOT/scripts/tg-notify.sh}"
HOST="${Y700_DEPLOY_HOST:-y700dev.stanleyxyz.com}"
USER="${Y700_DEPLOY_USER:-root}"
KEY="${Y700_DEPLOY_KEY:-$HOME/.ssh/id_ed25519_y700_deploy}"
CLOUDFLARED="${CLOUDFLARED_BIN:-/opt/homebrew/bin/cloudflared}"
REMOTE_RUNNER="${Y700_REMOTE_RUNNER:-}"
POLL_SEC="${Y700_RESUME_POLL_SEC:-8}"
TIMEOUT_SEC="${Y700_RESUME_TIMEOUT_SEC:-420}"
NOW_EPOCH="${Y700_RESUME_NOW_EPOCH:-}"

notify() {
  local state="$1" detail="$2"
  bash "$TG_NOTIFY" "$state" "$JOB_ID" --detail "$detail" >/dev/null 2>&1 || true
}

emit() {
  printf '%s\n' "$1"
}

block() {
  local reason="$1"
  notify RESUME_BLOCKED "$reason"
  printf '{"status":"RESUME_BLOCKED","job_id":"%s","reason":"%s"}\n' "$JOB_ID" "$reason"
  exit 6
}

waiting() {
  local reason="$1"
  notify RESUME_WAITING "$reason"
  printf '{"status":"RESUME_WAITING","job_id":"%s","reason":"%s"}\n' "$JOB_ID" "$reason"
  exit 5
}

remote() {
  local command="$1"
  if [ -n "$REMOTE_RUNNER" ]; then
    "$REMOTE_RUNNER" "$command"
    return
  fi
  ssh \
    -i "$KEY" \
    -o IdentitiesOnly=yes \
    -o BatchMode=yes \
    -o ConnectTimeout=15 \
    -o "ProxyCommand=$CLOUDFLARED access ssh --hostname %h" \
    "$USER@$HOST" "$command"
}

if [ ! -f "$STATE" ]; then
  block "unknown job or missing durable state"
fi

read -r mac_state intent < <(python3 - "$STATE" <<'PY'
import json,sys
try: d=json.load(open(sys.argv[1],encoding='utf-8'))
except Exception: print('INVALID -')
else: print(d.get('state',''), d.get('workflow_intent','-'))
PY
)
if [ "$mac_state" = "INVALID" ]; then
  block "invalid Mac job state"
fi
if [ "$intent" != "STORE_ALBUM" ] && [ "$intent" != "AUTO_PUBLISH" ] && [ "$intent" != "DIRECT_DOWNLOAD" ]; then
  block "workflow_intent missing; refusing to infer or upgrade legacy job"
fi

notify RESUMING "intent=${intent}; durable_state=${mac_state}; resume completed steps only"

handoff_fresh() {
  [ -f "$HANDOFF" ] || return 1
  python3 - "$HANDOFF" "$NOW_EPOCH" <<'PY'
import json,sys,time
path,override=sys.argv[1:]
try: d=json.load(open(path,encoding='utf-8'))
except Exception: raise SystemExit(1)
now=int(override) if override else int(time.time())
exp=int(d.get('expires_at') or 0)
raise SystemExit(0 if exp > now + 30 else 1)
PY
}

refresh_export_if_needed() {
  if handoff_fresh; then
    return 0
  fi
  case "$mac_state" in
    EXPORTED|AWAITING_APPROVAL)
      if [ "$intent" = "DIRECT_DOWNLOAD" ]; then
        bash "$PIPELINE_CMD" direct-export "$JOB_ID" >/dev/null || block "unable to refresh expired direct-download handoff"
      else
        bash "$PIPELINE_CMD" export "$JOB_ID" >/dev/null || block "unable to refresh expired handoff"
      fi
      mac_state="$(python3 - "$STATE" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8')).get('state',''))
PY
)"
      ;;
    *)
      block "handoff expired/missing and Mac state is not safely re-exportable: $mac_state"
      ;;
  esac
}

manifest_url() {
  python3 - "$HANDOFF" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8'))['manifest_url'])
PY
}

if [ "$intent" = "DIRECT_DOWNLOAD" ]; then
  case "$mac_state" in
    DIRECT_DOWNLOADED)
      emit "{\"status\":\"ALREADY_COMPLETE\",\"job_id\":\"$JOB_ID\",\"workflow_intent\":\"DIRECT_DOWNLOAD\"}"
      exit 0
      ;;
    DOWNLOADED)
      if ! bash "$PIPELINE_CMD" direct-export "$JOB_ID" >/dev/null; then
        waiting "direct-download capability export still unavailable; original MP4 remains on Mac"
      fi
      mac_state="EXPORTED"
      ;;
    EXPORTED)
      ;;
    *)
      block "DIRECT_DOWNLOAD resume only allows DOWNLOADED/EXPORTED; current=$mac_state"
      ;;
  esac
  refresh_export_if_needed
  if ! bash "$DIRECT_CMD" "$JOB_ID" Y700Agent; then
    waiting "Y700 direct-download handoff did not complete; keep Mac original and retry 继续任务 / Resume Task after connectivity returns"
  fi
  exit 0
fi

if [ "$intent" = "STORE_ALBUM" ]; then
  case "$mac_state" in
    STORED_IN_ALBUM)
      emit "{\"status\":\"ALREADY_COMPLETE\",\"job_id\":\"$JOB_ID\",\"workflow_intent\":\"STORE_ALBUM\"}"
      exit 0
      ;;
    EXPORTED)
      ;;
    *)
      block "STORE_ALBUM resume only allows EXPORTED; current=$mac_state"
      ;;
  esac
  refresh_export_if_needed
  if ! bash "$ALBUM_CMD" "$JOB_ID" Y700Agent; then
    waiting "Y700 album handoff did not complete; keep Mac artifacts and retry 继续任务 / Resume Task after connectivity returns"
  fi
  exit 0
fi

# AUTO_PUBLISH: publication history must dominate retries. Never repull/re-export
# after a COMMIT manifest or ambiguous/published state is observed.
case "$mac_state" in
  VERIFIED|PUBLISHED)
    bash "$CLOSURE_CMD" "$JOB_ID" >/dev/null 2>&1 || true
    emit "{\"status\":\"ALREADY_PUBLISHED_OR_CLOSING\",\"job_id\":\"$JOB_ID\"}"
    exit 0
    ;;
  EXPORTED|AWAITING_APPROVAL|APPROVED)
    ;;
  STORED_IN_ALBUM|DIRECT_DOWNLOADED)
    block "non-publish terminal job cannot be resumed as AUTO_PUBLISH"
    ;;
  *)
    block "AUTO_PUBLISH resume does not accept Mac state=$mac_state"
    ;;
esac

status_json=""
if ! status_json="$(remote "cd /opt/y700/workspaces/y700-agent && ./scripts/publish-status.sh '$JOB_ID'" 2>/dev/null)"; then
  waiting "Y700 is unreachable; no publish action was attempted"
fi

read_remote() {
  python3 - "$status_json" <<'PY'
import json,sys
try: d=json.loads(sys.argv[1])
except Exception: print('INVALID - false false')
else:
    print(d.get('status',''), d.get('publish_mode') or '-', 'true' if d.get('ready') else 'false', 'true' if d.get('published') else 'false')
PY
}
read -r remote_status publish_mode ready published < <(read_remote)

case "$remote_status" in
  PUBLISHED)
    bash "$CLOSURE_CMD" "$JOB_ID" >/dev/null 2>&1 || true
    emit "{\"status\":\"PUBLICATION_CLOSURE_STARTED\",\"job_id\":\"$JOB_ID\",\"reason\":\"already_published\"}"
    exit 0
    ;;
  AMBIGUOUS_COMMIT_NEEDS_RECONCILE)
    bash "$CLOSURE_CMD" "$JOB_ID" >/dev/null 2>&1 || true
    notify RESUME_WAITING "检测到 COMMIT 模糊状态；已转 reconciliation，禁止重复 COMMIT"
    emit "{\"status\":\"RECONCILE_REQUIRED\",\"job_id\":\"$JOB_ID\"}"
    exit 0
    ;;
esac
if [ "$publish_mode" = "COMMIT" ]; then
  bash "$CLOSURE_CMD" "$JOB_ID" >/dev/null 2>&1 || true
  notify RESUME_WAITING "Y700 manifest 已进入 COMMIT；仅允许 closure/reconcile，禁止普通 resume 重试"
  emit "{\"status\":\"RECONCILE_REQUIRED\",\"job_id\":\"$JOB_ID\",\"reason\":\"manifest_commit\"}"
  exit 0
fi

# Ensure a fresh capability handoff only while still positively pre-COMMIT.
if [ "$ready" != "true" ]; then
  refresh_export_if_needed
  url="$(manifest_url)"
  if ! remote "cd /opt/y700/workspaces/y700-agent && python3 publisher/pull_job.py '$url'" >/dev/null 2>&1; then
    waiting "Y700 pull failed before DRY_RUN; safe to retry /resume later"
  fi
fi

# Re-read after pull and decide whether a DRY_RUN must be started.
if ! status_json="$(remote "cd /opt/y700/workspaces/y700-agent && ./scripts/publish-status.sh '$JOB_ID'" 2>/dev/null)"; then
  waiting "lost Y700 connectivity before DRY_RUN"
fi
read -r remote_status publish_mode ready published < <(read_remote)

if [ "$remote_status" = "DRY_RUN_PASS" ] || { [ "$remote_status" = "READY_TO_COMMIT" ] && [ "$publish_mode" = "DRY_RUN" ]; }; then
  :
elif [ "$remote_status" = "RUNNING" ]; then
  :
elif [ "$publish_mode" = "DRY_RUN" ] && [[ "$remote_status" == FAILED || "$remote_status" == IDLE || "$remote_status" == STOPPED_* || "$remote_status" == OTHER_JOB ]]; then
  # One resume invocation may start at most one new DRY_RUN attempt. DRY_RUN has
  # no irreversible publish side effect.
  if ! remote "cd /opt/y700/workspaces/y700-agent && ./scripts/publish-async.sh '$JOB_ID'" >/dev/null 2>&1; then
    waiting "unable to start retry-safe DRY_RUN"
  fi
else
  block "unexpected Y700 pre-COMMIT state: status=$remote_status mode=$publish_mode"
fi

# Wait for the retry-safe phase only. Once COMMIT is armed, hand off immediately
# to the existing detached publication closure/reconciliation controller.
deadline=$(( $(date +%s) + TIMEOUT_SEC ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if ! status_json="$(remote "cd /opt/y700/workspaces/y700-agent && ./scripts/publish-status.sh '$JOB_ID'" 2>/dev/null)"; then
    sleep "$POLL_SEC"
    continue
  fi
  read -r remote_status publish_mode ready published < <(read_remote)
  case "$remote_status" in
    DRY_RUN_PASS)
      if [ "$publish_mode" != "DRY_RUN" ]; then
        block "DRY_RUN_PASS reported with non-DRY_RUN manifest"
      fi
      current_mac="$(python3 - "$STATE" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8')).get('state',''))
PY
)"
      if [ "$current_mac" = "EXPORTED" ]; then
        bash "$PIPELINE_CMD" mark-dryrun "$JOB_ID" --y700-job-id "$JOB_ID" >/dev/null
        current_mac="AWAITING_APPROVAL"
      fi
      if [ "$current_mac" = "AWAITING_APPROVAL" ]; then
        bash "$PIPELINE_CMD" approve "$JOB_ID" --note 'original AUTO_PUBLISH workflow intent resumed from Telegram' >/dev/null
        current_mac="APPROVED"
      fi
      if [ "$current_mac" != "APPROVED" ]; then
        block "Mac state cannot cross PUBLIC boundary after DRY_RUN: $current_mac"
      fi
      if ! commit_json="$(remote "cd /opt/y700/workspaces/y700-agent && ./scripts/approve-public-commit.sh '$JOB_ID' 'Telegram AUTO_PUBLISH resume standing authorization'" 2>/dev/null)"; then
        # A timeout here is deliberately not retried. The closure controller is
        # the only safe next owner because COMMIT may already have been armed.
        bash "$CLOSURE_CMD" "$JOB_ID" >/dev/null 2>&1 || true
        notify RESUME_WAITING "COMMIT 边界响应不确定；已转 closure/reconcile，禁止重复 COMMIT"
        emit "{\"status\":\"COMMIT_OUTCOME_UNKNOWN_CLOSURE_STARTED\",\"job_id\":\"$JOB_ID\"}"
        exit 0
      fi
      bash "$CLOSURE_CMD" "$JOB_ID" >/dev/null 2>&1 || true
      emit "{\"status\":\"COMMIT_STARTED_AND_CLOSURE_STARTED\",\"job_id\":\"$JOB_ID\"}"
      exit 0
      ;;
    PUBLISHED)
      bash "$CLOSURE_CMD" "$JOB_ID" >/dev/null 2>&1 || true
      emit "{\"status\":\"PUBLICATION_CLOSURE_STARTED\",\"job_id\":\"$JOB_ID\"}"
      exit 0
      ;;
    AMBIGUOUS_COMMIT_NEEDS_RECONCILE)
      bash "$CLOSURE_CMD" "$JOB_ID" >/dev/null 2>&1 || true
      emit "{\"status\":\"RECONCILE_REQUIRED\",\"job_id\":\"$JOB_ID\"}"
      exit 0
      ;;
    FAILED)
      if [ "$publish_mode" = "COMMIT" ]; then
        bash "$CLOSURE_CMD" "$JOB_ID" >/dev/null 2>&1 || true
        emit "{\"status\":\"RECONCILE_REQUIRED\",\"job_id\":\"$JOB_ID\",\"reason\":\"failed_after_commit_arm\"}"
        exit 0
      fi
      notify FAILED_SAFE "恢复中的 DRY_RUN 明确失败；未进入 COMMIT，可稍后再次 继续任务 / Resume Task"
      emit "{\"status\":\"FAILED_SAFE\",\"job_id\":\"$JOB_ID\",\"phase\":\"DRY_RUN\"}"
      exit 1
      ;;
  esac
  sleep "$POLL_SEC"
done

waiting "resume 等待 DRY_RUN 超时；没有发起新的 COMMIT，可再次 继续任务 / Resume Task"
