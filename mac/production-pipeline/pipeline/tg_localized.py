"""TG-only localized-video delivery and post-receipt job artifact cleanup.

Only TG_LOCALIZED may use this terminal path. The Telegram API's verified SENT
receipt is durable before cleanup; uncertain sends retain every local artifact.
"""
from __future__ import annotations

import fcntl
import os
import re
import shutil
from pathlib import Path

from .common import JOBS, TMP, atomic_json, now_iso, read_json
from .state import Job
from .telegram_media import deliver

ARTIFACT_DIRS = ("source", "analysis", "localization", "production", "evidence", "export", "resume", "tmp")
RECEIPT_NAME = "tg-delivery-receipt.json"


class TelegramCleanupError(RuntimeError):
    pass


def _validated_receipt(record: dict, job_id: str) -> dict:
    if (
        record.get("status") != "SENT"
        or record.get("intent") != "TG_LOCALIZED"
        or record.get("job_id") != job_id
        or not isinstance(record.get("message_id"), int)
        or isinstance(record.get("message_id"), bool)
        or record["message_id"] <= 0
        or not isinstance(record.get("size"), int)
        or record["size"] <= 0
        or not isinstance(record.get("sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None
        or not isinstance(record.get("destination_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", record["destination_sha256"]) is None
    ):
        raise TelegramCleanupError("verified Telegram delivery receipt required")
    return {key: record[key] for key in (
        "status", "intent", "job_id", "message_id", "size",
        "sha256", "destination_sha256",
    )}


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _check_tree(path: Path) -> None:
    if path.is_symlink():
        raise TelegramCleanupError("symlink in cleanup scope")
    if path.exists():
        if not path.is_dir():
            raise TelegramCleanupError("unexpected cleanup path type")
        for entry in path.rglob("*"):
            if entry.is_symlink():
                raise TelegramCleanupError("symlink inside cleanup scope")


def _cleanup(job_dir: Path) -> None:
    # Preflight all paths before removing anything; never follow job/file symlinks.
    if TMP.is_symlink():
        raise TelegramCleanupError("symlinked temporary root")
    locations = [job_dir / name for name in ARTIFACT_DIRS]
    locations.append(TMP / job_dir.name)
    for path in locations:
        if path.parent.resolve() not in {job_dir.resolve(), TMP.resolve()}:
            raise TelegramCleanupError("cleanup path escapes its owner")
        _check_tree(path)
    for path in locations:
        if path.exists():
            shutil.rmtree(path)
    for name in ("events.jsonl",):
        p = job_dir / name
        if p.is_symlink():
            raise TelegramCleanupError("symlink in job log")
        if p.is_file():
            p.unlink()


def finish(job: Job) -> dict:
    """Idempotent send -> durable receipt -> cleanup -> terminal state."""
    job_dir = job.dir
    if (
        not re.fullmatch(r"[A-Za-z0-9._-]+", job.job_id)
        or job_dir.is_symlink()
        or job_dir.parent.resolve() != JOBS.resolve()
        or not job_dir.is_dir()
    ):
        raise TelegramCleanupError("invalid job ownership")

    # Keep lock outside deletion scope across retries/crash recovery.
    lock_path = job_dir / ".tg-finish.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = job.state()
        if state.get("workflow_intent") != "TG_LOCALIZED":
            raise TelegramCleanupError("TG_LOCALIZED intent required")
        current = state.get("state")
        saved = job_dir / RECEIPT_NAME

        if current == "TG_DELIVERED":
            receipt = _validated_receipt(read_json(saved, {}), job.job_id)
            return {"status": "TG_DELIVERED", "job_id": job.job_id,
                    "message_id": receipt["message_id"], "cleanup": "COMPLETE"}

        if current == "RENDERED":
            receipt = _validated_receipt(deliver(job_dir, intent="TG_LOCALIZED"), job.job_id)
            atomic_json(saved, receipt)
            _sync_directory(job_dir)
            job.write_state(
                "TG_DELIVERED_CLEANUP_PENDING",
                telegram_message_id=receipt["message_id"],
                telegram_media_sha256=receipt["sha256"],
                telegram_destination_sha256=receipt["destination_sha256"],
            )
            _sync_directory(job_dir)
        elif current == "TG_DELIVERED_CLEANUP_PENDING":
            receipt = _validated_receipt(read_json(saved, {}), job.job_id)
            if (
                state.get("telegram_message_id") != receipt["message_id"]
                or state.get("telegram_media_sha256") != receipt["sha256"]
                or state.get("telegram_destination_sha256") != receipt["destination_sha256"]
            ):
                raise TelegramCleanupError("cleanup checkpoint does not match delivery receipt")
        else:
            raise TelegramCleanupError(
                f"TG-only completion requires RENDERED or cleanup checkpoint; current={current}"
            )

        _cleanup(job_dir)
        job.write_state(
            "TG_DELIVERED",
            telegram_cleanup_at=now_iso(),
            telegram_cleanup_status="COMPLETE",
        )
        _sync_directory(job_dir)
        return {"status": "TG_DELIVERED", "job_id": job.job_id,
                "message_id": receipt["message_id"], "cleanup": "COMPLETE"}
