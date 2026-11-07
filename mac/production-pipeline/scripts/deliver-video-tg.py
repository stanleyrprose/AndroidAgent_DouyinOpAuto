#!/usr/bin/env python3
"""Send one verified task video to Y700 Telegram; then remove task-local bulk artifacts."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline.common import JOBS, RUNTIME, MEDIA_EXPORT, atomic_json, sha256_file

SENDER=Path.home()/'Documents/mcpx-projects/macmini_automation/scripts/telegram_y700_send.py'

def cleanup_confirmed(job_id, output):
    """Finish a previously confirmed delivery without ever resending video."""
    import shutil
    job=JOBS/job_id
    review_files={'human_ocr_decision':'tg-human-decisions.json',
                  'layout_approvals':'quality-approvals.json',
                  'semantic_decision':'tg-semantic-decisions.json'}
    compact={}
    for key,filename in review_files.items():
        source=job/'production'/filename
        if source.is_file():
            try:
                record=json.loads(source.read_text())
                if key=='human_ocr_decision':
                    compact[key]={k:record.get(k) for k in ('decision','event_ids','message_reference','updated_canonical_lock','status')}
                elif key=='semantic_decision':
                    compact[key]={k:record.get(k) for k in ('event_id','message_reference','reviewer','status')}
                else:
                    compact[key]=[{k:row.get(k) for k in ('code','evidence_revision','approved_at_utc')} for row in record.get('approvals',[])]
            except (OSError,ValueError,TypeError):
                compact[key]={'status':'UNREADABLE_EVIDENCE_NOT_ARCHIVED'}
    if compact:output['review_evidence_summary']=compact
    for folder in ('source','analysis','localization','production','export','evidence'):
        path=job/folder
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
    export_cache=MEDIA_EXPORT/'exports'/job_id
    if export_cache.is_dir() and not export_cache.is_symlink():
        shutil.rmtree(export_cache)
    output['temporary_files_removed']=True
    state_file=job/'state.json'
    if state_file.is_file():
        state_data=json.loads(state_file.read_text())
        state_data.update(tg_delivery_status='TG_DELIVERED',tg_message_id=output['message_id'],
                          tg_temporary_files_removed=True)
        atomic_json(state_file,state_data)
    atomic_json(RUNTIME/'tg-delivery-receipts'/f'{job_id}.json',output)
    return output


def deliver(job_id, video_kind, *, sender=SENDER):
    if not re.fullmatch(r'[A-Za-z0-9._-]{5,100}',job_id):
        raise ValueError('invalid job ID')
    if video_kind not in ('original','localized'):
        raise ValueError('invalid kind')
    job=JOBS/job_id
    receipt=RUNTIME/'tg-delivery-receipts'/f'{job_id}.json'
    if receipt.is_file():
        previous=json.loads(receipt.read_text())
        if previous.get('accepted'):
            if not previous.get('temporary_files_removed'):
                previous=cleanup_confirmed(job_id,previous)
            return {**previous,'already_delivered':True}
        # Ambiguous sends are not safe to repeat automatically.
        raise RuntimeError('previous attempt not confirmed; manual reconciliation required')
    if not job.is_dir():
        raise FileNotFoundError('missing job')
    if video_kind=='original':
        source=json.loads((job/'source/source.json').read_text())
        video=Path(source['video_path'])
        if not video.resolve().is_relative_to(job.resolve()):
            raise ValueError('source outside task')
    else:
        state=json.loads((job/'state.json').read_text())
        if state.get('subtitle_mode')!='dynamic_v04' or state.get('state') not in ('RENDERED','EXPORTED'):
            raise ValueError('requires rendered dynamic_v04')
        qa=json.loads((job/'production/quality_report.json').read_text())
        if qa.get('status')!='PASS' or qa.get('quality_stage')!='Q3_POST_RENDER':
            raise ValueError('post-render Q3 quality gate not PASS')
        from pipeline.subtitle_quality import require_pass
        require_pass(job)
        video=job/'production/video.my.mp4'
    if not video.is_file() or video.stat().st_size<=0:
        raise FileNotFoundError('video unavailable')
    digest=sha256_file(video)
    receipt.parent.mkdir(parents=True,exist_ok=True)
    # Persist intent before network call: a crash/timeout must not cause duplicate sends.
    atomic_json(receipt,{'job_id':job_id,'accepted':False,'status':'SEND_UNCONFIRMED',
                         'sha256':digest,'kind':video_kind,'size':video.stat().st_size})
    attempt=subprocess.run([sys.executable,str(sender),'video',str(video),'--caption',
                            f'{job_id} | {video_kind} | Telegram delivery'],
                           capture_output=True,text=True,timeout=180)
    try:
        result=json.loads(attempt.stdout.strip().splitlines()[-1])
    except (ValueError,IndexError):
        result={}
    if attempt.returncode!=0 or result.get('success') is not True or not result.get('message_id'):
        raise RuntimeError('Telegram acceptance unconfirmed; files retained; do not auto-retry')
    output={'job_id':job_id,'accepted':True,'status':'TG_DELIVERED',
            'message_id':str(result['message_id']),'chat_id':str(result.get('chat_id','')),
            'sha256':digest,'kind':video_kind,'size':video.stat().st_size}
    atomic_json(receipt,output)
    return cleanup_confirmed(job_id, output)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('job_id');parser.add_argument('kind',choices=['original','localized'])
    args=parser.parse_args()
    try:
        print(json.dumps(deliver(args.job_id,args.kind),ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'status':'TG_DELIVERY_BLOCKED','job_id':args.job_id,'reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        sys.exit(1)
