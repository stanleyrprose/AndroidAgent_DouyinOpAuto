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
