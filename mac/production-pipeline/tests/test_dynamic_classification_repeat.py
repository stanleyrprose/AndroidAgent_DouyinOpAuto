from pipeline.subtitle_events import _latin_visual_disposition, fuse_events, EventRules


def test_latin_only_ocr_requires_review_not_invalid_translation():
    event={'text_zh':'IS INSPIRATION','start':12.25,'end':12.5}
    assert _latin_visual_disposition(event)[0]=='review_required'
    assert _latin_visual_disposition({**event,'text_zh':'15 ISPIRATION'})[0]=='review_required'
    assert _latin_visual_disposition({**event,'text_zh':'猫皮子讨封啦'})[0]=='translate_target'
    assert _latin_visual_disposition({**event,'text_zh':'Cat is funny','end':15})[0]=='review_required'


def test_fusion_preserves_latin_evidence_but_requires_adjudication():
    source={'source_id':'ocr-1','source_kind':'visual_text','text_zh':'IS INSPIRATION',
            'start':12.25,'end':12.5,'bbox_norm':[.1,.1,.3,.2],
            'source_refs':['frame#12'],'review_flags':[]}
    ledger=fuse_events([], [source],source_sha256='sha',duration=70,rules=EventRules())
    row=ledger['canonical_events'][0]
    assert row['fact_disposition']=='review_required'
    assert row['text_zh']=='IS INSPIRATION'
    assert 'LATIN_ONLY_OCR_REVIEW' in row['review_flags']
