#!/usr/bin/env python3
from __future__ import annotations
import fcntl, json, os, secrets
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

RUNTIME = Path(os.environ.get("Y700_RUNTIME", "/opt/y700/runtime"))
RESOURCE_DIR = Path(os.environ.get("Y700_RESOURCE_DIR", str(RUNTIME / "resources")))
ANDROID_UI_DIR = RESOURCE_DIR / "android_ui"
LOCK_PATH = ANDROID_UI_DIR / "android-ui.lock"
CLAIM_PATH = ANDROID_UI_DIR / "claim.json"

class ResourceError(RuntimeError):
    pass

def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp-" + secrets.token_hex(4))
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)

def read_claim():
    try:
        with open(CLAIM_PATH, encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, dict) else None
    except FileNotFoundError:
        return None

@dataclass(frozen=True)
class ResourceGuard:
    resource: str
    owner_kind: str
    owner_id: str
    claim_id: str
    backend_job_id: str
    def as_dict(self):
        return {"resource": self.resource, "owner_kind": self.owner_kind, "owner_id": self.owner_id, "claim_id": self.claim_id, "backend_job_id": self.backend_job_id}

def assert_guard(guard):
    if not isinstance(guard, dict):
        raise ResourceError("RESOURCE_OWNERSHIP_REQUIRED")
    if guard.get("resource") != "android_ui":
        raise ResourceError("RESOURCE_OWNERSHIP_MISMATCH")
    current = read_claim()
    if not current:
        raise ResourceError("RESOURCE_OWNERSHIP_REQUIRED")
    for key in ("owner_kind", "owner_id", "claim_id", "backend_job_id"):
        if not guard.get(key) or guard.get(key) != current.get(key):
            raise ResourceError("RESOURCE_OWNERSHIP_MISMATCH")
    return current

@contextmanager
def acquire_android_ui(*, owner_kind: str, owner_id: str, backend_job_id: str, capability_job_id: str | None = None, blocking: bool = False):
    if owner_kind not in {"LEGACY", "CAPABILITY", "ADMIN"}:
        raise ResourceError("RESOURCE_OWNER_KIND_INVALID")
    if owner_kind == "CAPABILITY" and not capability_job_id:
        raise ResourceError("CAPABILITY_JOB_ID_REQUIRED")
    ANDROID_UI_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as exc:
            raise ResourceError("DEVICE_BUSY") from exc
        if read_claim():
            raise ResourceError("RESOURCE_RECONCILE_REQUIRED")
        claim_id = "claim-" + secrets.token_hex(16)
        _atomic_json(CLAIM_PATH, {"schema_version": 1, "resource": "android_ui", "owner_kind": owner_kind, "owner_id": owner_id, "claim_id": claim_id, "backend_job_id": backend_job_id, "capability_job_id": capability_job_id, "coordinator_pid": os.getpid()})
        guard = ResourceGuard("android_ui", owner_kind, owner_id, claim_id, backend_job_id)
        try:
            yield guard
        finally:
            current = read_claim()
            if current and current.get("claim_id") == claim_id:
                CLAIM_PATH.unlink()
                _fsync_dir(CLAIM_PATH.parent)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
