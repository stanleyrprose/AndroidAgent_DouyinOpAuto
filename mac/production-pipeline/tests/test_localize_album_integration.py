"""Contract and state-flow tests for existing Mac-to-Y700 album integration."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/localize-to-y700-album.sh'


def test_localize_album_contract():
    source = SCRIPT.read_text()
    for fragment in ('submit "$URL" --dynamic-subtitles',
                     'set-intent "$job_id" STORE_ALBUM',
                     'translate-auto "$job_id"', '--audit',
                     'quality-check "$job_id"', 'render "$job_id"',
                     '"$DELIVER" "$job_id" localized'):
        assert fragment in source
    assert 'direct-download "$URL"' not in source
    assert 'start-publication-closure' not in source


def test_invalid_input_cannot_run_remote_commands():
    result = subprocess.run(['bash', str(SCRIPT), 'https://example.invalid', 'Album!',
                             'dynamic_clean'], text=True, capture_output=True)
    assert result.returncode == 2


def test_shell_syntax():
    subprocess.run(['bash', '-n', str(SCRIPT)], check=True)


def _invoke(tmp_path, blocked_step='', duplicate_job='', confirmed_review=False):
    qa_dir=tmp_path/'jobs'/'safe-job-1'/'production'
    qa_dir.mkdir(parents=True)
    if confirmed_review:
        localization = qa_dir.parent / 'localization'
        localization.mkdir()
        (localization / 'semantic_audit.json').write_text(
            json.dumps({'audit_request_sha256': 'verified-audit'}))
        (qa_dir / 'tg-semantic-evidence.json').write_text(json.dumps({
            'job_id': 'safe-job-1', 'review_kind': 'semantic_meaning',
            'status': 'SENT_CONFIRMED', 'message_id': '123456',
            'chat_id': '7890', 'audit_request_sha256': 'verified-audit',
        }))
    pipe = tmp_path / 'pipeline.sh'
    store = tmp_path / 'album.sh'
    tg = tmp_path / 'tg.sh'
    log = tmp_path / 'events.txt'
    pipe.write_text('''#!/usr/bin/env bash
printf '%s\\n' "$1" >> "$TRACE"
if [ "$1" = submit ]; then
  if [ -n "$DUPLICATE_JOB" ] && [[ "$*" != *--allow-duplicate* ]]; then
    printf '{"status":"DUPLICATE","job_id":"%s"}\\n' "$DUPLICATE_JOB"
    exit 10
  fi
  echo '{"status":"ANALYZED","job_id":"safe-job-1","subtitle_mode":"dynamic_v04"}'
  exit 0
fi
if [ "$1" = translate-auto ]; then
  if [ "$BLOCK_STEP" = translate-auto ]; then exit 13; fi
  echo '{"status":"PASS","codes":[]}' > "$QA_DIR/quality_report.json"
fi
if [ "$1" = quality-check ] && [ "$BLOCK_STEP" = quality-check ]; then
  echo '{"status":"BLOCKED","codes":["BLOCKED_SEMANTIC_AUDIT_UNCERTAIN"]}' > "$QA_DIR/quality_report.json"
  exit 20
fi
if [ "$1" = "$BLOCK_STEP" ]; then exit 13; fi
''')
    store.write_text('''#!/usr/bin/env bash
printf 'TG_DELIVERED:%s:%s\\n' "$1" "$2" >> "$TRACE"
''')
    tg.write_text('''#!/usr/bin/env bash
printf 'NOTIFIED:%s\\n' "$1" >> "$TRACE"
''')
    env = {**os.environ,'Y700_PIPELINE_CMD':str(pipe),
           'Y700_TG_DELIVER_CMD':str(store), 'Y700_TG_DELIVER_PYTHON':'/bin/bash', 'Y700_TG_NOTIFY':str(tg),
           'TRACE':str(log),'BLOCK_STEP':blocked_step,'DUPLICATE_JOB':duplicate_job,
           'QA_DIR':str(qa_dir),'Y700_TG_QA_JOBS_ROOT':str(tmp_path/'jobs')}
    result = subprocess.run(['bash',str(SCRIPT),'https://example.invalid/abc',
                             'Y700Agent','dynamic_clean'],env=env,text=True,errors="replace",capture_output=True)
    return result, log.read_text().splitlines()


def test_success_uses_existing_album_path(tmp_path):
    result, events = _invoke(tmp_path)
    assert result.returncode == 0, result.stderr
    assert events == ['submit','set-intent','translate-auto','quality-check',
                      'render','quality-check','TG_DELIVERED:safe-job-1:localized']


def test_translation_failure_does_not_transfer(tmp_path):
    result, events = _invoke(tmp_path,'translate-auto')
    assert result.returncode == 5
    assert events[:3] == ['submit','set-intent','translate-auto']
    assert events[-1] == 'NOTIFIED:FAILED_SAFE'


def test_direct_download_duplicate_can_be_localized_separately(tmp_path):
    result, events = _invoke(tmp_path, duplicate_job='dd-1234567890123456789')
    assert result.returncode == 0, result.stderr
    assert events[:3] == ['submit', 'submit', 'set-intent']
    assert 'TG_DELIVERED:safe-job-1:localized' in events


def test_already_localized_duplicate_cannot_reprocess(tmp_path):
    result, events = _invoke(tmp_path, duplicate_job='dy-1234567890123456789')
    assert result.returncode == 3
    assert events == ['submit', 'NOTIFIED:LEGACY_UPGRADE_BLOCKED']


def test_render_failure_notifies_and_blocks_delivery(tmp_path):
    result, events = _invoke(tmp_path, 'render')
    assert result.returncode == 7
    assert 'TG_DELIVERED:safe-job-1:localized' not in events
    assert events[-1] == 'NOTIFIED:QUALITY_BLOCKED'


def test_delivery_failure_notifies_and_keeps_control(tmp_path):
    result, events = _invoke(tmp_path, 'unrelated')
    assert result.returncode == 0
    assert events[-1] == 'TG_DELIVERED:safe-job-1:localized'


def test_quality_failure_does_not_transfer(tmp_path):
    result, events = _invoke(tmp_path,'quality-check')
    assert result.returncode == 20
    assert events[:4] == ['submit','set-intent','translate-auto','quality-check']
    assert events[-1] == 'NOTIFIED:QUALITY_BLOCKED'


def test_verified_telegram_evidence_allows_actionable_review_notice(tmp_path):
    result, events = _invoke(tmp_path, 'quality-check', confirmed_review=True)
    assert result.returncode == 20
    assert events[-1] == 'NOTIFIED:QUALITY_REVIEW_REQUIRED'
    assert not any(x.startswith('TG_DELIVERED:') for x in events)
