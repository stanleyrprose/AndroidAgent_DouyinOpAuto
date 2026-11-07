"""Regression: TG human reviews must bypass LLM and require bound evidence."""
import importlib.util
from pathlib import Path

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'

def load(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),SCRIPTS/name)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_reply_image_metadata_is_stripped_without_relaxing_match():
    module=load('tg-review-ingress.py')
    name='my-7597434271141216881-v04-r001'
    assert module.classify(f'审核：{name}：布局=通过  [Replied-to image xyz]')==(name,'布局=通过')
    assert module.classify(f'审核：{name}：语义：evt-2be3fb51c38cd5c1：含义=猫咪突然拱背像恐龙')==(name,'语义:evt-2be3fb51c38cd5c1:含义=猫咪突然拱背像恐龙')
    assert module.classify('继续任务：other-job') is None
    assert module.classify(f'审核：{name}：布局=通过；直接发布')==('', '')

def test_dispatch_rejects_invalid_evidence_without_spawning(monkeypatch):
    module=load('tg-review-ingress.py')
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**k: (_ for _ in ()).throw(AssertionError('must not spawn')))
    assert 'REVIEW_REJECTED' in module.dispatch('审核：my-7597434271141216881-v04-r001：布局=通过',platform='telegram',chat_id='123456',reply_to_id=None)
    assert 'REVIEW_REJECTED' in module.dispatch('审核：my-7597434271141216881-v04-r001：布局=通过',platform='slack',chat_id='123456',reply_to_id='416')

def test_dispatch_passes_fixed_argv_without_shell(monkeypatch,tmp_path):
    module=load('tg-review-ingress.py')
    monkeypatch.setattr(module,'RUNNER',tmp_path/'scripts'/'tg-review-and-resume.sh')
    calls=[]
    def fake(argv,**kwargs):
        calls.append((argv,kwargs));return type('Result',(),{'returncode':0})()
    monkeypatch.setattr(module.subprocess,'run',fake)
    out=module.dispatch('审核：my-7597434271141216881-v04-r001：布局=通过',platform='telegram',chat_id='6486819035',reply_to_id='416')
    assert out.startswith('REVIEW_ACCEPTED')
    argv,k=calls[0]
    assert argv[0]=='bash' and argv[3:] == ['布局=通过','416','6486819035']
    assert k['capture_output'] and not k.get('shell',False)
