#!/usr/bin/env python3
"""TikTok adapter for the generic Y700 Android Automation Core.

DRY_RUN has a hard boundary at POST_CONFIG and never clicks Publish. COMMIT is
a separate explicit path: it reuses the same semantic preparation workflow,
durably crosses the publisher's COMMITTING boundary via a required callback,
then dispatches exactly one irreversible Publish click for later verification.
"""
from __future__ import annotations

import fcntl
import json
import os
import secrets
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
AUTOMATION = ROOT / "automation"
ROOT_EXEC = ROOT / "bridge" / "root-exec.sh"
REQUEST_RUNTIME = Path(
    os.environ.get("Y700_AUTOMATION_REQUEST_RUNTIME", "/opt/y700/runtime/automation-driver")
)
UI_JOBS = Path(os.environ.get("Y700_UI_JOBS", "/opt/y700/ui-jobs"))
UI_LEASE = Path(os.environ.get("Y700_UI_LEASE", "/opt/y700/runtime/android-ui.lock"))

if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))
import ui_job  # noqa: E402

from .state import TIKTOK, detect_state  # noqa: E402

ALBUM = "Y700Agent"

RID = {
    "home_create": f"{TIKTOK}:id/o70",
    "upload": f"{TIKTOK}:id/upload_hot_area",
    "gallery": f"{TIKTOK}:id/viewpager_choose_media",
    "album_menu": f"{TIKTOK}:id/dqr",
    "album_title": f"{TIKTOK}:id/tv_title",
    "album_row_text": f"{TIKTOK}:id/kmp",
    "grid": f"{TIKTOK}:id/jc5",
    "edit_next": f"{TIKTOK}:id/pje",
    "edit_next_text": f"{TIKTOK}:id/pjg",
    "caption": f"{TIKTOK}:id/h00",
    "title": f"{TIKTOK}:id/h04",
    "visibility": f"{TIKTOK}:id/doy",
    "visibility_container": f"{TIKTOK}:id/y0d",
    "visibility_heading": f"{TIKTOK}:id/pcq",
    "publish": f"{TIKTOK}:id/st6",
}


class TikTokCoreError(RuntimeError):
    def __init__(self, message: str, result: dict[str, Any] | None = None):
        super().__init__(message)
        self.result = result or {}


