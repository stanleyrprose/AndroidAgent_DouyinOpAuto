#!/bin/bash
set -euo pipefail
umask 0077

PIPE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JOB_ID="${1:-}"
ALBUM="${2:-Y700Agent}"
if [ -z "$JOB_ID" ] || [[ ! "$JOB_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "usage: store-to-y700-album.sh <job_id> [album]" >&2
  exit 2
fi
if [[ ! "$ALBUM" =~ ^[A-Za-z0-9._-]{1,64}$ ]]; then
  echo "invalid album" >&2
  exit 2
fi

RUNTIME_ROOT="${Y700_PIPE_RUNTIME_ROOT:-$PIPE_ROOT/runtime}"
JOB_DIR="$RUNTIME_ROOT/jobs/$JOB_ID"
HANDOFF="$JOB_DIR/export/handoff.json"
PIPELINE_CMD="${Y700_PIPELINE_CMD:-$PIPE_ROOT/scripts/pipeline.sh}"
TG_NOTIFY="${Y700_TG_NOTIFY:-$PIPE_ROOT/scripts/tg-notify.sh}"
HOST="${Y700_DEPLOY_HOST:-y700dev.stanleyxyz.com}"
USER="${Y700_DEPLOY_USER:-root}"
KEY="${Y700_DEPLOY_KEY:-$HOME/.ssh/id_ed25519_y700_deploy}"
CLOUDFLARED="${CLOUDFLARED_BIN:-/opt/homebrew/bin/cloudflared}"
REMOTE_RUNNER="${Y700_REMOTE_RUNNER:-}"
RECEIPT="$JOB_DIR/album-store-closure.json"

if [ ! -f "$HANDOFF" ]; then
  echo "missing handoff for job $JOB_ID" >&2
  exit 3
fi

manifest_url="$(python3 - "$HANDOFF" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding='utf-8'))['manifest_url'])
PY
)"

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

bash "$TG_NOTIFY" TRANSFERRING "$JOB_ID" --detail "正在传输到 Y700 相册 $ALBUM" >/dev/null || true

# Capability URL is intentionally never echoed. Pull is idempotent at job scope;
# album storage is non-destructive for every other file in the album.
remote "cd /opt/y700/workspaces/y700-agent && python3 publisher/pull_job.py '$manifest_url'" >/dev/null
store_json="$(remote "cd /opt/y700/workspaces/y700-agent && ./scripts/store-to-album.sh '$JOB_ID' '$ALBUM'")"

read -r status device_path note_saved < <(python3 - "$store_json" <<'PY'
import json,sys
try: d=json.loads(sys.argv[1])
except Exception: print('INVALID - false')
else: print(d.get('status',''), d.get('device_path','-'), 'true' if d.get('note_saved') is True else 'false')
PY
)
if [ "$status" != "STORED_IN_ALBUM" ] || [ "$note_saved" != "true" ]; then
  bash "$TG_NOTIFY" FAILED_SAFE "$JOB_ID" --detail "相册/便签存储未完整成功；未启动 TikTok，也没有发布动作" >/dev/null || true
  printf '%s\n' "$store_json" >&2
  exit 4
fi

bash "$PIPELINE_CMD" mark-album-stored "$JOB_ID" --album "$ALBUM" --device-path "$device_path" >/dev/null
notify_json="$(bash "$TG_NOTIFY" ALBUM_STORED "$JOB_ID" --detail "视频已保存到 Y700 / Movies/$ALBUM；缅语 Caption 已存入 ZUI 便签；未启动 TikTok" || true)"
python3 - "$RECEIPT" "$JOB_ID" "$ALBUM" "$device_path" "$notify_json" <<'PY'
import json,os,sys,time
path,job,album,device,raw=sys.argv[1:]
try: notify=json.loads(raw)
except Exception: notify={"sent":False,"reason":"INVALID_NOTIFICATION_RECEIPT"}
out={
  "job_id":job,
  "status":"STORED_IN_ALBUM",
  "album":album,
  "device_path":device,
  "note_saved":True,
  "note_app":"com.zui.notes",
  "closed_at":time.strftime("%Y-%m-%dT%H:%M:%S%z"),
  "notification":notify,
}
tmp=path+'.tmp'
with open(tmp,'w',encoding='utf-8') as f:
    json.dump(out,f,ensure_ascii=False,indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
os.replace(tmp,path)
PY
printf '{"status":"STORED_IN_ALBUM","job_id":"%s","album":"%s","device_path":"%s"}\n' "$JOB_ID" "$ALBUM" "$device_path"
