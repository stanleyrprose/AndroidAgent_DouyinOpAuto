import json
from pathlib import Path
from importlib.util import spec_from_file_location,module_from_spec
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=spec_from_file_location('tg_delivery',ROOT/'scripts/deliver-video-tg.py')
module=module_from_spec(spec);spec.loader.exec_module(module)

def test_accepted_receipt_then_cleanup(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'JOBS',tmp_path/'jobs')
    monkeypatch.setattr(module,'RUNTIME',tmp_path)
    monkeypatch.setattr(module,'MEDIA_EXPORT',tmp_path/'media')
    job=module.JOBS/'dd-1234567890123456789';(job/'source').mkdir(parents=True)
    src=job/'source/video.mp4';src.write_bytes(b'video-content')
    (job/'source/source.json').write_text(json.dumps({'video_path':str(src)}))
    for part in ['analysis','localization','production','export']:
        d=job/part;d.mkdir();(d/'work.tmp').write_bytes(b'x')
    (job/'state.json').write_text('{}')
    cache=module.MEDIA_EXPORT/'exports'/job.name;cache.mkdir(parents=True)
    (cache/'tmp').write_bytes(b'cache')
    sibling=module.MEDIA_EXPORT/'exports'/'another';sibling.mkdir()
    sender=tmp_path/'send.py';sender.write_text('print(\'{"success":true,"message_id":"42","chat_id":"123"}\')')
    out=module.deliver(job.name,'original',sender=sender)
    assert out['accepted'] and out['message_id']=='42'
    assert not (job/'source').exists() and not cache.exists()
    assert sibling.exists() and (job/'state.json').exists()
    assert (tmp_path/'tg-delivery-receipts'/f'{job.name}.json').exists()
    assert module.deliver(job.name,'original',sender=sender)['already_delivered']

def test_failed_send_keeps_video_and_blocks_retry(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'JOBS',tmp_path/'jobs')
    monkeypatch.setattr(module,'RUNTIME',tmp_path)
    job=module.JOBS/'dd-1234567890123456789';(job/'source').mkdir(parents=True)
    video=job/'source/video.mp4';video.write_bytes(b'video')
    (job/'source/source.json').write_text(json.dumps({'video_path':str(video)}))
    bad=tmp_path/'bad.py';bad.write_text('import sys;sys.exit(1)')
    with pytest.raises(RuntimeError):module.deliver(job.name,'original',sender=bad)
    assert video.exists()
    with pytest.raises(RuntimeError,match='previous attempt'):module.deliver(job.name,'original',sender=bad)

def test_localized_send_requires_post_render_q3_pass(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'JOBS',tmp_path/'jobs')
    monkeypatch.setattr(module,'RUNTIME',tmp_path)
    job=module.JOBS/'my-7597434271141216881-v04-r002'
    (job/'production').mkdir(parents=True)
    (job/'state.json').write_text(json.dumps({'subtitle_mode':'dynamic_v04','state':'RENDERED'}))
    (job/'production/quality_report.json').write_text(json.dumps({'status':'PASS','quality_stage':'Q1_Q2'}))
    (job/'production/video.my.mp4').write_bytes(b'no unverified video should be sent')
    with pytest.raises(ValueError,match='post-render Q3'):
        module.deliver(job.name,'localized',sender=tmp_path/'missing-sender')
    assert (job/'production/video.my.mp4').exists()
    assert not (tmp_path/'tg-delivery-receipts'/f'{job.name}.json').exists()
