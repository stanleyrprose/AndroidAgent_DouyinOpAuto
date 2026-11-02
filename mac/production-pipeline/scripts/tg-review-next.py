#!/usr/bin/env python3
"""Send actionable Telegram evidence for the next bounded dynamic subtitle review."""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline.common import JOBS,atomic_json,read_json

SENDER=Path('/Users/xu/Documents/mcpx-projects/macmini_automation/scripts/telegram_y700_send.py')

def send(job_id):
    job=JOBS/job_id
    qa=read_json(job/'production/quality_report.json',{})
    codes=set(qa.get('codes',[]))
    if qa.get('status')=='PASS':return {'status':'PASS','job_id':job_id}
    if 'BLOCKED_UNRESOLVED_EVENT' in codes:
        from PIL import Image,ImageDraw
        ledger=read_json(job/'analysis/fused_events.zh.json',{})
        ocr=read_json(job/'analysis/ocr_observations.zh.json',{})
        pending=[e for e in ledger.get('canonical_events',[]) if e.get('fact_disposition')=='review_required']
        if not pending or not all('LATIN_ONLY_OCR_REVIEW' in e.get('review_flags',[]) for e in pending):
            return {'status':'UNSUPPORTED_REVIEW_REQUIRED','codes':sorted(codes)}
        record=job/'production/tg-review-evidence.json'
        if record.exists():return {'status':'EXISTING_OR_UNCONFIRMED_EVIDENCE','record':str(record)}
        by_event=[]
        for event in pending:
            obs=next((x for x in ocr.get('observations',[]) if any(str(x.get('observation_id')) in ref for ref in event.get('source_refs',[]))),None)
            if obs is None:
                obs=min(ocr.get('observations',[]),key=lambda x:abs(float(x.get('frame_ts',0))-float(event['start'])),default=None)
            if obs is None:return {'status':'MISSING_OCR_EVIDENCE'}
            frame=job/str(obs['evidence_frame_ref'])
            if not frame.is_file():return {'status':'MISSING_FRAME','event_id':event['event_id']}
            by_event.append((event,obs,frame))
        width=600;height=350
        sheet=Image.new('RGB',(width,height*len(by_event)),'white');draw=ImageDraw.Draw(sheet)
        for i,(event,obs,frame) in enumerate(by_event):
            image=Image.open(frame).convert('RGB');image.thumbnail((width-20,height-55))
            x0,y0=10,i*height+35;sheet.paste(image,(x0,y0))
            box=obs.get('bbox_norm') or [0,0,0,0]
            draw.rectangle([x0+box[0]*image.width,y0+box[1]*image.height,x0+box[2]*image.width,y0+box[3]*image.height],outline='red',width=3)
            draw.text((10,i*height+7),f'{float(obs["frame_ts"]):.2f}s OCR: {str(obs.get("text_zh_raw",""))[:55]}',fill='black')
        picture=job/'production/tg-review-ocr.jpg';picture.parent.mkdir(exist_ok=True);sheet.save(picture,quality=85)
        record_data={'job_id':job_id,'review_kind':'latin_ocr','event_ids':sorted(e['event_id'] for e in pending),
                     'status':'SEND_UNCONFIRMED','qa_evidence_revision':qa.get('evidence_revision')}
        atomic_json(record,record_data)
        caption=f'OCR审核 {job_id}。请看红框是否有真实需翻译文字；若确认为误识别，请【回复此图】：审核：{job_id}：英文OCR=误识别'
        kind='file';payload=str(picture)
    elif 'BLOCKED_SEMANTIC_AUDIT_UNCERTAIN' in codes or 'BLOCKED_SEMANTIC_AUDIT_FAILED' in codes:
        audit=read_json(job/'localization/semantic_audit.json',{})
        ledger=read_json(job/'analysis/fused_events.zh.json',{})
        timeline=read_json(job/'localization/subtitle_timeline.json',{})
        findings=[x for x in audit.get('findings',[]) if x.get('verdict')!='pass']
        if not findings:return {'status':'NO_SEMANTIC_FINDINGS'}
        pending=findings[0];eid=pending['event_id']
        record=job/'production/tg-semantic-evidence.json'
        if record.exists():return {'status':'EXISTING_OR_UNCONFIRMED_EVIDENCE','record':str(record)}
        source=next(e for e in ledger['canonical_events'] if e['event_id']==eid)
        target=next(e for e in timeline['events'] if e['event_id']==eid)
        caption=(f'逐句语义审核 {job_id}\n事件：{eid}\n时间：{source["start"]}–{source["end"]}s\n'
                 f'中文：{source["text_zh"]}\n缅语：{target["localization"]["text_my"]}\n'
                 f'疑点：{pending.get("reason", "语义不明确")}\n'
                 f'请【回复此消息】，用中文说明真正含义：审核：{job_id}：语义：{eid}：含义=你的中文解释。'
                 '\n系统据此重新翻译该句并独立审核；不要直接批准有争议的译文。')
        record_data={'job_id':job_id,'review_kind':'semantic_meaning','event_id':eid,
                     'audit_request_sha256':audit.get('audit_request_sha256'), 'status':'SEND_UNCONFIRMED'}
        atomic_json(record,record_data)
        kind='message';payload=caption
    elif 'REVIEW_REQUIRED_LAYOUT' in codes and not any(c.startswith('BLOCKED') for c in codes):
        return {'status':'LAYOUT_READY','job_id':job_id}
    else:
        return {'status':'UNSUPPORTED_REVIEW_REQUIRED','codes':sorted(codes)}
    completed=subprocess.run([sys.executable,str(SENDER),kind,payload]+(['--caption',caption] if kind=='file' else []),capture_output=True,text=True,timeout=90)
    try:response=json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError,ValueError):response={}
    if completed.returncode or response.get('success') is not True or not response.get('message_id'):
        return {'status':'TG_SEND_UNCONFIRMED','job_id':job_id}
    record_data.update({'message_id':str(response['message_id']),'chat_id':str(response.get('chat_id','')),'status':'SENT_CONFIRMED'})
    atomic_json(record,record_data)
    return {'status':'REVIEW_SENT','job_id':job_id,'message_id':record_data['message_id'],'review_kind':record_data['review_kind']}

if __name__=='__main__':
 try:print(json.dumps(send(sys.argv[1]),ensure_ascii=False))
 except Exception as error:print(json.dumps({'status':'REVIEW_DELIVERY_BLOCKED','reason':type(error).__name__}),file=sys.stderr);raise SystemExit(1)
