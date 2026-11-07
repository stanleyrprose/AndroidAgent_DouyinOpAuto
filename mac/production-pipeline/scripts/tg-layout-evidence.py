#!/usr/bin/env python3
"""Deliver concrete subtitle placement review evidence through the existing Telegram bot."""
import json,subprocess,sys,tempfile
from pathlib import Path
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline.common import JOBS,atomic_json,read_json
from pipeline.subtitle_layout import plan_timeline
from pipeline.subtitle_render import _transform

SENDER=Path.home()/'Documents/mcpx-projects/macmini_automation/scripts/telegram_y700_send.py'

def prepare(job_id):
    job=JOBS/job_id
    report=read_json(job/'production/quality_report.json',{})
    if 'REVIEW_REQUIRED_LAYOUT' not in report.get('codes',[]):raise ValueError('no pending layout review')
    evidence=job/'production/tg-layout-evidence.json'
    if evidence.exists():raise ValueError('layout evidence already sent or ambiguous; do not duplicate')
    timeline=read_json(job/'localization/subtitle_timeline.json',{})
    source=read_json(job/'source/source.json',{})
    analysis=read_json(job/'analysis/analysis.json',{})
    stream=next(x for x in analysis.get('probe',{}).get('streams',[]) if x.get('codec_type')=='video')
    placements=plan_timeline([x for x in timeline['events'] if x.get('localization',{}).get('text_my')], _transform(stream['width'],stream['height']))
    events=[x for x in timeline['events'] if x.get('localization',{}).get('text_my')]
    overlap=[(a['start']+a['end'])/2 for a in events if a['role']=='callout' and any(b['role']=='primary_subtitle' and min(a['end'],b['end'])>max(a['start'],b['start']) for b in events)]
    candidates=overlap+[e['start']+(e['end']-e['start'])/2 for e in events]
    times=[]
    for t in candidates:
        if 0<=t<float(timeline['duration_s']) and all(abs(t-x)>1 for x in times):times.append(t)
        if len(times)==3:break
    if not times:raise ValueError('no subtitle frames for layout review')
    sheet=Image.new('RGB',(540*len(times),1010),'white')
    video=Path(source['video_path'])
    with tempfile.TemporaryDirectory(prefix='tg-layout-') as d:
        for idx,t in enumerate(times):
            frame=Path(d)/f'{idx}.png'
            proc=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-ss',str(t),'-i',str(video),'-frames:v','1','-vf','scale=540:960:force_original_aspect_ratio=decrease,pad=540:960:(ow-iw)/2:(oh-ih)/2','-y',str(frame)],capture_output=True,timeout=40)
            if proc.returncode or not frame.is_file():raise RuntimeError('ffmpeg failed to render review frame')
            img=Image.open(frame).convert('RGB');draw=ImageDraw.Draw(img,'RGBA')
            for event in events:
                if not float(event['start'])<=t<=float(event['end']):continue
                place=placements[event['event_id']]
                x,y=place['x']/2,place['y']/2
                draw.rectangle([x,y,x+450,y+130],fill=(10,120,255,65),outline=(25,110,255,255),width=3)
                draw.text((x+8,y+8),'MY: '+event['event_id'][-7:],fill=(255,255,255,255))
                box=place.get('source_box')
                if box:draw.rectangle([v/2 for v in box],outline=(255,35,35,255),width=3)
            sheet.paste(img,(540*idx,35))
            draw2=ImageDraw.Draw(sheet);draw2.text((540*idx+15,10),f'{t:.2f}s | Blue=Myanmar subtitle, Red=original text',fill=(10,10,10))
    output=job/'production/tg-layout-review.jpg';sheet.save(output,quality=85)
    record={'schema_version':1,'job_id':job_id,'review_kind':'layout','evidence_revision':report['evidence_revision'],'status':'SEND_UNCONFIRMED'}
    atomic_json(evidence,record)
    response=subprocess.run([sys.executable,str(SENDER),'file',str(output),'--caption',f'布局审核 {job_id}：蓝框是拟叠加缅语字幕区域，红框是源文字。确认无冲突后请回复此图：审核：{job_id}：布局=通过'],capture_output=True,text=True,timeout=90)
    try:data=json.loads(response.stdout.strip().splitlines()[-1])
    except (ValueError,IndexError):data={}
    if response.returncode or not data.get('success') or not data.get('message_id'):
        raise RuntimeError('layout screenshot send unconfirmed; do not retry without reconciliation')
    record.update({'message_id':str(data['message_id']),'chat_id':str(data.get('chat_id')),'status':'SENT_CONFIRMED'})
    atomic_json(evidence,record)
    return {'job_id':job_id,'status':'LAYOUT_REVIEW_SENT','message_id':record['message_id']}
if __name__=='__main__':
 try:print(json.dumps(prepare(sys.argv[1]),ensure_ascii=False))
 except Exception as exc:print(json.dumps({'status':'REVIEW_EVIDENCE_BLOCKED','reason':str(exc)},ensure_ascii=False),file=sys.stderr);raise SystemExit(1)
