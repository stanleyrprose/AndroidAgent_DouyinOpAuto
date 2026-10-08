from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import INDEX, JOBS, atomic_json, ensure_runtime, now_iso, read_json

STATES = {
    "RECEIVED",
    "DOWNLOADED",
    "ANALYZED",
    "LOCALIZED",
    "RENDERED",
    "EXPORTED",
    "Y700_DRY_RUN_PASS",
    "AWAITING_APPROVAL",
    "APPROVED",
    "PUBLISHED",
    "VERIFIED",
    "STORED_IN_ALBUM",
    "DIRECT_DOWNLOADED",
    "BLOCKED",
    "FAILED",
    "DUPLICATE",
}


class Job:
    def __init__(self, job_id: str):
        ensure_runtime()
        self.job_id = job_id
        self.dir = JOBS / job_id
        self.state_path = self.dir / "state.json"

    @classmethod
    def create(cls, job_id: str, source_url: str) -> "Job":
        j = cls(job_id)
        if j.dir.exists():
            raise RuntimeError(f"job already exists: {job_id}")
        j.dir.mkdir(parents=True)
        for name in ("source", "analysis", "localization", "production", "export", "evidence"):
            (j.dir / name).mkdir()
        j.write_state("RECEIVED", source_url=source_url)
        return j

    def state(self) -> dict[str, Any]:
        return read_json(self.state_path, {})

    def write_state(self, state: str, **extra: Any) -> dict[str, Any]:
        if state not in STATES:
            raise ValueError(f"invalid state: {state}")
        old = self.state()
        data = {
            **old,
            "job_id": self.job_id,
            "state": state,
            "updated_at": now_iso(),
            **extra,
        }
        data.setdefault("created_at", data["updated_at"])
        atomic_json(self.state_path, data)
        return data

    def event(self, kind: str, **data: Any) -> None:
        path = self.dir / "events.jsonl"
        import json, os
        row = {"at": now_iso(), "kind": kind, **data}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


def load_index() -> dict[str, Any]:
    ensure_runtime()
    return read_json(INDEX, {"aweme": {}, "url": {}})


def save_index(index: dict[str, Any]) -> None:
    atomic_json(INDEX, index)


def find_duplicate(*, aweme_id: str | None = None, url_key: str | None = None) -> dict[str, Any] | None:
    idx = load_index()
    if aweme_id and aweme_id in idx.get("aweme", {}):
        return idx["aweme"][aweme_id]
    if url_key and url_key in idx.get("url", {}):
        return idx["url"][url_key]
    return None


def index_job(job: Job, *, aweme_id: str | None = None, url_key: str | None = None) -> None:
    idx = load_index()
    summary = {
        "job_id": job.job_id,
        "state": job.state().get("state"),
        "updated_at": now_iso(),
    }
    terminal = {"PUBLISHED", "VERIFIED"}
    if aweme_id:
        current = idx.setdefault("aweme", {}).get(aweme_id)
        if not (current and current.get("state") in terminal and summary["state"] not in terminal):
            idx["aweme"][aweme_id] = summary
    if url_key:
        current = idx.setdefault("url", {}).get(url_key)
        if not (current and current.get("state") in terminal and summary["state"] not in terminal):
            idx["url"][url_key] = summary
    save_index(idx)


def mark_published(aweme_id: str, job_id: str, *, verified: bool = False) -> None:
    idx = load_index()
    idx.setdefault("aweme", {})[aweme_id] = {
        "job_id": job_id,
        "state": "VERIFIED" if verified else "PUBLISHED",
        "updated_at": now_iso(),
    }
    save_index(idx)


def set_workflow_intent(job: Job, intent: str) -> dict[str, Any]:
    if intent not in {"AUTO_PUBLISH", "STORE_ALBUM", "DIRECT_DOWNLOAD"}:
        raise RuntimeError(f"unsupported workflow intent: {intent}")
    current = job.state()
    existing = current.get("workflow_intent")
    if existing and existing != intent:
        raise RuntimeError(f"workflow intent is immutable: existing={existing} requested={intent}")
    terminal = {"PUBLISHED", "VERIFIED", "STORED_IN_ALBUM", "DIRECT_DOWNLOADED"}
    if not existing and current.get("state") in terminal:
        raise RuntimeError(f"cannot backfill workflow intent after terminal state: {current.get('state')}")
    if existing:
        return current
    state_name = current.get("state")
    if not state_name:
        raise RuntimeError("job state missing")
    out = job.write_state(
        state_name,
        workflow_intent=intent,
        workflow_intent_set_at=now_iso(),
    )
    job.event("WORKFLOW_INTENT_SET", workflow_intent=intent)
    return out
