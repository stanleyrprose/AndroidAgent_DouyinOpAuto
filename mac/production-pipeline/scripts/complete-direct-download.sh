#!/bin/bash
set -euo pipefail
umask 0077

PIPE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JOB_ID="${1:-}"
ALBUM="${2:-Y700Agent}"
if [ -z "$JOB_ID" ] || [[ ! "$JOB_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "usage: complete-direct-download.sh <job_id> [album]" >&2
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
RECEIPT="$JOB_DIR/direct-download-closure.json"

if [ ! -f "$HANDOFF" ]; then
  echo "missing handoff for job $JOB_ID" >&2
  exit 3
fi

bash "$PIPELINE_CMD" set-intent "$JOB_ID" DIRECT_DOWNLOAD >/dev/null

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

bash "$TG_NOTIFY" TRANSFERRING "$JOB_ID" --detail "正在把原始抖音视频传输到 Y700 相册 $ALBUM" >/dev/null || true

remote "cd /opt/y700/workspaces/y700-agent && python3 scripts/pull-artifact-bundle.py --manifest-url '$manifest_url' --target-root /opt/y700/runtime/direct-download" >/dev/null
store_json="$(remote "cd /opt/y700/workspaces/y700-agent && ./scripts/store-direct-download.sh '$JOB_ID' '$ALBUM'")"

read -r status device_path < <(python3 - "$store_json" <<'PY'
import json,sys
try: d=json.loads(sys.argv[1])
except Exception: print('INVALID -')
else: print(d.get('status',''), d.get('device_path','-'))
PY
)
if [ "$status" != "DIRECT_DOWNLOADED" ]; then
  bash "$TG_NOTIFY" FAILED_SAFE "$JOB_ID" --detail "直接下载未完成；未启动 Notes/TikTok，也没有发布动作" >/dev/null || true
  printf '%s\n' "$store_json" >&2
  exit 4
fi

bash "$PIPELINE_CMD" mark-direct-downloaded "$JOB_ID" --album "$ALBUM" --device-path "$device_path" >/dev/null
notify_json="$(bash "$TG_NOTIFY" DIRECT_DOWNLOADED "$JOB_ID" --detail "原始抖音视频已保存到 Y700 / Movies/$ALBUM；未分析、未翻译、未写 Notes、未启动 TikTok" || true)"
python3 - "$RECEIPT" "$JOB_ID" "$ALBUM" "$device_path" "$notify_json" <<'PY'
import json,os,sys,time
path,job,album,device,raw=sys.argv[1:]
try: notify=json.loads(raw)
except Exception: notify={"sent":False,"reason":"INVALID_NOTIFICATION_RECEIPT"}
out={
  "job_id":job,
  "status":"DIRECT_DOWNLOADED",
  "album":album,
  "device_path":device,
  "note_saved":False,
  "closed_at":time.strftime("%Y-%m-%dT%H:%M:%S%z"),
  "notification":notify,
}
tmp=path+'.tmp'
with open(tmp,'w',encoding='utf-8') as f:
    json.dump(out,f,ensure_ascii=False,indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
os.replace(tmp,path)
PY
printf '{"status":"DIRECT_DOWNLOADED","job_id":"%s","album":"%s","device_path":"%s"}\n' "$JOB_ID" "$ALBUM" "$device_path"
