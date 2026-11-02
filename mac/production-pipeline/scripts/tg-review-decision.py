#!/usr/bin/env python3
"""Bounded TG reviewer decision. Does not bypass independent semantic audit or QA."""
import argparse,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline.common import JOBS,atomic_json,read_json
from pipeline.state import Job
from pipeline.subtitle_events import digest
from pipeline.subtitle_localization import build_timeline,semantic_audit_request
from pipeline.subtitle_quality import evaluate, approve_review

def decide(job_id,decision,reviewer,reference,chat_id):
    if not re.fullmatch(r'my-\d{18,20}-v04(?:-r\d{3})?',job_id):raise ValueError('invalid review job')
    if decision not in ('英文OCR=误识别','布局=通过') and not decision.startswith('语义:'):raise ValueError('unsupported decision')
    if not re.fullmatch(r'telegram:[0-9]{4,20}',reviewer) or not re.fullmatch(r'[0-9]+',reference) or not re.fullmatch(r'-?[0-9]+',chat_id):
        raise ValueError('verified Telegram user, reply id and chat id required')
    job=JOBS/job_id
    state=read_json(job/'state.json',{})
    if state.get('subtitle_mode')!='dynamic_v04' or state.get('state') not in ('ANALYZED','LOCALIZED','RENDERED'):
        raise ValueError('not a pending dynamic subtitle job')
    if decision.startswith('语义:'):
        from pipeline.semantic_transport import invoke_json
        from pipeline.subtitle_localization import validate_response
        pattern=re.fullmatch(r'语义:(evt-[0-9a-f]{16}):含义=(.{4,180})',decision,flags=re.DOTALL)
        if not pattern:raise ValueError('semantic review syntax invalid')
        eid,meaning=pattern.groups()
        journal=job/'production/tg-semantic-decisions.json'
        if journal.exists():
            previous=read_json(journal,{})
            if (previous.get('status')=='APPLIED' and previous.get('message_reference')==reference and
                previous.get('reviewer')==reviewer and previous.get('event_id')==eid and previous.get('meaning')==meaning):
                return {'job_id':job_id,'already_applied':True,'status':'REVIEW_RECORDED'}
            raise ValueError('conflicting or partial semantic decision; manual reconciliation required')
        if state.get('state')=='RENDERED':raise ValueError('cannot change already-rendered semantic content')
        evidence=read_json(job/'production/tg-semantic-evidence.json',{})
        audit=read_json(job/'localization/semantic_audit.json',{})
        if (evidence.get('job_id')!=job_id or evidence.get('event_id')!=eid or
            str(evidence.get('message_id'))!=reference or str(evidence.get('chat_id'))!=chat_id or
            evidence.get('audit_request_sha256')!=audit.get('audit_request_sha256')):
            raise ValueError('semantic review not bound to current evidence')
        if not any(x.get('event_id')==eid and x.get('verdict') in ('uncertain','fail') for x in audit.get('findings',[])):
            raise ValueError('semantic issue no longer pending')
        ledger=read_json(job/'analysis/fused_events.zh.json')
        timeline=read_json(job/'localization/subtitle_timeline.json')
        source=next(e for e in ledger['canonical_events'] if e['event_id']==eid)
        request={'target_events':[{'event_id':eid,'text_zh':source['text_zh'],'human_verified_meaning':meaning}],
                 'instruction':'Translate this one Chinese subtitle into natural Burmese. Human-verified meaning is authoritative context, not a change to source text. Return only translations=[{event_id,text_my}].'}
        answer=invoke_json(request,role='translate')
        correction=validate_response(request,answer)[eid]
        translations={e['event_id']:e.get('localization',{}).get('text_my') for e in timeline['events'] if e['fact_disposition']=='translate_target'}
        translations[eid]=correction
        source['human_verified_meaning']=meaning
        bundle={'canonical_lock':ledger['canonical_lock'],'fused_events_sha256':digest(ledger),
                'translations':[{'event_id':key,'text_my':value} for key,value in translations.items()],
                'caption_my':timeline['caption_my'],'title_my':timeline['title_my'],
                'visibility':timeline['visibility'],'render_preset':timeline['render_preset']}
        revised,projection=build_timeline(ledger,bundle)
        new_audit_request=semantic_audit_request(ledger,translations)
        atomic_json(journal,{'job_id':job_id,'event_id':eid,'meaning':meaning,
                             'reviewer':reviewer,'message_reference':reference,
                             'translation':correction,'status':'PREPARED'})
        atomic_json(job/'analysis/fused_events.zh.json',ledger)
        atomic_json(job/'localization/subtitle_timeline.json',revised)
        atomic_json(job/'localization/localization.json',projection)
        atomic_json(job/'localization/semantic_audit_request.json',new_audit_request)
        for filename in ('semantic_audit.json','semantic_audit_attempts.json','semantic_repair_request.json','semantic_repair_response.json'):
            (job/'localization'/filename).unlink(missing_ok=True)
        record=read_json(journal);record['status']='APPLIED';atomic_json(journal,record)
        qa=evaluate(job)
        return {'job_id':job_id,'semantic_review_recorded':True,'status':qa['status'],'codes':qa['codes']}
    if decision == '布局=通过':
        evidence=read_json(job/'production/tg-layout-evidence.json',{})
        report=read_json(job/'production/quality_report.json',{})
        if (evidence.get('job_id')!=job_id or str(evidence.get('message_id'))!=reference or
            str(evidence.get('chat_id'))!=chat_id or
            evidence.get('evidence_revision')!=report.get('evidence_revision')):
            raise ValueError('layout review does not match current Telegram evidence and quality revision')
        approved=read_json(job/'production/quality-approvals.json',{})
        if any(x.get('code')=='REVIEW_REQUIRED_LAYOUT' and x.get('evidence_revision')==report.get('evidence_revision')
               and x.get('reviewer')==reviewer for x in approved.get('approvals',[])):
            return {'job_id':job_id,'already_applied':True,'status':'REVIEW_RECORDED'}
        if state.get('state')=='RENDERED':raise ValueError('cannot add new approval to rendered job')
        if 'REVIEW_REQUIRED_LAYOUT' not in report.get('codes',[]):
            raise ValueError('layout review is no longer pending')
        approve_review(job,code='REVIEW_REQUIRED_LAYOUT',reviewer=reviewer,
            reason='Telegram layout evidence message '+reference+' explicitly accepted by reviewer '+reviewer)
        after=evaluate(job)
        return {'job_id':job_id,'status':after['status'],'codes':after['codes'],'reviewed':'REVIEW_REQUIRED_LAYOUT'}
    if state.get('state')=='RENDERED':raise ValueError('cannot change already-rendered OCR evidence')
    ledger=read_json(job/'analysis/fused_events.zh.json')
    timeline=read_json(job/'localization/subtitle_timeline.json')
    if not ledger or not timeline:raise ValueError('missing evidence')
    evidence=read_json(job/'production/tg-review-evidence.json',{})
    if (evidence.get('job_id') != job_id or str(evidence.get('message_id')) != reference or
        str(evidence.get('chat_id')) != chat_id or evidence.get('review_kind') != 'latin_ocr'):
        raise ValueError('Telegram reply does not match this job evidence message')
    record=job/'production/tg-human-decisions.json'
    if record.exists():
        prev=read_json(record,{})
        if (prev.get('decision')==decision and prev.get('message_reference')==reference and
            prev.get('reviewer')==reviewer and prev.get('status')=='APPLIED'):
            return {'job_id':job_id,'already_applied':True,'status':'REVIEW_RECORDED'}
        raise ValueError('prior decision exists; stop for reconciliation')
    targets=[e for e in ledger['canonical_events'] if e['fact_disposition']=='review_required' and 'LATIN_ONLY_OCR_REVIEW' in e.get('review_flags',[])]
    if not targets:raise ValueError('no pending matching OCR reviews')
    if {e['event_id'] for e in targets} != set(evidence.get('event_ids', [])):
        raise ValueError('review event set changed; resend evidence')
    old={e['event_id']:e.get('localization',{}).get('text_my') for e in timeline['events'] if e['fact_disposition']=='translate_target'}
    ids={e['event_id'] for e in targets}
    source_lock=ledger['canonical_lock']
    for e in targets:
        e['fact_disposition']='excluded_with_reason'
        e['exclude_reason']='NON_SEMANTIC_DECORATION'
        e['review_flags']=[x for x in e.get('review_flags',[]) if x not in ('SHORT_EVENT_REVIEW','LATIN_ONLY_OCR_REVIEW')]
    ledger['canonical_lock']=digest([(e['event_id'],e['start'],e['end'],e['source_refs'],e['fact_disposition']) for e in ledger['canonical_events']])
    bundle={'canonical_lock':ledger['canonical_lock'],'fused_events_sha256':digest(ledger),
        'translations':[{'event_id':k,'text_my':v} for k,v in old.items() if v],
        'caption_my':timeline['caption_my'],'title_my':timeline['title_my'],
        'visibility':timeline['visibility'],'render_preset':timeline['render_preset']}
    updated,projection=build_timeline(ledger,bundle)
    atomic_json(job/'analysis/fused_events.zh.json',ledger)
    atomic_json(job/'localization/subtitle_timeline.json',updated)
    atomic_json(job/'localization/localization.json',projection)
    atomic_json(job/'localization/semantic_audit_request.json',semantic_audit_request(ledger,old))
    (job/'localization/semantic_audit.json').unlink(missing_ok=True)
    Job(job_id).write_state('LOCALIZED')
    atomic_json(record,{'schema_version':1,'job_id':job_id,'reviewer':reviewer,'message_reference':reference,
        'decision':decision,'event_ids':sorted(ids),'source_canonical_lock':source_lock,
        'updated_canonical_lock':ledger['canonical_lock'],'status':'APPLIED'})
    report=evaluate(job)
    return {'job_id':job_id,'excluded_ids':sorted(ids),'status':report['status'],'codes':report['codes'],
            'next':'run independent semantic-audit-auto; then review remaining layout evidence'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('job_id');p.add_argument('decision');p.add_argument('--reviewer',required=True);p.add_argument('--message-reference',required=True);p.add_argument('--chat-id',required=True)
 a=p.parse_args()
 try:print(json.dumps(decide(a.job_id,a.decision,a.reviewer,a.message_reference,a.chat_id),ensure_ascii=False))
 except Exception as e:print(json.dumps({'status':'REVIEW_BLOCKED','reason':str(e)}),file=sys.stderr);raise SystemExit(1)
