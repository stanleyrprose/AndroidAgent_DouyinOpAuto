"""Human review evidence is sent only to the existing Bot, with durable receipt."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'scripts/send-subtitle-review.py'
spec = spec_from_file_location('subtitle_review_sender', MODULE)
review = module_from_spec(spec)
spec.loader.exec_module(review)


def test_packet_contains_semantic_evidence(tmp_path):
    job = tmp_path / 'job-1'
    for name, obj in {
        'production/quality_report.json': {'status':'REVIEW_REQUIRED', 'codes':['REVIEW_REQUIRED_SEMANTIC'], 'quality_stage':'Q2'},
        'localization/semantic_audit.json': {'findings':[{'event_id':'event-1','verdict':'uncertain','reason':'needs context'}]},
        'localization/subtitle_timeline.json': {'events':[{'event_id':'event-1','localization':{'text_my':'မြန်မာ'}}]},
        'analysis/fused_events.zh.json': {'canonical_events':[{'event_id':'event-1','text_zh':'中文句子'}]},
    }.items():
        path=job/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,ensure_ascii=False))
    text=review.build_packet(job)
    assert 'event-1' in text and '中文句子' in text and 'မြန်မာ' in text
    assert 'REVIEW_REQUIRED_SEMANTIC' in text
    assert '禁止' in text


def test_send_receipt_prevents_duplicate(tmp_path,monkeypatch):
    monkeypatch.setattr(review,'JOBS',tmp_path)
    job=tmp_path/'job-2';(job/'production').mkdir(parents=True)
    sender=tmp_path/'sender.py'
    sender.write_text('import json\nprint(json.dumps({"success":True,"message_id":19}))\n')
    first=review.deliver('job-2',sender=sender)
    second=review.deliver('job-2',sender=sender)
    assert first['accepted'] and first['message_id']==19
    assert second['accepted'] and second['already_sent']
    assert (job/'production/human-review.txt').is_file()


def test_no_sender_reports_not_sent(tmp_path,monkeypatch):
    monkeypatch.setattr(review,'JOBS',tmp_path)
    (tmp_path/'job-3').mkdir()
    assert not review.deliver('job-3',sender=tmp_path/'missing.py')['accepted']
