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
    "profile": f"{TIKTOK}:id/o76",
    "private_tile": f"{TIKTOK}:id/ev2",
    "post_caption": f"{TIKTOK}:id/desc",
    "private_label": f"{TIKTOK}:id/tv_label",
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
        "has_parent": {"class_name": "android.widget.GridView"},
    }


def home_create_selector() -> dict[str, Any]:
    """Semantic create-tab selector resilient to TikTok resource-id drift."""
    return {"content_desc": "创建", "clickable": True}


def album_menu_selector() -> dict[str, Any]:
    """Semantic album picker selector; TikTok obfuscates this container id."""
    return {
        "class_name": "android.widget.LinearLayout",
        "clickable": True,
        "has_descendant": {"text": "最近项目"},
    }


def edit_next_selector() -> dict[str, Any]:
    """Semantic edit-page Next selector resilient to resource-id drift."""
    return {
        "class_name": "android.widget.LinearLayout",
        "clickable": True,
        "has_descendant": {"text": "下一步"},
    }


def caption_selector() -> dict[str, Any]:
    """Semantic post description editor selector."""
    return {
        "class_name": "android.widget.EditText",
        "clickable": True,
    }


def publish_button_selector() -> dict[str, Any]:
    """Semantic final Publish button selector."""
    return {
        "class_name": "android.widget.Button",
        "text": "发布",
        "clickable": True,
        "enabled": True,
    }


def visibility_summary_selector() -> dict[str, Any]:
    """Semantic public visibility summary button on post-config."""
    return {
        "class_name": "android.widget.Button",
        "content_desc": "所有人可见",
        "clickable": True,
    }


