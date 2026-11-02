#!/usr/bin/env python3
"""Create a separate v04 job from a downloaded legacy video; never rewrite it."""
import json
import os
from pathlib import Path
import re
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.analyze import analyze
from pipeline.common import atomic_json, read_json, sha256_file
from pipeline import state
from pipeline.state import Job
from pipeline.subtitle_analyze import analyze_dynamic


def upgrade(legacy_id, repeat=False):
    if not re.fullmatch(r'dy-\d{18,20}', legacy_id):
        raise ValueError('legacy ID must be an exact dy-aweme identifier')
    old = Job(legacy_id)
    old_state = old.state()
    if old_state.get('subtitle_mode') != 'legacy' or old_state.get('workflow_intent') != 'STORE_ALBUM':
        raise ValueError('only STORE_ALBUM legacy jobs are eligible')
    old_source = read_json(old.dir / 'source/source.json', {}) or {}
    source = Path(old_source.get('video_path', ''))
    if not source.is_file() or not source.resolve().is_relative_to(old.dir.resolve()):
        raise ValueError('legacy original video unavailable or outside original job')
    base_id = 'my-' + legacy_id[3:] + '-v04'
    new_id = base_id
    if repeat:
        for index in range(1, 1000):
            candidate = f'{base_id}-r{index:03d}'
            if not (state.JOBS / candidate).exists():
                new_id = candidate
                break
        else:
            raise RuntimeError('repeat job limit reached')
    new = Job(new_id)
    if new.dir.exists():
        existing_state = new.state()
        if existing_state.get('subtitle_mode') == 'dynamic_v04' and existing_state.get('workflow_intent') == 'STORE_ALBUM':
            return {'status': 'EXISTING_DYNAMIC_JOB', 'job_id': new_id, 'state': existing_state['state']}
        raise ValueError('existing upgrade job is not resumable automatically')
    new = Job.create(new_id, old_source.get('source_url', ''))
    try:
        dest = new.dir / 'source' / 'original.mp4'
        shutil.copy2(source, dest)
        if sha256_file(dest) != sha256_file(source):
            raise RuntimeError('source checksum mismatch')
        atomic_json(new.dir / 'source/source.json', {
            **old_source, 'video_path': str(dest.resolve()), 'upgrade_from': legacy_id,
        })
        from pipeline.state import set_workflow_intent
        set_workflow_intent(new, 'STORE_ALBUM')
        analysis = analyze(dest, new.dir / 'analysis', allow_no_audio=True)
        analysis = analyze_dynamic(dest, new.dir / 'analysis', analysis)
        new.write_state('ANALYZED', subtitle_mode='dynamic_v04', route=analysis['route'], upgrade_from=legacy_id)
        return {'status': 'ANALYZED', 'job_id': new_id, 'subtitle_mode': 'dynamic_v04',
                'upgrade_from': legacy_id}
    except BaseException as exc:
        new.write_state('FAILED', reason=type(exc).__name__)
        raise


if __name__ == '__main__':
    try:
        result = upgrade(sys.argv[1], repeat='--repeat' in sys.argv[2:])
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, RuntimeError, OSError) as exc:
        print(json.dumps({'status': 'BLOCKED_UPGRADE', 'reason': str(exc)}, ensure_ascii=False))
        raise SystemExit(4)
