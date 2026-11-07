"""Legacy album upgrades create isolated v04 jobs without rewriting prior output."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import pytest
from pipeline import state

PATH=Path(__file__).resolve().parents[1]/'scripts/upgrade_legacy_to_dynamic.py'
spec=spec_from_file_location('upgrade_legacy',PATH)
module=module_from_spec(spec)
spec.loader.exec_module(module)


def test_separate_legacy_upgrade_and_durable_retry(tmp_path,monkeypatch):
    monkeypatch.setattr(state,'JOBS',tmp_path)
    old=state.Job.create('dy-7597434271141216881','https://www.iesdouyin.com/share/video/7597434271141216881/')
    video=old.dir/'source/source.mp4'
    video.write_bytes(b'mp4-test-fixture')
    from pipeline.common import atomic_json
    atomic_json(old.dir/'source/source.json',{'source_url':'https://example.invalid','aweme_id':'7597434271141216881','video_path':str(video)})
    state.set_workflow_intent(old,'STORE_ALBUM')
    old.write_state('EXPORTED',subtitle_mode='legacy')
    original=old.state().copy()
    monkeypatch.setattr(module,'analyze',lambda source,dest,allow_no_audio: {'duration':10,'route':'visual_review'})
    monkeypatch.setattr(module,'analyze_dynamic',lambda source,dest,analysis: analysis)
    result=module.upgrade(old.job_id)
    assert result['status']=='ANALYZED'
    assert result['job_id']=='my-7597434271141216881-v04'
    new=state.Job(result['job_id'])
    assert new.state()['subtitle_mode']=='dynamic_v04'
    assert new.state()['workflow_intent']=='STORE_ALBUM'
    assert new.state()['upgrade_from']==old.job_id
    assert old.state()==original
    assert (new.dir/'source/original.mp4').read_bytes()==video.read_bytes()
    assert module.upgrade(old.job_id)['status']=='EXISTING_DYNAMIC_JOB'
    repeat1=module.upgrade(old.job_id, repeat=True)
    repeat2=module.upgrade(old.job_id, repeat=True)
    assert repeat1['job_id'].endswith('-r001')
    assert repeat2['job_id'].endswith('-r002')
    assert state.Job(repeat1['job_id']).state()['subtitle_mode']=='dynamic_v04'
    assert old.state()==original


def test_upgrade_rejects_invalid_id():
    with pytest.raises(ValueError):
        module.upgrade('../../unsafe')


def test_short_link_recovery_creates_verified_version_without_touching_legacy(tmp_path, monkeypatch):
    repeat_path=PATH.with_name('reprocess_douyin_dynamic.py')
    repeat_spec=spec_from_file_location('reprocess_dynamic',repeat_path)
    repeat_module=module_from_spec(repeat_spec)
    repeat_spec.loader.exec_module(repeat_module)
    monkeypatch.setattr(state,'JOBS',tmp_path)
    aweme='7999912345678901234'
    old=state.Job.create(f'dy-{aweme}','https://v.douyin.com/ExampleAbc/')
    old.write_state('ANALYZED',subtitle_mode='legacy')
    old_before=old.state().copy()

    class Download:
        def download(self, url, output):
            assert url=='https://v.douyin.com/ExampleAbc/'
            (output/f'{aweme}.mp4').write_bytes(b'video-fixture')
            return {'job_id':'douzy-test'}

    monkeypatch.setattr(repeat_module,'Client',lambda:Download())
    monkeypatch.setattr(repeat_module,'_find_video',lambda source:source/f'{aweme}.mp4')
    monkeypatch.setattr(repeat_module,'analyze',lambda source,dest,allow_no_audio: {'route':'visual_review'})
    monkeypatch.setattr(repeat_module,'analyze_dynamic',lambda source,dest,analysis: analysis)
    result=repeat_module.reprocess('https://v.douyin.com/ExampleAbc/',expected_aweme_id=aweme)
    assert result['job_id']==f'my-{aweme}-v04-r001'
    assert state.Job(result['job_id']).state()['subtitle_mode']=='dynamic_v04'
    assert old.state()==old_before

    with pytest.raises(ValueError,match='conflicts'):
        repeat_module.reprocess('https://www.douyin.com/video/7999912345678901235',expected_aweme_id=aweme)

    class UnidentifiedDownload:
        def download(self, url, output):
            (output/'unlabeled.mp4').write_bytes(b'unknown-video')
            return {'job_id':'douzy-test'}

    monkeypatch.setattr(repeat_module,'Client',lambda:UnidentifiedDownload())
    monkeypatch.setattr(repeat_module,'_find_video',lambda source:source/'unlabeled.mp4')
    with pytest.raises(RuntimeError,match='missing or mismatched'):
        repeat_module.reprocess('https://v.douyin.com/ExampleAbc/',expected_aweme_id=aweme)
    assert state.Job(f'my-{aweme}-v04-r002').state()['state']=='FAILED'
    assert old.state()==old_before