@contextmanager
def ui_lease(timeout_sec: int = 300):
    """Exclusive screen lease across recovery and all workflow sessions."""
    UI_LEASE.parent.mkdir(parents=True, exist_ok=True)
    with open(UI_LEASE, "a+", encoding="utf-8") as lock:
        deadline = time.monotonic() + timeout_sec
        while True:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TikTokCoreError("UI_LEASE_TIMEOUT: another workflow owns the screen")
                time.sleep(0.2)
        lock.seek(0)
        lock.truncate()
        lock.write(json.dumps({"pid": os.getpid(), "acquired_at": time.time()}) + "\n")
        lock.flush()
        os.fsync(lock.fileno())
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _root(
    command: str,
    *,
    timeout: int = 60,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["Y700_BRIDGE_TIMEOUT_MS"] = str(max(1_000, min(3_600_000, timeout * 1000)))
    p = subprocess.run(
        [str(ROOT_EXEC), command],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout + 30,
    )
    if check and p.returncode != 0:
        raise TikTokCoreError(
            f"root command failed rc={p.returncode}: {command}\n{p.stderr.strip()}"
        )
    return p


def force_stop() -> None:
    _root(f"am force-stop {TIKTOK}", timeout=20, check=False)


def _job_id(label: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._-" else "-" for c in label)[:44]
    return f"tiktok-v05-{safe}-{int(time.time() * 1000)}-{secrets.token_hex(3)}"


def _run(
    label: str,
    actions: list[dict[str, Any]],
    *,
    max_duration_ms: int = 120_000,
) -> dict[str, Any]:
    REQUEST_RUNTIME.mkdir(parents=True, exist_ok=True)
    request = {
        "protocol_version": 1,
        "job_id": _job_id(label),
        "max_duration_ms": max_duration_ms,
        "actions": actions,
    }
    request_path = REQUEST_RUNTIME / f"{request['job_id']}.json"
    ui_job.atomic_json(request_path, request)
    try:
        result = ui_job.run_workflow(request_path)
    finally:
        request_path.unlink(missing_ok=True)
    if result.get("status") != "PASS":
        raise TikTokCoreError(
            f"TikTok workflow {label} failed: "
            f"{json.dumps(result.get('error'), ensure_ascii=False)}",
            result,
        )
    return result


def _observe(
    label: str = "observe",
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    result = _run(
        label,
        [{"action_id": "observe", "action": "observe"}],
        max_duration_ms=30_000,
    )
    data = result["actions"][0]["data"]
    elements = data["elements"]
    return detect_state(elements), elements, result


def _press_back_and_observe(label: str) -> dict[str, Any]:
    result = _run(
        label,
        [
            {
                "action_id": "back",
                "action": "pressBack",
                "side_effect": "REVERSIBLE_LOCAL",
            },
            {
                "action_id": "wait",
                "action": "waitStable",
                "timeout_ms": 8_000,
                "stable_interval_ms": 400,
            },
            {"action_id": "observe", "action": "observe"},
        ],
        max_duration_ms=20_000,
    )
    elements = result["actions"][-1]["data"]["elements"]
    return detect_state(elements)


def _recover_home_unlocked(prefix: str) -> dict[str, Any]:
    """Cold-launch and reach HOME using bounded semantic recovery only."""
    force_stop()
    _root(
        f"monkey -p {TIKTOK} -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1",
        timeout=20,
    )

    deadline = time.monotonic() + 35
    back_budget = 3
    recoverable = {
        "POST_CONFIG",
        "VISIBILITY",
        "EDIT",
        "GALLERY",
        "CREATE",
        "SMS_PROMPT",
    }
    last: dict[str, Any] | None = None
    attempt = 0

    while time.monotonic() < deadline:
        attempt += 1
        state, _, _ = _observe(f"{prefix}-home-{attempt}")
        last = state
        if state["state"] == "HOME" and state.get("tiktok_visible"):
            return state

        if state["state"] in recoverable and back_budget > 0:
            back_budget -= 1
            last = _press_back_and_observe(f"{prefix}-back-{attempt}")
            if last["state"] == "HOME" and last.get("tiktok_visible"):
                return last
            continue

        if state["state"] == "PERMISSION":
            raise TikTokCoreError("TikTok media permission prompt blocks DRY_RUN", {"state": state})

        # UNKNOWN/KEYGUARD can be transient after a cold launch. UI-job preflight
        # already handles screen/keyguard, so wait briefly rather than guessing.
        time.sleep(0.8)

    raise TikTokCoreError(f"HOME not reached after bounded recovery; last={last}")


def recover_home(prefix: str = "recover") -> dict[str, Any]:
    with ui_lease():
        return _recover_home_unlocked(prefix)


def media_selector() -> dict[str, Any]:
    """Selector for the single media item staged in the isolated album.

    stage_job.py deletes previous files before copying the current job. The
    generic driver still enforces cardinality, so stale/multiple visible tiles
    fail closed with SELECTOR_AMBIGUOUS instead of choosing an arbitrary item.
    """
    return {
        "class_name": "android.widget.FrameLayout",
        "clickable": True,
        "has_parent": {"resource_id": RID["grid"]},
    }


def build_dry_run_actions(caption: str, album: str = ALBUM) -> list[dict[str, Any]]:
    """One instrumentation session from cold-launch HOME to verified POST_CONFIG."""
    media = media_selector()
    return [
        {
            "action_id": "wait-cold-home",
            "action": "waitFor",
            "selector": {"resource_id": RID["home_create"], "clickable": True},
            "unique": True,
            "timeout_ms": 45_000,
        },
        {
            "action_id": "home-create",
            "action": "click",
            "selector": {"resource_id": RID["home_create"], "clickable": True},
            "expect": {"selector": {"resource_id": RID["upload"]}, "unique": True},
            "timeout_ms": 12_000,
            "side_effect": "REVERSIBLE_LOCAL",
        },
        {
            "action_id": "open-upload",
            "action": "click",
            "selector": {"resource_id": RID["upload"], "clickable": True},
            "expect": {"selector": {"resource_id": RID["gallery"]}, "unique": True},
            "timeout_ms": 15_000,
            "side_effect": "REVERSIBLE_LOCAL",
        },
        {
            "action_id": "album-menu",
            "action": "click",
            "selector": {"resource_id": RID["album_menu"], "clickable": True},
            "side_effect": "REVERSIBLE_LOCAL",
        },
        {
            "action_id": "wait-album-entry",
            "action": "waitFor",
            "selector": {
                "class_name": "android.widget.RelativeLayout",
                "clickable": True,
                "has_descendant": {
                    "resource_id": RID["album_row_text"],
                    "text": album,
                },
            },
            "unique": True,
            "timeout_ms": 8_000,
        },
        {
            "action_id": "select-album",
            "action": "click",
            "selector": {
                "class_name": "android.widget.RelativeLayout",
                "clickable": True,
                "has_descendant": {
                    "resource_id": RID["album_row_text"],
                    "text": album,
                },
            },
            "expect": {
                "selector": {"resource_id": RID["album_title"], "text": album},
                "unique": True,
            },
            "timeout_ms": 8_000,
            "side_effect": "REVERSIBLE_LOCAL",
        },
        {
            "action_id": "find-isolated-media",
            "action": "find",
            "selector": media,
        },
        {
            "action_id": "select-isolated-media",
            "action": "click",
            "selector": media,
            "side_effect": "REVERSIBLE_LOCAL",
        },
        {
            "action_id": "wait-edit",
            "action": "waitFor",
            "selector": {"resource_id": RID["edit_next"], "clickable": True},
            "unique": True,
            "timeout_ms": 20_000,
        },
        {
            "action_id": "next-to-post-config",
            "action": "click",
            "selector": {"resource_id": RID["edit_next"], "clickable": True},
            "precondition": {
                "selector": {"resource_id": RID["edit_next_text"], "text": "下一步"},
                "unique": True,
            },
            "expect": {"selector": {"resource_id": RID["publish"]}, "unique": True},
            "timeout_ms": 25_000,
            "side_effect": "REVERSIBLE_LOCAL",
        },
        {
            "action_id": "wait-caption",
            "action": "waitFor",
            "selector": {
                "resource_id": RID["caption"],
                "class_name": "android.widget.EditText",
            },
            "unique": True,
            "timeout_ms": 15_000,
        },
        {
            "action_id": "caption",
            "action": "inputText",
            "selector": {
                "resource_id": RID["caption"],
                "class_name": "android.widget.EditText",
            },
            "text": caption,
            "clear_first": True,
            "dismiss_ime": True,
            "precondition": {
                "selector": {"resource_id": RID["publish"], "enabled": True},
                "unique": True,
            },
            "expect": {
                "selector": {"resource_id": RID["caption"], "text": caption},
                "unique": True,
            },
            "timeout_ms": 12_000,
            "side_effect": "REVERSIBLE_LOCAL",
        },
        {
            "action_id": "open-visibility",
            "action": "click",
            "selector": {
                "resource_id": RID["visibility"],
                "clickable": True,
                "has_ancestor": {"resource_id": RID["visibility_container"]},
            },
            "expect": {
                "selector": {
                    "resource_id": RID["visibility_heading"],
                    "text": "谁可以看",
                },
                "unique": True,
            },
            "timeout_ms": 8_000,
            "side_effect": "REVERSIBLE_LOCAL",
        },
        {
            "action_id": "choose-private",
            "action": "click",
            "selector": {
                "resource_id": RID["visibility"],
                "content_desc": "仅自己",
                "clickable": True,
                "checkable": True,
            },
            "precondition": {
                "selector": {
                    "resource_id": RID["visibility_heading"],
                    "text": "谁可以看",
                },
                "unique": True,
            },
            "expect": {
                "absent_selector": {
                    "resource_id": RID["visibility_heading"],
                    "text": "谁可以看",
                }
            },
            "timeout_ms": 8_000,
            "side_effect": "IDEMPOTENT",
        },
        {
            "action_id": "wait-private-summary",
            "action": "waitFor",
            "selector": {
                "resource_id": RID["visibility"],
                "content_desc_contains": "自己",
                "clickable": True,
                "has_ancestor": {"resource_id": RID["visibility_container"]},
            },
            "unique": True,
            "timeout_ms": 15_000,
        },
        {
            "action_id": "assert-caption",
            "action": "assert",
            "selector": {"resource_id": RID["caption"], "text": caption},
        },
        {
            "action_id": "assert-private",
            "action": "assert",
            "selector": {
                "resource_id": RID["visibility"],
                "content_desc_contains": "自己",
                "clickable": True,
                "has_ancestor": {"resource_id": RID["visibility_container"]},
            },
        },
        {
            "action_id": "assert-publish-ready",
            "action": "assert",
            "selector": {
                "resource_id": RID["publish"],
                "text": "发布",
                "enabled": True,
            },
        },
        {"action_id": "observe-ready", "action": "observe"},
        {
            "action_id": "ready-evidence",
            "action": "screenshot",
            "filename": "private-dry-run-ready.png",
        },
    ]


def _cold_launch() -> None:
    force_stop()
    _root(
        f"monkey -p {TIKTOK} -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1",
        timeout=20,
    )


def _run_single_session_dry_run(caption: str, album: str) -> dict[str, Any]:
    _cold_launch()
    result = _run(
        "cold-dry-run",
        build_dry_run_actions(caption, album),
        max_duration_ms=180_000,
    )
    observe = next(a for a in result["actions"] if a["action_id"] == "observe-ready")
    state = detect_state(observe["data"]["elements"])
    if state["state"] != "POST_CONFIG":
        raise TikTokCoreError(f"DRY_RUN left POST_CONFIG: {state}", result)

    shot = next(a for a in result["actions"] if a["action_id"] == "ready-evidence")
    evidence_path = shot["data"].get("evidence_path")
    if not evidence_path:
        raise TikTokCoreError("READY_TO_COMMIT screenshot was not exported", result)
    source = UI_JOBS / result["job_id"] / evidence_path
    if not source.is_file():
        raise TikTokCoreError(f"READY_TO_COMMIT evidence missing: {source}", result)

    return {
        "workflow_job_id": result["job_id"],
        "ui_state": state,
        "caption_verified": True,
        "visibility": "PRIVATE",
        "evidence": {
            "relative_path": evidence_path,
            "source_path": str(source),
            "size": source.stat().st_size,
        },
    }

def prepare_dry_run(
    caption: str,
    *,
    title: str = "",
    visibility: str = "PRIVATE",
    album: str = ALBUM,
) -> dict[str, Any]:
    if not caption:
        raise TikTokCoreError("caption must be non-empty")
    if visibility.upper() != "PRIVATE":
        raise TikTokCoreError(
            f"generic DRY_RUN fails closed for visibility={visibility}; PRIVATE required"
        )

    with ui_lease():
        ready = _run_single_session_dry_run(caption, album)
        return {
            "engine": "androidx-uiautomator-2.4",
            "title": {
                "status": "SKIPPED",
                "reason": "title_field_not_present_in_verified_ui",
                "requested": bool(title),
            },
            **ready,
        }


def build_commit_actions(caption: str) -> list[dict[str, Any]]:
    """Revalidate POST_CONFIG, then dispatch exactly one irreversible Publish click."""
    return [
        {
            "action_id": "commit-assert-caption",
            "action": "assert",
            "selector": {"resource_id": RID["caption"], "text": caption},
        },
        {
            "action_id": "commit-assert-private",
            "action": "assert",
            "selector": {
                "resource_id": RID["visibility"],
                "content_desc_contains": "自己",
                "clickable": True,
                "has_ancestor": {"resource_id": RID["visibility_container"]},
            },
        },
        {
            "action_id": "commit-assert-publish-ready",
            "action": "assert",
            "selector": {
                "resource_id": RID["publish"],
                "text": "发布",
                "enabled": True,
            },
        },
        {
            "action_id": "commit-before-evidence",
            "action": "screenshot",
            "filename": "private-before-commit.png",
        },
        {
            "action_id": "commit-publish",
            "action": "click",
            "selector": {
                "resource_id": RID["publish"],
                "text": "发布",
                "enabled": True,
                "clickable": True,
            },
            "side_effect": "EXTERNAL_IRREVERSIBLE",
        },
    ]


def commit_private(
    caption: str,
    *,
    title: str = "",
    visibility: str = "PRIVATE",
    album: str = ALBUM,
    before_irreversible: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Prepare generically, persist COMMITTING, then dispatch Publish exactly once."""
    if not caption:
        raise TikTokCoreError("caption must be non-empty")
    if visibility.upper() != "PRIVATE":
        raise TikTokCoreError(
            f"generic COMMIT fails closed for visibility={visibility}; PRIVATE required"
        )
    if before_irreversible is None:
        raise TikTokCoreError("before_irreversible callback is required for COMMIT")

    with ui_lease():
        ready = _run_single_session_dry_run(caption, album)
        commit_actions = build_commit_actions(caption)
        precommit = _run(
            "commit-preflight",
            commit_actions[:-1],
            max_duration_ms=45_000,
        )
        before_irreversible()
        commit_result = _run(
            "commit-click",
            [commit_actions[-1]],
            max_duration_ms=30_000,
        )
        return {
            "engine": "androidx-uiautomator-2.4",
            "title": {
                "status": "SKIPPED",
                "reason": "title_field_not_present_in_verified_ui",
                "requested": bool(title),
            },
            **ready,
            "commit_preflight_workflow_job_id": precommit["job_id"],
            "commit_workflow_job_id": commit_result["job_id"],
            "commit_dispatched": True,
        }
