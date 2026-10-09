"""Durable best-effort quality notification; notification never changes publication truth."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .common import atomic_json, read_json
from .subtitle_events import digest


def queue_alert(job_dir: Path, report: dict) -> dict:
    """Persist before any remote attempt; unique by job, QA revision and code."""
    path = job_dir / "production" / "quality-notify.json"
    outbox = read_json(path, {"schema_version": 1, "alerts": []}) or {"schema_version": 1, "alerts": []}
    seen = {x["alert_id"] for x in outbox.get("alerts", [])}
    for code in report.get("codes", []):
        key = digest([job_dir.name, report.get("revision"), code])[:20]
        if key not in seen:
            outbox["alerts"].append({
                "alert_id": key, "qa_revision": report.get("revision"), "qa_code": code,
                "status": "PENDING", "attempts": 0, "last_error": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "next_action": report.get("next_action", "Review Mac job evidence"),
                "evidence_ref": f"runtime/jobs/{job_dir.name}/production/quality_report.json",
            })
    atomic_json(path, outbox)
    return outbox


def send_pending(job_dir: Path, *, explicit_resend: bool = False) -> dict:
    from .telegram_notify import send_status
    path = job_dir / "production" / "quality-notify.json"
    outbox = read_json(path, {}) or {"schema_version": 1, "alerts": []}
    attempts = 0
    sent = 0
    for alert in outbox.get("alerts", []):
        if alert["status"] == "SENT":
            continue
        if alert["status"] == "FAILED" and not explicit_resend:
            continue
        qa = read_json(job_dir / "production" / "quality_report.json", {}) or {}
        state = "QUALITY_BLOCKED" if qa.get("status") == "BLOCKED" else "QUALITY_REVIEW_REQUIRED"
        alert["status"] = "PENDING"
        alert["attempts"] += 1
        alert["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
        # Never transmit private video, URLs, credentials or screenshots.
        detail = (f"code={alert['qa_code']} stage={qa.get('quality_stage','?')} "
                  f"evidence={alert['evidence_ref']} action=review-Mac")
        atomic_json(path, outbox)
        receipt = send_status(state, job_dir.name, detail=detail)
        attempts += 1
        if receipt.get("sent"):
            alert["status"] = "SENT"
            alert["last_error"] = None
            sent += 1
        else:
            alert["status"] = "FAILED"
            alert["last_error"] = receipt.get("reason", "delivery_failed")
        alert["last_receipt"] = {
            "sent": bool(receipt.get("sent")), "reason": receipt.get("reason"),
        }
        atomic_json(path, outbox)
    return {"job_id": job_dir.name, "attempted": attempts, "sent": sent,
            "pending_or_failed": sum(1 for a in outbox.get("alerts", []) if a["status"] != "SENT")}


def notify_if_blocked(job_dir: Path, report: dict) -> dict | None:
    if report.get("status") == "PASS":
        return None
    queue_alert(job_dir, report)
    return send_pending(job_dir)
