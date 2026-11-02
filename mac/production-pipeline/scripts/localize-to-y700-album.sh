#!/usr/bin/env bash
# Existing dynamic-v04 processing; Telegram-only video delivery; no publication path.
set -euo pipefail
umask 0077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${1:-}"
ALBUM="${2:-Y700Agent}"
PRESET="${3:-dynamic_clean}"
REPEAT="${4:-normal}"
if [[ -z "$URL" || ! "$ALBUM" =~ ^[A-Za-z0-9._-]{1,64}$ ]] || [[ "$PRESET" != dynamic_clean && "$PRESET" != dynamic_fun ]] || [[ "$REPEAT" != normal && "$REPEAT" != repeat ]]; then
  echo 'usage: localize-to-y700-album.sh <douyin_url> [album] [dynamic_clean|dynamic_fun]' >&2
  exit 2
fi
PIPE="${Y700_PIPELINE_CMD:-$ROOT/scripts/pipeline.sh}"
DELIVER="${Y700_TG_DELIVER_CMD:-$ROOT/scripts/deliver-video-tg.py}"
NOTIFY="${Y700_TG_NOTIFY:-$ROOT/scripts/tg-notify.sh}"
QA_JOBS_ROOT="${Y700_TG_QA_JOBS_ROOT:-$ROOT/runtime/jobs}"
# Explicit repeat is versioned and re-downloads its source because prior task media is deleted after TG receipt.
if [[ "$REPEAT" == repeat ]]; then
  response="$("$ROOT/.venv/bin/python" "$ROOT/scripts/reprocess_douyin_dynamic.py" "$URL")" || { echo "$response" >&2; exit 3; }
  submit_rc=0
else
  set +e
  response="$(bash "$PIPE" submit "$URL" --dynamic-subtitles)"
  submit_rc=$?
  set -e
fi
if [ "$submit_rc" -eq 10 ]; then
  existing_id="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("job_id", "") if d.get("status")=="DUPLICATE" else "")' <<<"$response" 2>/dev/null || true)"
  # Existing direct-download jobs and legacy album jobs have independent intents.
  if [[ "$existing_id" == dd-* ]]; then
    response="$(bash "$PIPE" submit "$URL" --dynamic-subtitles --allow-duplicate)" || { echo "$response" >&2; exit 3; }
    submit_rc=0
  elif [[ "$existing_id" =~ ^dy-[0-9]{18,20}$ ]]; then
    extra=()
    if [[ "$REPEAT" == repeat ]]; then extra=(--repeat); fi
    response="$("$ROOT/.venv/bin/python" "$ROOT/scripts/upgrade_legacy_to_dynamic.py" "$existing_id" "${extra[@]}")" || {
      echo "$response" >&2
      bash "$NOTIFY" QUALITY_REVIEW_REQUIRED "$existing_id" --detail '历史任务升级失败；未覆盖旧任务，也未向Y700交付视频' || true
      exit 3
    }
    if [[ "$response" == *'"status": "EXISTING_DYNAMIC_JOB"'* ]]; then
      echo "$response" >&2
      bash "$NOTIFY" QUALITY_REVIEW_REQUIRED "$existing_id" --detail '新版升级任务已存在；必须按状态恢复，禁止再次创建或重复投递' || true
      exit 3
    fi
    submit_rc=0
  fi
fi
if [ "$submit_rc" -ne 0 ]; then echo "$response" >&2; exit 3; fi
job_id="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("job_id","") if d.get("status")=="ANALYZED" and d.get("subtitle_mode")=="dynamic_v04" else "")' <<<"$response")"
if [[ ! "$job_id" =~ ^[A-Za-z0-9._-]+$ ]]; then echo "$response" >&2; exit 4; fi
bash "$PIPE" set-intent "$job_id" STORE_ALBUM >/dev/null
# Translation headings are presentation metadata; semantic audit evaluates each event.
# Translation's independent auditor may return 20 for REVIEW_REQUIRED, even when
# every translated sentence is semantically PASS. Inspect the actual QA codes.
set +e
bash "$PIPE" translate-auto "$job_id" --title-my 'မြန်မာစာတန်းထိုး ဗီဒီယို' --caption-my 'မြန်မာစာတန်းထိုး' --render-preset "$PRESET" --audit
translate_rc=$?
set -e
if [[ "$translate_rc" != 0 && ! -f "$QA_JOBS_ROOT/$job_id/production/quality_report.json" ]]; then
  bash "$NOTIFY" FAILED_SAFE "$job_id" --detail '翻译服务或语义检查失败；保留任务媒体与原因' || true
  exit 5
fi
# Refresh state regardless of the return code from semantic-audit-auto.
bash "$PIPE" quality-check "$job_id" >/dev/null || true
qa="$QA_JOBS_ROOT/$job_id/production/quality_report.json"
status="$("$ROOT/.venv/bin/python" -c 'import json,sys;print(json.load(open(sys.argv[1])).get("status","UNKNOWN"))' "$qa")"
if [[ "$status" != PASS ]]; then
  codes="$("$ROOT/.venv/bin/python" -c 'import json,sys;print(",".join(json.load(open(sys.argv[1])).get("codes",[])))' "$qa")"
  if [[ "$codes" == *BLOCKED_SEMANTIC* || "$codes" == *BLOCKED_UNRESOLVED_EVENT* || "$codes" == *REVIEW_REQUIRED_OCR* ]]; then
    /opt/anaconda3/bin/python3 "$ROOT/scripts/tg-review-next.py" "$job_id" || true
  elif [[ "$status" == REVIEW_REQUIRED && "$codes" == *REVIEW_REQUIRED_LAYOUT* ]]; then
    /opt/anaconda3/bin/python3 "$ROOT/scripts/tg-layout-evidence.py" "$job_id" || true
  else
    /opt/anaconda3/bin/python3 "$ROOT/scripts/tg-review-next.py" "$job_id" || true
  fi
  bash "$NOTIFY" QUALITY_REVIEW_REQUIRED "$job_id" --detail "当前状态=${status}，${codes}；请在TG直接回复审核证据，继续现有Job" || true
  exit 20
fi
if ! bash "$PIPE" render "$job_id"; then
  bash "$NOTIFY" QUALITY_REVIEW_REQUIRED "$job_id" --detail '视频渲染失败，保留媒体与审核证据' || true
  exit 7
fi
if ! bash "$PIPE" quality-check "$job_id" >/dev/null; then
  bash "$NOTIFY" QUALITY_REVIEW_REQUIRED "$job_id" --detail '渲染后独立质量审核未通过，文件保留' || true
  exit 7
fi
# Telegram is the sole delivery destination; no Y700 album/TikTok action.
if ! "${Y700_TG_DELIVER_PYTHON:-$ROOT/.venv/bin/python}" "$DELIVER" "$job_id" localized; then
  bash "$NOTIFY" FAILED_SAFE "$job_id" --detail 'TG 视频投递未确认，文件保留，禁止自动重发' || true
  exit 8
fi
