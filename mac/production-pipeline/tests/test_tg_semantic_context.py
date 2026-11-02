"""A human-verified semantic correction survives the independent repair loop."""
from pipeline.subtitle_localization import semantic_repair_request

def test_repair_carries_human_verified_source_context():
    request={'audit_request_sha256':'source-lock','pairs':[{'event_id':'evt-a','text_zh':'脊背龙','text_my':'နဂါး'}],
             'verified_source_context':[{'event_id':'evt-a','meaning':'Cat arches its back like a dinosaur'}]}
    audit={'audit_request_sha256':'source-lock','findings':[{'event_id':'evt-a','verdict':'uncertain','reason':'creature ambiguous'}]}
    repair=semantic_repair_request(request,audit)
    assert repair['verified_source_context']==request['verified_source_context']
    assert 'Human-verified source context is authoritative' in repair['instruction']
