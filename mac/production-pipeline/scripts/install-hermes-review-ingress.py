#!/usr/bin/env python3
"""Reversible, anchored Hermes admission-side review dispatch installation.

Installed in the dedicated gateway's run_inbound module, after auth and pending
intercepts and before LLM fallback. The source change is strictly one block.
"""
from pathlib import Path
import argparse, shutil

START='        # Y700_DETERMINISTIC_REVIEW_INGRESS_BEGIN\n'
END='        # Y700_DETERMINISTIC_REVIEW_INGRESS_END\n'
ANCHOR='        # Evict a leaked/reaped ``_running_agents`` slot before the busy-session fast-path.\n'
BLOCK=(START+
'''        if not is_internal and str(getattr(source.platform, 'value', source.platform)) == 'telegram':
            import importlib.util
            from pathlib import Path
            _y700_review_module = Path.home() / 'Library/Application Support/Y700Automation/AndroidAgent_DouyinOpAuto/mac/production-pipeline/scripts/tg-review-ingress.py'
            if _y700_review_module.is_file():
                _y700_spec = importlib.util.spec_from_file_location('y700_review_ingress', _y700_review_module)
                _y700_mod = importlib.util.module_from_spec(_y700_spec)
                _y700_spec.loader.exec_module(_y700_mod)
                if _y700_mod.classify(event.text or '') is not None:
                    return await asyncio.to_thread(
                        _y700_mod.dispatch, event.text or '', platform='telegram',
                        chat_id=str(source.chat_id or ''),
                        reply_to_id=str(getattr(event, 'reply_to_message_id', '') or ''),
                    )
'''+END)

def install(path: Path):
    data=path.read_text()
    if START in data:
        if BLOCK not in data:raise RuntimeError('unknown existing ingress patch; manual reconciliation required')
        return 'already installed'
    if data.count(ANCHOR)!=1:raise RuntimeError('Hermes anchor not unique; refusing patch')
    backup=path.with_suffix('.py.y700-review-prepatch')
    if not backup.exists():shutil.copy2(path,backup)
    path.write_text(data.replace(ANCHOR,BLOCK+ANCHOR,1))
    return 'installed'

def remove(path: Path):
    data=path.read_text()
    if START not in data:return 'not installed'
    if BLOCK not in data:raise RuntimeError('unrecognized ingress modification; refusing rollback')
    path.write_text(data.replace(BLOCK,'',1))
    return 'removed'

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['install','remove','check']);parser.add_argument('--gateway-file',required=True)
    args=parser.parse_args();path=Path(args.gateway_file)
    if args.action=='install':print(install(path))
    elif args.action=='remove':print(remove(path))
    else:print('installed' if BLOCK in path.read_text() else 'not installed')
