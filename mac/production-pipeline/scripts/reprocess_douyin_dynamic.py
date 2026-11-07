#!/usr/bin/env python3
"""Explicit repeat intent: re-download source and create a distinct dynamic_v04 job."""
import argparse
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline import state
from pipeline.common import atomic_json, read_json, extract_aweme_id
from pipeline.douzy import Client
from pipeline.cli import _find_video
from pipeline.analyze import analyze
from pipeline.subtitle_analyze import analyze_dynamic


def reprocess(url, expected_aweme_id=None):
    found=re.search(r'(?:share/video/|video/)(\d{18,20})',url)
    if expected_aweme_id is not None:
        if not re.fullmatch(r'\d{18,20}', expected_aweme_id):
            raise ValueError('expected Aweme ID must be numeric')
        if found and found.group(1) != expected_aweme_id:
            raise ValueError('canonical URL conflicts with expected Aweme ID')
        aweme=expected_aweme_id
    else:
        if not found:
            raise ValueError('repeat requires a canonical Douyin video URL with aweme ID')
        aweme=found.group(1)
    prefix=f'my-{aweme}-v04-r'
    for n in range(1,1000):
        job_id=f'{prefix}{n:03d}'
        if not (state.JOBS/job_id).exists():
            break
    else:
        raise RuntimeError('repeat version limit reached')
    job=state.Job.create(job_id,url)
    state.set_workflow_intent(job,'STORE_ALBUM')
    try:
        result=Client().download(url,job.dir/'source')
        video=_find_video(job.dir/'source')
        # Never match the expected ID from the parent job directory or output_dir JSON.
        # The downloaded filename or explicit Douzy metadata must identify the source.
        identifiers=[extract_aweme_id(video.name), result.get('aweme_id'), result.get('video_id')]
        identifiers={str(value) for value in identifiers if value}
        if not identifiers or identifiers!={aweme}:
            raise RuntimeError('source Aweme ID missing or mismatched; refusing unverified video')
        atomic_json(job.dir/'source/source.json',{'source_url':url,'aweme_id':aweme,
            'video_path':str(video.resolve()),'douzy_job_id':result.get('job_id')})
        analysis=analyze(video,job.dir/'analysis',allow_no_audio=True)
        analysis=analyze_dynamic(video,job.dir/'analysis',analysis)
        job.write_state('ANALYZED',subtitle_mode='dynamic_v04',route=analysis['route'])
        return {'status':'ANALYZED','job_id':job_id,'subtitle_mode':'dynamic_v04'}
    except Exception as exc:
        job.write_state('FAILED',reason=type(exc).__name__)
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('--expected-aweme-id')
    args=parser.parse_args()
    try:print(json.dumps(reprocess(args.url,expected_aweme_id=args.expected_aweme_id),ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'status':'REPROCESS_BLOCKED','reason':type(exc).__name__}),file=sys.stderr)
        raise SystemExit(4)
