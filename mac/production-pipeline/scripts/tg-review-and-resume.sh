#!/usr/bin/env bash
# Deterministic continuation from a Telegram human-review decision.
set -euo pipefail
umask 0077
LIVE="$(cd "$(dirname "$0")/.." && pwd)"
RELEASE="$LIVE/releases/dynamic-v04-20261030"
PY="$RELEASE/.venv/bin/python"
PIPE="$RELEASE/scripts/pipeline.sh"
SENDER="/Users/xu/Documents/mcpx-projects/macmini_automation/scripts/telegram_y700_send.py"
JOB="${1:-}"; DECISION="${2:-}"; REPLY="${3:-}"; CHAT="${4:-}"
REVIEWER="telegram:$CHAT"
[[ "$JOB" =~ ^my-[0-9]{18,20}-v04(-r[0-9]{3})?$ ]] || { echo 'INVALID_JOB' >&2; exit 2; }
[[ "$DECISION" == '英文OCR=误识别' || "$DECISION" == '布局=通过' || "$DECISION" == 语义:* ]] || { echo 'INVALID_DECISION' >&2; exit 2; }
[[ "$REVIEWER" =~ ^telegram:[0-9]{4,20}$ && "$REPLY" =~ ^[0-9]+$ && "$CHAT" =~ ^-?[0-9]+$ ]] || { echo 'MISSING_VERIFIED_TELEGRAM_IDENTITY' >&2; exit 2; }
[[ "$RELEASE/runtime" -ef "$LIVE/runtime" ]] || { echo 'RUNTIME_MISMATCH' >&2; exit 3; }
export PATH="/opt/homebrew/bin:$PATH"
export Y700_MEDIA_EXPORT_ROOT="$LIVE/../media-export"
notify() { "$PY" "$SENDER" message "$1" >/dev/null 2>&1 || true; }
RECEIPT="$LIVE/runtime/tg-delivery-receipts/$JOB.json"
if [[ -f "$RECEIPT" ]] && "$PY" -c 'import json,sys; d=json.load(open(sys.argv[1]));sys.exit(0 if d.get("accepted") else 1)' "$RECEIPT"; then
  if ! "$PY" "$RELEASE/scripts/deliver-video-tg.py" "$JOB" localized; then
    notify "TG 视频已有成功回执，但清理尚未确认：$JOB。请检查原始回执，不可重发。"
    exit 12
  fi
  notify "该 Job 已交付 TG，清理已确认：$JOB。禁止重复投递。"
  exit 0
fi
if ! REVIEW_RESULT="$("$PY" "$RELEASE/scripts/tg-review-decision.py" "$JOB" "$DECISION" --reviewer "$REVIEWER" --message-reference "$REPLY" --chat-id "$CHAT")"; then
  notify "审核未生效：$JOB。请回复该任务原始审核图片，并使用完整审核指令。未修改质量门禁。"
  exit 4
fi
if [[ "$REVIEW_RESULT" == *'"already_applied": true'* ]]; then
  notify "已确认该审核裁决此前记录：$JOB。将检查当前任务状态，但不会再次批准或重复发送视频。"
fi
notify "已记录 Telegram 人工裁决：$JOB / $DECISION。继续执行独立语义和质量审核；不会跳过门禁。"
if [[ "$DECISION" == '英文OCR=误识别' || "$DECISION" == 语义:* ]]; then
  # semantic-audit-auto returns 20 even when semantic audit PASS but a
  # separate layout warning remains; inspect the authoritative QA codes below.
  bash "$PIPE" semantic-audit-auto "$JOB" >/dev/null || true
fi
# refresh deterministic quality truth; non-PASS returns 20.
bash "$PIPE" quality-check "$JOB" >/dev/null || true
REPORT="$LIVE/runtime/jobs/$JOB/production/quality_report.json"
STATUS="$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1])).get("status","UNKNOWN"))' "$REPORT")"
SEMANTIC_BLOCKED="$("$PY" -c 'import json,sys;codes=json.load(open(sys.argv[1])).get("codes",[]);print("yes" if any(c.startswith("BLOCKED_SEMANTIC") or c.startswith("BLOCKED_TRANSLATION") for c in codes) else "no")' "$REPORT")"
if [[ "$SEMANTIC_BLOCKED" == yes ]]; then
  /opt/anaconda3/bin/python3 "$RELEASE/scripts/tg-review-next.py" "$JOB" || true
  notify "审核进度：$JOB 语义审核仍待人工裁决。请查看 TG 审核消息，回复对应图片或文本；工作媒体保留。"
  exit 5
fi
if [[ "$STATUS" == 'REVIEW_REQUIRED' ]]; then
  HAS_LAYOUT="$("$PY" -c 'import json,sys;print("yes" if "REVIEW_REQUIRED_LAYOUT" in json.load(open(sys.argv[1])).get("codes",[]) else "no")' "$REPORT")"
  if [[ "$HAS_LAYOUT" == yes ]]; then
    if ! /opt/anaconda3/bin/python3 "$RELEASE/scripts/tg-layout-evidence.py" "$JOB"; then
      notify "审核进度：$JOB 布局尚待确认，但证据图发送未确认。保留视频材料，不自动重发。"
      exit 6
    fi
    exit 0
  fi
fi
if [[ "$STATUS" != 'PASS' ]]; then
  /opt/anaconda3/bin/python3 "$RELEASE/scripts/tg-review-next.py" "$JOB" || true
  notify "审核进度：$JOB 质量状态为 $STATUS。请查看明确的 TG 审核指令；文件保留。"
  exit 7
fi
if ! bash "$PIPE" render "$JOB"; then
  notify "审核进度：$JOB 字幕渲染失败，文件保留，未投递视频。"
  exit 8
fi
if ! bash "$PIPE" quality-check "$JOB" >/dev/null; then
  notify "审核进度：$JOB 渲染后质量门禁未通过，文件保留，未投递视频。"
  exit 9
fi
if ! "$PY" "$RELEASE/scripts/deliver-video-tg.py" "$JOB" localized; then
  notify "审核进度：$JOB Telegram 视频投递未确认，文件保留，禁止自动重发。"
  exit 10
fi
notify "✅ $JOB：Telegram 视频已被接受；已记录消息回执并执行本任务临时文件清理。"
