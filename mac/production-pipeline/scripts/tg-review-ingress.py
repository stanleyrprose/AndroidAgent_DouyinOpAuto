#!/usr/bin/env python3
"""Allowlisted deterministic Telegram review dispatch, independent of LLM decisions.

This module only parses exact review commands; it cannot approve anything. The
review runner must validate evidence revisions and Telegram reply-to IDs.
"""
from __future__ import annotations
import re
import fcntl
import subprocess
from pathlib import Path

JOB = r'(my-\d{18,20}-v04(?:-r\d{3})?)'
SUPPORTED = {
    '英文OCR=误识别': '英文OCR=误识别',
    '布局=通过': '布局=通过',
}
COMMAND = re.compile(rf'^审核\s*[：:]\s*{JOB}\s*[：:]\s*(英文OCR=误识别|布局=通过)\s*$')
SEMANTIC = re.compile(rf'^审核\s*[：:]\s*{JOB}\s*[：:]\s*语义[：:]\s*(evt-[0-9a-f]{{16}})[：:]\s*含义=(.{{4,180}})$', re.DOTALL)
RUNNER = Path.home() / 'Library/Application Support/Y700Automation/AndroidAgent_DouyinOpAuto/mac/production-pipeline/scripts/tg-review-and-resume.sh'


def classify(text: str):
    stripped = text.split('  [Replied-to ', 1)[0].strip()
    match = COMMAND.fullmatch(stripped)
    if match:
        return (match.group(1), SUPPORTED[match.group(2)])
    semantic = SEMANTIC.fullmatch(stripped)
    if semantic:
        return (semantic.group(1), '语义:' + semantic.group(2) + ':含义=' + semantic.group(3))
    if stripped.startswith('审核：') or stripped.startswith('审核:'):
        return ('', '')
    return None


def dispatch(text: str, *, platform: str, chat_id: str, reply_to_id: str | None, timeout=900):
    item = classify(text)
    if item is None:
        return None
    if platform != 'telegram':
        return 'REVIEW_REJECTED: Telegram-only review command.'
    job, decision = item
    if not job or not decision:
        return 'REVIEW_REJECTED: unsupported review command; use the exact instruction shown beneath the evidence.'
    if not re.fullmatch(r'-?\d{4,20}', str(chat_id)) or not re.fullmatch(r'\d+', str(reply_to_id or '')):
        return 'REVIEW_REJECTED: use Reply on the exact evidence message for this job.'
    # Durable per-job claim prevents two TG callbacks from running the same QA
    # mutation or sending the same video concurrently. Lock releases on crash.
    lock_dir = RUNNER.parent.parent / 'runtime' / 'review-claims'
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / (job + '.lock')).open('a+') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return f'REVIEW_BUSY: {job}; another review is running; do not repeat.'
        try:
            result = subprocess.run(['bash', str(RUNNER), job, decision, str(reply_to_id), str(chat_id)],
                                    capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return f'REVIEW_IN_PROGRESS_OR_UNCONFIRMED: {job}; check job status, do not resubmit approval.'
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    if result.returncode:
        return f'REVIEW_BLOCKED: {job}; code={result.returncode}. Original media retained; check the TG status receipt.'
    return f'REVIEW_ACCEPTED: {job} / {decision}. Follow the next Telegram review or video delivery receipt; do not start a new job.'
