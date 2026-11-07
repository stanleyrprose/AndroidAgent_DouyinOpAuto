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
    # Keep historical jobs immutable. If they cannot be upgraded from saved media,
    # re-download into an independent version, binding the expected Aweme ID.
    if upgrade_result="$("$ROOT/.venv/bin/python" "$ROOT/scripts/upgrade_legacy_to_dynamic.py" "$existing_id")"; then
      response="$upgrade_result"
    else
      echo "$upgrade_result" >&2
      if ! response="$("$ROOT/.venv/bin/python" "$ROOT/scripts/reprocess_douyin_dynamic.py" "$URL" --expected-aweme-id "${existing_id#dy-}")"; then
        echo "$response" >&2
        upgrade_reason="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("reason","unknown"))' <<<"$upgrade_result" 2>/dev/null || echo unknown)"
        bash "$NOTIFY" LEGACY_UPGRADE_BLOCKED "$existing_id" --detail "升级原因=${upgrade_reason}；独立版本重新下载失败；旧任务与媒体保留，请检查下载服务后恢复" || true
        exit 3
      fi
      recovered_id="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("job_id","") if d.get("status")=="ANALYZED" and d.get("subtitle_mode")=="dynamic_v04" else "")' <<<"$response")"
      if [[ ! "$recovered_id" =~ ^my-[0-9]{18,20}-v04-r[0-9]{3}$ ]]; then
        bash "$NOTIFY" LEGACY_UPGRADE_BLOCKED "$existing_id" --detail '新版本任务回执无效；旧任务未修改，请人工核对' || true
        exit 3
      fi
      bash "$NOTIFY" RECOVERY_STARTED "$recovered_id" --detail "旧任务=${existing_id}；已独立重新下载，继续缅语化并仅投递TG" || true
    fi
    if [[ "$response" == *'"status": "EXISTING_DYNAMIC_JOB"'* ]]; then
      echo "$response" >&2
      bash "$NOTIFY" RESUME_BLOCKED "$existing_id" --detail '新版升级任务已存在；必须检查其实际状态并恢复，禁止再次创建或重复投递' || true
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
  # Only ask for human review after its exact, current evidence has a durable TG receipt.
  evidence_message_id="$(python3 - "$QA_JOBS_ROOT/$job_id" <<'PY'
import json, pathlib, sys
job=pathlib.Path(sys.argv[1])
def load(path):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError): return {}
qa=load(job/'production/quality_report.json')
codes=set(qa.get('codes',[]))
candidates=[]
if 'BLOCKED_UNRESOLVED_EVENT' in codes or 'REVIEW_REQUIRED_OCR' in codes:
    candidates.append(('tg-review-evidence.json','latin_ocr'))
if 'BLOCKED_SEMANTIC_AUDIT_UNCERTAIN' in codes or 'BLOCKED_SEMANTIC_AUDIT_FAILED' in codes:
    candidates.append(('tg-semantic-evidence.json','semantic_meaning'))
if 'REVIEW_REQUIRED_LAYOUT' in codes and not any(c.startswith('BLOCKED') for c in codes):
    candidates.append(('tg-layout-evidence.json','layout'))
for filename,kind in candidates:
    evidence=load(job/'production'/filename)
    if (evidence.get('job_id')!=job.name or evidence.get('review_kind')!=kind
        or evidence.get('status')!='SENT_CONFIRMED'
        or not str(evidence.get('message_id','')).isdigit()
        or not str(evidence.get('chat_id','')).lstrip('-').isdigit()):
        continue
    if kind=='layout' and evidence.get('evidence_revision')!=qa.get('evidence_revision'):
        continue
    if kind=='semantic_meaning' and evidence.get('audit_request_sha256')!=load(job/'localization/semantic_audit.json').get('audit_request_sha256'):
        continue
    print(evidence['message_id'])
    break
PY
)"
  if [[ -n "$evidence_message_id" ]]; then
    bash "$NOTIFY" QUALITY_REVIEW_REQUIRED "$job_id" --detail "当前状态=${status}，${codes}；请直接回复已送达的TG审核证据(message_id=${evidence_message_id})，不要回复此状态通知" || true
  else
    bash "$NOTIFY" QUALITY_BLOCKED "$job_id" --detail "当前状态=${status}，${codes}；无已确认送达的当前审核证据，暂不能人工复核；任务媒体保留待排查" || true
  fi
  exit 20
fi
if ! bash "$PIPE" render "$job_id"; then
  bash "$NOTIFY" QUALITY_BLOCKED "$job_id" --detail '视频渲染失败；不是人工复核请求，保留任务媒体与现有证据' || true
  exit 7
fi
if ! bash "$PIPE" quality-check "$job_id" >/dev/null; then
  bash "$NOTIFY" QUALITY_BLOCKED "$job_id" --detail '渲染后独立质量审核未通过；尚无可操作的人工复核通知，文件保留' || true
  exit 7
fi
# Telegram is the sole delivery destination; no Y700 album/TikTok action.
if ! "${Y700_TG_DELIVER_PYTHON:-$ROOT/.venv/bin/python}" "$DELIVER" "$job_id" localized; then
  bash "$NOTIFY" FAILED_SAFE "$job_id" --detail 'TG 视频投递未确认，文件保留，禁止自动重发' || true
  exit 8
fi
