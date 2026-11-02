#!/usr/bin/env python3
"""Deliver concise, idempotent human review evidence to the existing Y700 TG bot.

Never changes job truth, grants QA approval, or authorizes publication.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.common import JOBS, atomic_json, read_json


def build_packet(job_dir: Path) -> str:
    qa = read_json(job_dir / 'production/quality_report.json', {}) or {}
    audit = read_json(job_dir / 'localization/semantic_audit.json', {}) or {}
    timeline = read_json(job_dir / 'localization/subtitle_timeline.json', {}) or {}
    ledger = read_json(job_dir / 'analysis/fused_events.zh.json', {}) or {}
    by_id = {x.get('event_id'): x for x in ledger.get('canonical_events', [])}
    translated = {x.get('event_id'): x for x in timeline.get('events', [])}
    lines = [f'Y700 缅语化人工审核包 | Job {job_dir.name}',
             '状态：等待人工裁决；禁止视为质量通过或 TikTok 发布授权。',
             '当前阶段：' + str(qa.get('quality_stage', 'UNKNOWN')),
             '门禁：' + str(qa.get('status', 'UNKNOWN')),
             '质量原因：' + ', '.join(map(str, qa.get('codes', []))),
             '请审核以下中文原意及对应缅语译文；只回复需要修改的事件 ID。', '']
    findings = [x for x in audit.get('findings', []) if x.get('verdict') != 'pass']
    for i, finding in enumerate(findings, 1):
        key = finding.get('event_id', '?')
        source = by_id.get(key, {})
        rendered = translated.get(key, {})
        lines += [f'{i}. event_id={key}',
                  '审核结论：' + str(finding.get('verdict', '?')),
                  '中文：' + str(source.get('text_zh') or source.get('text') or '详见原视频'),
                  '缅语：' + str(rendered.get('localization', {}).get('text_my', '未生成')),
                  '原因：' + str(finding.get('reason', '未提供')), '']
    if not findings:
        lines += ['未发现可引用的具体语义争议；请根据门禁原因核查视频或源素材。', '']
    lines += ['建议回复：Y700/Job ' + job_dir.name + '：事件ID=通过/建议修改文字；',
              '人工回复不会自动批准发布，仅作为后续修订依据。']
    return '\n'.join(lines) + '\n'


def deliver(job_id: str, *, sender: Path) -> dict:
    if not job_id or not all(c.isascii() and (c.isalnum() or c in '._-') for c in job_id):
        raise ValueError('invalid job ID')
    job_dir = JOBS / job_id
    if not job_dir.is_dir():
        raise ValueError('job not found')
    path = job_dir / 'production/human-review.txt'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_packet(job_dir), encoding='utf-8')
    receipt_path = path.with_suffix('.delivery.json')
    last = read_json(receipt_path, {}) or {}
    if last.get('accepted'):
        return {'accepted': True, 'already_sent': True, 'job_id': job_id}
    if last.get('reason') == 'TG_SEND_UNCONFIRMED_DO_NOT_AUTO_RETRY':
        return {'accepted': False, 'job_id': job_id,
                'reason': 'TG_SEND_UNCONFIRMED_DO_NOT_AUTO_RETRY'}
    if not sender.is_file():
        return {'accepted': False, 'reason': 'TG_SENDER_UNAVAILABLE', 'packet': str(path)}
    try:
        result = subprocess.run([sys.executable, str(sender), 'file', str(path),
                                 '--caption', f'缅语化 Job {job_id} 待审核（禁止自动发布）'],
                                capture_output=True, text=True, timeout=70)
        response = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
        accepted = result.returncode == 0 and response.get('success') is True
        out = {'accepted': accepted, 'job_id': job_id,
               'message_id': response.get('message_id') if accepted else None,
               'reason': None if accepted else 'TG_SEND_FAILED'}
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        out = {'accepted': False, 'job_id': job_id, 'reason': 'TG_SEND_UNCONFIRMED_DO_NOT_AUTO_RETRY'}
    atomic_json(receipt_path, out)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('job_id')
    parser.add_argument('--sender', type=Path, default=Path(os.environ.get(
        'Y700_REVIEW_TG_SENDER', '/Users/xu/Documents/mcpx-projects/macmini_automation/scripts/telegram_y700_send.py')))
    args = parser.parse_args()
    result = deliver(args.job_id, sender=args.sender)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get('accepted') else 1


if __name__ == '__main__':
    raise SystemExit(main())
