"""Mandatory original-byte Telegram delivery before capability handoff/pull."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

from .common import atomic_json, read_json, sha256_file


class MediaDeliveryError(RuntimeError):
    pass


def _save(path, data):
    atomic_json(path, data)
    # Persist rename as well as receipt bytes before allowing a remote pull.
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _send(video: Path, chat: str) -> dict:
    token = os.environ.get('Y700_TG_BOT_TOKEN') or os.environ.get('TELEGRAM_BOT_TOKEN')
    adapter = os.environ.get('Y700_TG_MEDIA_SENDER')
    if token:
        if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token):
            raise MediaDeliveryError('INVALID_BOT_CONFIGURATION')
        # Token is stdin configuration, never argv or emitted diagnostics.
        config = f'url = "https://api.telegram.org/bot{token}/sendDocument"\n'
        filename = str(video).replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))
        command = ['curl', '--config', '-', '--silent', '--max-time', '180',
                   '--form-string', f'chat_id={chat}',
                   '--form', f'document=@"{filename}";type=video/mp4',
                   '--form-string', 'disable_content_type_detection=true']
        proc = subprocess.run(command, input=config, capture_output=True, text=True, timeout=190)
    elif adapter:
        # Explicit media-capable Hermes adapter; no guessing text-only CLI flags.
        proc = subprocess.run([adapter, '--chat-id', chat, '--document', str(video)],
                              capture_output=True, text=True, timeout=190)
    else:
        raise MediaDeliveryError('MEDIA_SENDER_NOT_CONFIGURED')
    if proc.returncode:
        raise MediaDeliveryError('DELIVERY_UNCERTAIN')
    try:
        return json.loads(proc.stdout)
    except ValueError:
        raise MediaDeliveryError('DELIVERY_UNCERTAIN') from None


def deliver(job_dir: Path, *, intent: str | None = None) -> dict:
    job_dir = job_dir.resolve(strict=True)
    state = read_json(job_dir / 'state.json', {})
    intent = intent or state.get('workflow_intent')
    if intent not in {'DIRECT_DOWNLOAD', 'STORE_ALBUM', 'AUTO_PUBLISH'}:
        raise MediaDeliveryError('WORKFLOW_INTENT_REQUIRED')
    if state.get('workflow_intent') and state['workflow_intent'] != intent:
        raise MediaDeliveryError('WORKFLOW_INTENT_MISMATCH')
    chat = state.get('telegram_chat_id') or os.environ.get('Y700_TG_CHAT_ID')
    if not isinstance(chat, (str, int)) or not re.fullmatch(r'-?[0-9]+', str(chat)):
        raise MediaDeliveryError('EXPLICIT_TELEGRAM_CHAT_REQUIRED')
    chat = str(chat)
    destination = hashlib.sha256(chat.encode()).hexdigest()
    record = job_dir / 'export' / 'telegram-media-receipt.json'
    record.parent.mkdir(parents=True, exist_ok=True)
    with (record.parent / '.telegram-media.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old = read_json(record, {})
        if intent == 'DIRECT_DOWNLOAD':
            source = read_json(job_dir / 'source' / 'source.json', {})
            video = Path(source.get('video_path', ''))
            if not video.is_file():
                candidates = list((job_dir / 'source').glob('*.mp4'))
                if len(candidates) != 1:
                    raise MediaDeliveryError('SOURCE_MP4_REQUIRED')
                video = candidates[0]
        else:
            video = job_dir / 'production' / 'video.my.mp4'
        if video.is_symlink() or not video.resolve().is_relative_to(job_dir) or video.suffix.lower() != '.mp4':
            raise MediaDeliveryError('UNSAFE_MP4_PATH')
        sha = sha256_file(video)
        identity = {'job_id': job_dir.name, 'sha256': sha, 'destination_sha256': destination,
                    'intent': intent, 'size': video.stat().st_size}
        if old and any(old.get(k) != v for k, v in identity.items()):
            raise MediaDeliveryError('RECEIPT_IDENTITY_MISMATCH')
        if old.get('status') == 'SENT' and isinstance(old.get('message_id'), int):
            return old
        if old.get('status') in {'SENDING', 'UNCERTAIN'}:
            raise MediaDeliveryError('DELIVERY_UNCERTAIN_RECONCILE_REQUIRED')
        # Cloud Bot API conservative ceiling. Never compress, split or substitute a URL.
        limit = min(int(os.environ.get('Y700_TG_MEDIA_MAX_BYTES', '49000000')), 49000000)
        if not 0 < identity['size'] <= limit:
            _save(record, {**identity, 'status': 'BLOCKED_SIZE'})
            raise MediaDeliveryError('TELEGRAM_SIZE_LIMIT')
        if not (os.environ.get('Y700_TG_BOT_TOKEN') or os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('Y700_TG_MEDIA_SENDER')):
            raise MediaDeliveryError('MEDIA_SENDER_NOT_CONFIGURED')
        for attempt in range(1, 4):
            _save(record, {**identity, 'status': 'SENDING', 'attempt': attempt})
            try:
                reply = _send(video, chat)
                if not isinstance(reply, dict):
                    raise MediaDeliveryError('DELIVERY_UNCERTAIN')
                result = reply.get('result', {})
                if reply.get('ok') is True:
                    if (not isinstance(result, dict) or not isinstance(result.get('message_id'), int)
                            or not isinstance(result.get('chat'), dict)
                            or str(result['chat'].get('id')) != chat
                            or sha256_file(video) != sha):
                        raise MediaDeliveryError('DELIVERY_UNCERTAIN')
                    receipt = {**identity, 'status': 'SENT', 'message_id': result['message_id']}
                    _save(record, receipt)
                    return receipt
                if reply.get('ok') is not False:
                    raise MediaDeliveryError('DELIVERY_UNCERTAIN')
                code = reply.get('error_code')
                _save(record, {**identity, 'status': 'REJECTED', 'error_code': code})
                if code not in {429, 500, 502, 503, 504} or attempt == 3:
                    raise MediaDeliveryError('TELEGRAM_REJECTED')
                parameters = reply.get('parameters', {})
                if not isinstance(parameters, dict):
                    raise MediaDeliveryError('INVALID_RETRY_PARAMETERS')
                delay = parameters.get('retry_after', attempt * 2)
                if not isinstance(delay, (int, float)) or not 0 <= delay <= 30:
                    raise MediaDeliveryError('RETRY_DELAY_EXCEEDS_BOUND')
                time.sleep(delay)
            except (OSError, subprocess.TimeoutExpired, MediaDeliveryError) as exc:
                if read_json(record).get('status') == 'SENDING':
                    _save(record, {**identity, 'status': 'UNCERTAIN'})
                raise MediaDeliveryError(str(exc) if isinstance(exc, MediaDeliveryError) else 'DELIVERY_UNCERTAIN') from None
        raise MediaDeliveryError('TELEGRAM_REJECTED')
