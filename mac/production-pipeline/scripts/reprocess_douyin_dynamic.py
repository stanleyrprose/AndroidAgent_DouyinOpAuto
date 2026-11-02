#!/usr/bin/env python3
"""Explicit repeat intent: re-download source and create a distinct dynamic_v04 job."""
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


def reprocess(url):
    found=re.search(r'(?:share/video/|video/)(\d{18,20})',url)
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
        got=extract_aweme_id(str(video)) or extract_aweme_id(json.dumps(result,ensure_ascii=False))
        if got != aweme:
            raise RuntimeError('source Aweme ID mismatch; refusing incorrect video')
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
    try:print(json.dumps(reprocess(sys.argv[1]),ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'status':'REPROCESS_BLOCKED','reason':type(exc).__name__}),file=sys.stderr)
        raise SystemExit(4)
