#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

PASS = "PASS"
FAIL = "FAIL"
SPRINT_GATED = "SPRINT_GATED"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def emit(check: str, status: str, **details: Any) -> int:
    payload = {"check": check, "status": status, **details}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if status in {PASS, SPRINT_GATED} else 1


def safe_lstat(path: Path) -> dict[str, Any]:
    try:
        st = path.lstat()
    except FileNotFoundError:
        return {"path": str(path), "exists": False}
    return {
        "path": str(path),
        "exists": True,
        "uid": st.st_uid,
        "gid": st.st_gid,
        "mode": oct(stat.S_IMODE(st.st_mode)),
        "is_symlink": stat.S_ISLNK(st.st_mode),
        "is_dir": stat.S_ISDIR(st.st_mode),
        "is_file": stat.S_ISREG(st.st_mode),
        "group_or_other_write": bool(st.st_mode & 0o022),
    }


def y700_root() -> Path:
    return Path(os.environ.get("Y700_ROOT", "/opt/y700"))


def runtime_root() -> Path:
    return Path(os.environ.get("Y700_RUNTIME", str(y700_root() / "runtime")))


def on_y700() -> bool:
    return y700_root().exists() and (repo_root() / "bridge" / "root-exec.sh").exists()


def sprint_gated(check: str, owner: str, contract: str) -> int:
    return emit(check, SPRINT_GATED, owner=owner, contract=contract, production_assertion=False)


if __name__ == "__main__":
    sys.exit(emit("common-self-test", PASS, repo=str(repo_root())))