def build_dry_run_actions(caption: str, album: str = ALBUM) -> list[dict[str, Any]]:
    """One instrumentation session from cold-launch HOME to verified POST_CONFIG."""
    media = media_selector()
    home_create = home_create_selector()
    return [
        {
            "action_id": "wait-cold-home",
            "action": "waitFor",
            "selector": home_create,
            "unique": True,
            "timeout_ms": 45_000,
        },
        {
            "action_id": "wait-home-stable",
            "action": "waitStable",
            "timeout_ms": 5_000,
            "stable_interval_ms": 800,
        },
        {
            "action_id": "home-create",
            "action": "click",
            "selector": home_create,
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
            "selector": album_menu_selector(),
            "side_effect": "REVERSIBLE_LOCAL",
        },
        {
            "action_id": "wait-album-entry",
            "action": "waitFor",
            "selector": {
                "class_name": "android.widget.RelativeLayout",
                "clickable": True,
                "has_descendant": {
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
            "selector": edit_next_selector(),
            "unique": True,
            "timeout_ms": 20_000,
        },
        {
            "action_id": "next-to-post-config",
            "action": "click",
            "selector": edit_next_selector(),
            "precondition": {
                "selector": edit_next_selector(),
                "unique": True,
            },
            "expect": {"selector": publish_button_selector(), "unique": True},
            "timeout_ms": 25_000,
            "side_effect": "REVERSIBLE_LOCAL",
        },
        {
            "action_id": "wait-caption",
            "action": "waitFor",
            "selector": caption_selector(),
            "unique": True,
            "timeout_ms": 15_000,
        },
        {
            "action_id": "caption",
            "action": "inputText",
            "selector": caption_selector(),
            "text": caption,
            "clear_first": True,
            "dismiss_ime": True,
            "precondition": {
                "selector": publish_button_selector(),
                "unique": True,
            },
            "expect": {
                "selector": {**caption_selector(), "text": caption},
                "unique": True,
            },
            "timeout_ms": 12_000,
            "side_effect": "REVERSIBLE_LOCAL",
        },
        {
            "action_id": "open-visibility",
            "action": "click",
            "selector": visibility_summary_selector(),
            "expect": {
                "selector": {"text": "谁可以看"},
                "unique": True,
            },
            "timeout_ms": 8_000,
            "side_effect": "REVERSIBLE_LOCAL",
        },
        {
            "action_id": "choose-public",
            "action": "click",
            "selector": {
                "resource_id": RID["visibility"],
                "content_desc": "所有人",
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
            "action_id": "wait-public-summary",
            "action": "waitFor",
            "selector": visibility_summary_selector(),
            "unique": True,
            "timeout_ms": 15_000,
        },
        {
            "action_id": "assert-caption",
            "action": "assert",
            "selector": {**caption_selector(), "text": caption},
        },
        {
            "action_id": "assert-public",
            "action": "assert",
            "selector": visibility_summary_selector(),
        },
        {
            "action_id": "assert-publish-ready",
            "action": "assert",
            "selector": publish_button_selector(),
        },
        {"action_id": "observe-ready", "action": "observe"},
        {
            "action_id": "ready-evidence",
            "action": "screenshot",
            "filename": "public-dry-run-ready.png",
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
        "visibility": "PUBLIC",
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
    visibility: str = "PUBLIC",
    album: str = ALBUM,
) -> dict[str, Any]:
    if not caption:
        raise TikTokCoreError("caption must be non-empty")
    if visibility.upper() != "PUBLIC":
        raise TikTokCoreError(
            f"generic DRY_RUN fails closed for visibility={visibility}; PUBLIC required"
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
            "action_id": "commit-assert-public",
            "action": "assert",
            "selector": {
                "resource_id": RID["visibility"],
                "content_desc_contains": "所有人",
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
            "filename": "public-before-commit.png",
        },
        {
            "action_id": "commit-publish",
            "action": "click",
            "selector": publish_button_selector(),
            "side_effect": "EXTERNAL_IRREVERSIBLE",
        },
    ]


def commit_public(
    caption: str,
    *,
    title: str = "",
    visibility: str = "PUBLIC",
    album: str = ALBUM,
    before_irreversible: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Prepare generically, persist COMMITTING, then dispatch Publish exactly once."""
    if not caption:
        raise TikTokCoreError("caption must be non-empty")
    if visibility.upper() != "PUBLIC":
        raise TikTokCoreError(
            f"generic COMMIT fails closed for visibility={visibility}; PUBLIC required"
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



def _public_tab_selector(*, selected: bool | None = None) -> dict[str, Any]:
    selector: dict[str, Any] = {
        "content_desc": "视频",
        "clickable": True,
    }
    if selected is not None:
        selector["selected"] = selected
    return selector


def _public_post_matches(elements: list[dict[str, Any]], caption: str) -> bool:
    exact_caption = any(
        element.get("resource_id") == RID["post_caption"]
        and (element.get("text") or "").strip() == caption
        for element in elements
    )
    restricted_label = any(
        element.get("resource_id") == RID["private_label"]
        and (element.get("text") or "").strip()
        for element in elements
    )
    return exact_caption and not restricted_label


def _open_public_grid_unlocked(prefix: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _recover_home_unlocked(f"{prefix}-recover")
    result = _run(
        f"{prefix}-open-grid",
        [
            {
                "action_id": "wait-profile",
                "action": "waitFor",
                "selector": {"resource_id": RID["profile"], "clickable": True},
                "unique": True,
                "timeout_ms": 15_000,
            },
            {
                "action_id": "open-profile",
                "action": "click",
                "selector": {"resource_id": RID["profile"], "clickable": True},
                "side_effect": "REVERSIBLE_LOCAL",
            },
            {
                "action_id": "wait-public-tab",
                "action": "waitFor",
                "selector": _public_tab_selector(selected=True),
                "unique": True,
                "timeout_ms": 20_000,
            },
            {"action_id": "observe-public-grid", "action": "observe"},
        ],
        max_duration_ms=60_000,
    )
    elements = result["actions"][-1]["data"]["elements"]
    return elements, result


def verify_public_post(
    caption: str,
    *,
    timeout_sec: int = 75,
    max_candidates: int = 12,
) -> dict[str, Any]:
    """Verify PUBLIC publication without ever invoking Publish.

    Verification starts from the selected Profile "视频" tab. A candidate is
    accepted only when its detail view exposes the exact caption and does not
    expose any visibility label on the known restricted-visibility label node.
    Tile taps use bounds derived from the current semantic ev2 nodes only.
    """
    if not caption:
        raise TikTokCoreError("caption must be non-empty")
    deadline = time.monotonic() + max(15, timeout_sec)

    with ui_lease():
        _, current, _ = _observe("verify-public-current")
        if _public_post_matches(current, caption):
            evidence = _verification_evidence("verify-public-current")
            return {
                "verified": True,
                "method": "generic_profile_public_exact_caption",
                "caption": caption,
                "candidate_ordinal": 0,
                **evidence,
            }

        grid, grid_result = _open_public_grid_unlocked("verify-public")
        candidate_limit = min(max_candidates, len(_video_tile_bounds(grid)))

        for ordinal in range(candidate_limit):
            if time.monotonic() >= deadline:
                break
            tiles = _video_tile_bounds(grid)
            if ordinal >= len(tiles):
                break
            b = tiles[ordinal]
            x = (b[0] + b[2]) // 2
            y = (b[1] + b[3]) // 2

            _root(f"input tap {x} {y}", timeout=15)
            time.sleep(2.5)
            _, detail, _ = _observe(f"verify-public-candidate-{ordinal + 1}")
            if _public_post_matches(detail, caption):
                evidence = _verification_evidence(
                    f"verify-public-candidate-{ordinal + 1}"
                )
                return {
                    "verified": True,
                    "method": "generic_profile_public_exact_caption",
                    "caption": caption,
                    "candidate_ordinal": ordinal + 1,
                    "profile_workflow_job_id": grid_result["job_id"],
                    **evidence,
                }

            _run(
                f"verify-public-back-{ordinal + 1}",
                [
                    {
                        "action_id": "back",
                        "action": "pressBack",
                        "side_effect": "REVERSIBLE_LOCAL",
                    }
                ],
                max_duration_ms=15_000,
            )
            time.sleep(1.5)
            _, grid, _ = _observe(f"verify-public-grid-{ordinal + 1}")
            if not _video_tile_bounds(grid):
                grid, grid_result = _open_public_grid_unlocked(
                    f"verify-public-recover-{ordinal + 1}"
                )

    raise TikTokCoreError(
        "profile verification failed: exact PUBLIC caption not found "
        f"within {max_candidates} visible candidates"
    )


def _private_tab_selector(*, selected: bool | None = None) -> dict[str, Any]:
    selector: dict[str, Any] = {
        "class_name": "android.widget.RelativeLayout",
        "content_desc": "私密视频",
        "clickable": True,
    }
    if selected is not None:
        selector["selected"] = selected
    return selector


def _video_tile_bounds(elements: list[dict[str, Any]]) -> list[list[int]]:
    bounds: list[list[int]] = []
    for element in elements:
        if element.get("resource_id") != RID["private_tile"] or not element.get("clickable"):
            continue
        b = element.get("bounds")
        if (
            isinstance(b, list)
            and len(b) == 4
            and all(isinstance(v, int) for v in b)
            and b[2] > b[0]
            and b[3] > b[1]
        ):
            bounds.append(b)
    return sorted(bounds, key=lambda b: (b[1], b[0]))


def _private_post_matches(elements: list[dict[str, Any]], caption: str) -> bool:
    exact_caption = any(
        element.get("resource_id") == RID["post_caption"]
        and (element.get("text") or "").strip() == caption
        for element in elements
    )
    private_label = any(
        element.get("resource_id") == RID["private_label"]
        and (element.get("text") or "").strip() == "私密"
        for element in elements
    )
    return exact_caption and private_label


def _verification_evidence(prefix: str) -> dict[str, Any]:
    result = _run(
        f"{prefix}-evidence",
        [
            {
                "action_id": "verified-evidence",
                "action": "screenshot",
                "filename": "profile-private-verified.png",
            }
        ],
        max_duration_ms=20_000,
    )
    shot = result["actions"][0]["data"]
    evidence_path = shot.get("evidence_path")
    if not evidence_path:
        raise TikTokCoreError("profile verification screenshot was not exported", result)
    source = UI_JOBS / result["job_id"] / evidence_path
    if not source.is_file():
        raise TikTokCoreError(f"profile verification evidence missing: {source}", result)
    return {
        "workflow_job_id": result["job_id"],
        "evidence": {
            "relative_path": evidence_path,
            "source_path": str(source),
            "size": source.stat().st_size,
        },
    }


def _open_private_grid_unlocked(prefix: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _recover_home_unlocked(f"{prefix}-recover")
    result = _run(
        f"{prefix}-open-grid",
        [
            {
                "action_id": "wait-profile",
                "action": "waitFor",
                "selector": {"resource_id": RID["profile"], "clickable": True},
                "unique": True,
                "timeout_ms": 15_000,
            },
            {
                "action_id": "open-profile",
                "action": "click",
                "selector": {"resource_id": RID["profile"], "clickable": True},
                "expect": {"selector": _private_tab_selector(), "unique": True},
                "timeout_ms": 20_000,
                "side_effect": "REVERSIBLE_LOCAL",
            },
            {
                "action_id": "open-private-tab",
                "action": "click",
                "selector": _private_tab_selector(),
                "expect": {
                    "selector": _private_tab_selector(selected=True),
                    "unique": True,
                },
                "timeout_ms": 15_000,
                "side_effect": "REVERSIBLE_LOCAL",
            },
            {"action_id": "observe-private-grid", "action": "observe"},
        ],
        max_duration_ms=60_000,
    )
    elements = result["actions"][-1]["data"]["elements"]
    return elements, result


def verify_private_post(
    caption: str,
    *,
    timeout_sec: int = 75,
    max_candidates: int = 12,
) -> dict[str, Any]:
    """Verify publication without ever invoking Publish.

    Profile/private-tab navigation is semantic. TikTok private-grid tiles expose
    no caption or stable identity in accessibility, so reconciliation uses the
    *current observed* bounds of semantic private-video tile nodes only as a
    read-only navigation fallback. No absolute coordinates are stored or reused.
    Success requires exact caption text plus the explicit 私密 label.
    """
    if not caption:
        raise TikTokCoreError("caption must be non-empty")
    deadline = time.monotonic() + max(15, timeout_sec)

    with ui_lease():
        # Fast-path an already-open matching private post, useful after a commit
        # or a previous reconciliation inspection.
        _, current, _ = _observe("verify-current")
        if _private_post_matches(current, caption):
            evidence = _verification_evidence("verify-current")
            return {
                "verified": True,
                "method": "generic_profile_private_exact_caption",
                "caption": caption,
                "candidate_ordinal": 0,
                **evidence,
            }

        grid, grid_result = _open_private_grid_unlocked("verify-private")
        candidate_limit = min(max_candidates, len(_video_tile_bounds(grid)))

        for ordinal in range(candidate_limit):
            if time.monotonic() >= deadline:
                break
            tiles = _video_tile_bounds(grid)
            if ordinal >= len(tiles):
                break
            b = tiles[ordinal]
            x = (b[0] + b[2]) // 2
            y = (b[1] + b[3]) // 2

            # Justified fallback: private tiles have identical accessibility
            # selectors. Coordinates are derived from the current semantic
            # ev2 node bounds and are never hard-coded or persisted.
            _root(f"input tap {x} {y}", timeout=15)
            time.sleep(2.5)
            _, detail, _ = _observe(f"verify-candidate-{ordinal + 1}")
            if _private_post_matches(detail, caption):
                evidence = _verification_evidence(
                    f"verify-candidate-{ordinal + 1}"
                )
                return {
                    "verified": True,
                    "method": "generic_profile_private_exact_caption",
                    "caption": caption,
                    "candidate_ordinal": ordinal + 1,
                    "profile_workflow_job_id": grid_result["job_id"],
                    **evidence,
                }

            # Candidate mismatch is read-only. Return to the private grid and
            # re-observe before deriving the next candidate bounds.
            _run(
                f"verify-back-{ordinal + 1}",
                [
                    {
                        "action_id": "back",
                        "action": "pressBack",
                        "side_effect": "REVERSIBLE_LOCAL",
                    }
                ],
                max_duration_ms=15_000,
            )
            time.sleep(1.5)
            _, grid, _ = _observe(f"verify-grid-{ordinal + 1}")
            if not _video_tile_bounds(grid):
                grid, grid_result = _open_private_grid_unlocked(
                    f"verify-recover-{ordinal + 1}"
                )

    raise TikTokCoreError(
        "profile verification failed: exact PRIVATE caption not found "
        f"within {max_candidates} visible candidates"
    )
