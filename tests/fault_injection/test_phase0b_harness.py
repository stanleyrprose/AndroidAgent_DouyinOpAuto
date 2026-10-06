from __future__ import annotations
import os, tempfile, unittest
from pathlib import Path

class InjectedFailure(RuntimeError): pass

def durable_publish(path:Path,payload:bytes,fail_at:str|None=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    with open(tmp,"wb") as f:
        f.write(payload); f.flush()
        if fail_at=="file_fsync": raise InjectedFailure("file_fsync")
        os.fsync(f.fileno())
    if fail_at=="rename": raise InjectedFailure("rename")
    os.replace(tmp,path)
    dfd=os.open(path.parent,os.O_DIRECTORY)
    try:
        if fail_at=="dir_fsync": raise InjectedFailure("dir_fsync")
        os.fsync(dfd)
    finally: os.close(dfd)

class Phase0BFaultHarnessSelfTest(unittest.TestCase):
    def test_success(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"state.json"; durable_publish(p,b'{"ok":true}\n'); self.assertTrue(p.exists())
    def test_pre_rename_failure_does_not_publish(self):
        for point in ("file_fsync","rename"):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as td:
                p=Path(td)/"state.json"
                with self.assertRaises(InjectedFailure): durable_publish(p,b"x",point)
                self.assertFalse(p.exists())
    def test_parent_fsync_failure_is_detectable(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"state.json"
            with self.assertRaises(InjectedFailure): durable_publish(p,b"x","dir_fsync")
            self.assertTrue(p.exists())
