"""TG human review must never alter a job on unbound approval."""
import importlib.util
import json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('tg_human_review',ROOT/'scripts/tg-review-decision.py')
review=importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)

def test_no_matching_telegram_evidence_keeps_job_untouched(tmp_path,monkeypatch):
    monkeypatch.setattr(review,'JOBS',tmp_path)
    jid='my-7597434271141216881-v04-r001'
    job=tmp_path/jid
    for relative,obj in {
        'state.json':{'subtitle_mode':'dynamic_v04','state':'ANALYZED'},
        'analysis/fused_events.zh.json':{'canonical_events':[{'event_id':'e','fact_disposition':'review_required','review_flags':['LATIN_ONLY_OCR_REVIEW']}]},
        'localization/subtitle_timeline.json':{'events':[]},
        'production/tg-review-evidence.json':{'job_id':jid,'message_id':'387','chat_id':'1234','review_kind':'latin_ocr','event_ids':['e']},
    }.items():
        p=job/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj))
    ledger=(job/'analysis/fused_events.zh.json').read_bytes()
    with pytest.raises(ValueError,match='does not match'):
        review.decide(jid,'英文OCR=误识别','telegram:1234','386','1234')
    assert (job/'analysis/fused_events.zh.json').read_bytes()==ledger
    assert not (job/'production/tg-human-decisions.json').exists()

def test_unknown_review_type_never_modifies_job(tmp_path,monkeypatch):
    monkeypatch.setattr(review,'JOBS',tmp_path)
    with pytest.raises(ValueError,match='unsupported decision'):
        review.decide('my-7597434271141216881-v04-r001','语义=无条件通过','telegram:1234','387','1234')
