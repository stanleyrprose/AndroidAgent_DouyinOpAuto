from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

STATUS_TEXT = {
    "RECEIVED": ("🟡", "已接收"),
    "PRODUCING": ("🔵", "制作中"),
    "TRANSFERRING": ("🔵", "正在传输到 Y700"),
    "READY_TO_PUBLISH": ("🟡", "等待发布流程"),
    "DRY_RUN_PASS": ("🟡", "发布前检查通过"),
    "COMMITTING": ("🟠", "正在发布"),
    "PUBLISHED_VERIFIED": ("🟢", "已发布（已验证）"),
    "PUBLISHED_WITH_LIMITED_VERIFICATION": ("🟢", "已发布（验证有限）"),
    "RECONCILE_REQUIRED": ("🟠", "状态待核对，禁止重复发布"),
    "FAILED_SAFE": ("🔴", "失败（确认未发布）"),
    "DUPLICATE": ("⚪", "已存在，跳过重复发布"),
    "WAITING_EXECUTOR": ("🟡", "等待执行器"),
}

MAX_DETAIL = 300


def render_message(state: str, job_id: str, detail: str = "") -> str:
    if state not in STATUS_TEXT:
        raise ValueError(f"unsupported Telegram status: {state}")
    emoji, label = STATUS_TEXT[state]
    safe_detail = " ".join((detail or "").split())[:MAX_DETAIL]
    lines = [
        f"{emoji} Y700 Automation",
        f"Job: {job_id}",
        f"状态: {label}",
    ]
    if safe_detail:
        lines.append(f"说明: {safe_detail}")
    return "\n".join(lines)


def _resolve_sender() -> str | None:
    configured = os.environ.get("Y700_HERMES_WRAPPER")
    if configured:
        p = Path(configured).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    found = shutil.which("y700automation")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "y700automation"
    if fallback.is_file() and os.access(fallback, os.X_OK):
        return str(fallback)
    return None


def send_status(
    state: str,
    job_id: str,
    *,
    detail: str = "",
    target: str | None = None,
    strict: bool = False,
) -> dict:
    message = render_message(state, job_id, detail)
    sender = _resolve_sender()
    if not sender:
        receipt = {"sent": False, "state": state, "job_id": job_id, "reason": "HERMES_WRAPPER_NOT_FOUND"}
        if strict:
            raise RuntimeError(receipt["reason"])
        return receipt

    destination = target or os.environ.get("Y700_TG_TARGET", "telegram")
    try:
        proc = subprocess.run(
            [sender, "send", "--to", destination, "--json", message],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        receipt = {"sent": False, "state": state, "job_id": job_id, "reason": "SEND_EXECUTION_FAILED"}
        if strict:
            raise RuntimeError(receipt["reason"])
        return receipt

    sent = proc.returncode == 0
    receipt = {
        "sent": sent,
        "state": state,
        "job_id": job_id,
        "reason": None if sent else "TELEGRAM_DELIVERY_FAILED",
    }
    if strict and not sent:
        raise RuntimeError(receipt["reason"])
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(prog="tg-notify")
    ap.add_argument("state", choices=sorted(STATUS_TEXT))
    ap.add_argument("job_id")
    ap.add_argument("--detail", default="")
    ap.add_argument("--target")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    receipt = send_status(
        args.state,
        args.job_id,
        detail=args.detail,
        target=args.target,
        strict=args.strict,
    )
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt["sent"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
