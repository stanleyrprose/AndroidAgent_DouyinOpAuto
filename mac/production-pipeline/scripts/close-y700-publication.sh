#!/bin/bash
set -euo pipefail

PIPE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JOB_ID="${1:-}"
if [ -z "$JOB_ID" ] || [[ ! "$JOB_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "usage: close-y700-publication.sh <job_id>" >&2
  exit 2
fi

RUNTIME_ROOT="${Y700_PIPE_RUNTIME_ROOT:-$PIPE_ROOT/runtime}"
JOB_DIR="$RUNTIME_ROOT/jobs/$JOB_ID"
CLOSURE="$JOB_DIR/telegram-closure.json"
PIPELINE_CMD="${Y700_PIPELINE_CMD:-$PIPE_ROOT/scripts/pipeline.sh}"
TG_NOTIFY="${Y700_TG_NOTIFY:-$PIPE_ROOT/scripts/tg-notify.sh}"
POLL_SEC="${Y700_CLOSE_POLL_SEC:-15}"
TIMEOUT_SEC="${Y700_CLOSE_TIMEOUT_SEC:-600}"
HOST="${Y700_DEPLOY_HOST:-y700dev.stanleyxyz.com}"
USER="${Y700_DEPLOY_USER:-root}"
KEY="${Y700_DEPLOY_KEY:-$HOME/.ssh/id_ed25519_y700_deploy}"
CLOUDFLARED="${CLOUDFLARED_BIN:-/opt/homebrew/bin/cloudflared}"
REMOTE_RUNNER="${Y700_REMOTE_RUNNER:-}"

mkdir -p "$JOB_DIR"

if [ -f "$CLOSURE" ]; then
  existing="$(python3 - "$CLOSURE" <<'PY'
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding='utf-8'))
except Exception:
    print('')
else:
    print(d.get('status','') if d.get('notification',{}).get('sent') else '')
PY
)"
  case "$existing" in
    PUBLISHED_VERIFIED|FAILED_SAFE|RECONCILE_REQUIRED)
      printf '{"status":"ALREADY_CLOSED","job_id":"%s","terminal":"%s"}\n' "$JOB_ID" "$existing"
      exit 0
      ;;
  esac
fi

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

write_closure() {
  local terminal="$1"
  local receipt_json="$2"
  python3 - "$CLOSURE" "$JOB_ID" "$terminal" "$receipt_json" <<'PY'
import json,os,sys,time
path,job,status,raw=sys.argv[1:]
try:
    receipt=json.loads(raw)
except Exception:
    receipt={"sent":False,"reason":"INVALID_NOTIFICATION_RECEIPT"}
out={
    "job_id":job,
    "status":status,
    "closed_at":time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "notification":receipt,
}
tmp=path+".tmp"
with open(tmp,"w",encoding="utf-8") as f:
    json.dump(out,f,ensure_ascii=False,indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())
os.replace(tmp,path)
PY
}

notify() {
  local state="$1"
  local detail="$2"
  bash "$TG_NOTIFY" "$state" "$JOB_ID" --detail "$detail"
}

status_of() {
  python3 -c 'import json,sys; print(json.load(sys.stdin).get("status",""))'
}

started_reconcile=false
deadline=$(( $(date +%s) + TIMEOUT_SEC ))
last_status=""

while [ "$(date +%s)" -lt "$deadline" ]; do
  if ! status_json="$(remote "cd /opt/y700/workspaces/y700-agent && ./scripts/publish-status.sh '$JOB_ID'" 2>/dev/null)"; then
    sleep "$POLL_SEC"
    continue
  fi
  status="$(printf '%s' "$status_json" | status_of 2>/dev/null || true)"
  last_status="$status"
  case "$status" in
    PUBLISHED)
      bash "$PIPELINE_CMD" finalize "$JOB_ID" --verified --evidence generic_profile_public_exact_caption >/dev/null
      receipt="$(notify PUBLISHED_VERIFIED 'PUBLIC；TikTok profile exact caption 已验证')"
      write_closure PUBLISHED_VERIFIED "$receipt"
      printf '{"status":"PUBLISHED_VERIFIED","job_id":"%s"}\n' "$JOB_ID"
      exit 0
      ;;
    AMBIGUOUS_COMMIT_NEEDS_RECONCILE)
      if [ "$started_reconcile" = false ]; then
        remote "cd /opt/y700/workspaces/y700-agent && ./scripts/reconcile-public-async.sh '$JOB_ID'" >/dev/null 2>&1 || true
        started_reconcile=true
      fi
      ;;
    FAILED)
      receipt="$(notify FAILED_SAFE 'Y700 publisher 明确失败，未形成可验证发布')"
      write_closure FAILED_SAFE "$receipt"
      printf '{"status":"FAILED_SAFE","job_id":"%s"}\n' "$JOB_ID"
      exit 1
      ;;
  esac
  sleep "$POLL_SEC"
done

receipt="$(notify RECONCILE_REQUIRED "Y700 状态仍需核对；last_status=${last_status:-unknown}；禁止重复 COMMIT")"
write_closure RECONCILE_REQUIRED "$receipt"
printf '{"status":"RECONCILE_REQUIRED","job_id":"%s","last_status":"%s"}\n' "$JOB_ID" "${last_status:-unknown}"
exit 6
