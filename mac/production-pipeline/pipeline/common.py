from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
JOBS = RUNTIME / "jobs"
TMP = RUNTIME / "tmp"
INDEX = RUNTIME / "index.json"
MEDIA_EXPORT = Path(os.environ.get(
    "Y700_MEDIA_EXPORT_ROOT",
    str(ROOT.parent / "media-export"),
))
MODEL_DEFAULT = Path.home() / ".cache/huggingface/hub/models--Systran--faster-whisper-small/snapshots/536b0662742c02347bc0e980a01041f333bce120"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def ensure_runtime() -> None:
    for p in (RUNTIME, JOBS, TMP):
        p.mkdir(parents=True, exist_ok=True)


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def run(cmd: list[str], *, check: bool = True, cwd: Path | None = None,
        capture: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess:
    p = subprocess.run(
        [str(x) for x in cmd],
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        timeout=timeout,
    )
    if check and p.returncode != 0:
        raise RuntimeError(
            f"command failed rc={p.returncode}: {' '.join(map(str, cmd))}\n"
            f"{(p.stderr or '').strip()}"
        )
    return p


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def url_key(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:12]


def extract_aweme_id(text: str) -> str | None:
    import re
    matches = re.findall(r"(?<!\d)(\d{18,20})(?!\d)", text)
    return matches[-1] if matches else None
