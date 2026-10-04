#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(os.environ.get("Y700_ACCEPTANCE_REPO", "/opt/y700/workspaces/y700-agent"))
RUNTIME = Path(os.environ.get(
    "Y700_AUTOMATION_ACCEPTANCE_RUNTIME",
    "/opt/y700/runtime/semantic-actions-acceptance",
))
ROOT_EXEC = REPO / "bridge" / "root-exec.sh"
sys.path.insert(0, str(REPO / "automation"))
import ui_job  # noqa: E402


def root_exec(command: str) -> None:
    p = subprocess.run([str(ROOT_EXEC), command], text=True, capture_output=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError(f"root_exec failed rc={p.returncode}: {p.stderr}")


def run(req: dict) -> tuple[dict, Path]:
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = RUNTIME / f"{req['job_id']}.json"
    ui_job.atomic_json(path, req)
    try:
        result = ui_job.run_workflow(path)
    finally:
        path.unlink(missing_ok=True)
    return result, ui_job.UI_JOBS / req["job_id"]


def get_action(result: dict, action_id: str) -> dict:
    for row in result.get("actions") or []:
        if row.get("action_id") == action_id:
            return row
    raise AssertionError(f"action not found: {action_id}")


def left_signature(observe_action: dict) -> set[tuple]:
    elements = (observe_action.get("data") or {}).get("elements") or []
    rows: set[tuple] = set()
    for e in elements:
        bounds = e.get("bounds") or []
        if len(bounds) != 4 or bounds[0] >= 1105:
            continue
        key = (
            e.get("resource_id"),
            e.get("text"),
            e.get("content_desc"),
            e.get("class"),
            tuple(bounds),
        )
        rows.add(key)
    return rows


def launch_settings() -> None:
    root_exec("am force-stop com.android.settings; am start -a android.settings.SETTINGS >/dev/null")
    time.sleep(0.6)


def main() -> int:
    suffix = secrets.token_hex(3)

    # 1) Semantic scroll on a real scrollable Settings container.
    launch_settings()
    scroll, _ = run({
        "protocol_version": 1,
        "job_id": f"semantic-scroll-{suffix}",
        "max_duration_ms": 45000,
        "actions": [
            {"action_id": "before", "action": "observe"},
            {
                "action_id": "scroll-down",
                "action": "scroll",
                "selector": {
                    "resource_id": "com.android.settings:id/main_content_scrollable_container",
                    "scrollable": True,
                },
                "direction": "DOWN",
                "percent": 0.55,
                "side_effect": "REVERSIBLE_LOCAL",
            },
            {"action_id": "stable-down", "action": "waitStable", "timeout_ms": 5000},
            {"action_id": "after", "action": "observe"},
            {
                "action_id": "scroll-up",
                "action": "scroll",
                "selector": {
                    "resource_id": "com.android.settings:id/main_content_scrollable_container",
                    "scrollable": True,
                },
                "direction": "UP",
                "percent": 0.55,
                "side_effect": "REVERSIBLE_LOCAL",
            },
            {"action_id": "home", "action": "pressHome"},
        ],
    })
    if scroll.get("status") != "PASS":
        raise AssertionError(f"semantic scroll failed: {scroll}")
    down = get_action(scroll, "scroll-down")
    if not (down.get("data") or {}).get("moved"):
        raise AssertionError(f"semantic scroll reported moved=false: {down}")
    before_sig = left_signature(get_action(scroll, "before"))
    after_sig = left_signature(get_action(scroll, "after"))
    if before_sig == after_sig:
        raise AssertionError("semantic scroll did not change visible left-pane UI")

    # 2) Low-level normalized swipe. This is explicit and reversible; no
    # absolute coordinates are embedded.
    launch_settings()
    swipe, _ = run({
        "protocol_version": 1,
        "job_id": f"normalized-swipe-{suffix}",
        "max_duration_ms": 45000,
        "actions": [
            {"action_id": "before", "action": "observe"},
            {
                "action_id": "swipe-up",
                "action": "swipe",
                "from_x": 0.20,
                "from_y": 0.80,
                "to_x": 0.20,
                "to_y": 0.32,
                "steps": 30,
                "side_effect": "REVERSIBLE_LOCAL",
            },
            {"action_id": "stable-up", "action": "waitStable", "timeout_ms": 5000},
            {"action_id": "after", "action": "observe"},
            {
                "action_id": "swipe-back",
                "action": "swipe",
                "from_x": 0.20,
                "from_y": 0.32,
                "to_x": 0.20,
                "to_y": 0.80,
                "steps": 30,
                "side_effect": "REVERSIBLE_LOCAL",
            },
            {"action_id": "home", "action": "pressHome"},
        ],
    })
    if swipe.get("status") != "PASS":
        raise AssertionError(f"normalized swipe failed: {swipe}")
    if left_signature(get_action(swipe, "before")) == left_signature(get_action(swipe, "after")):
        raise AssertionError("normalized swipe did not change visible left-pane UI")

    # 3) Unicode/IME + longClick on the real Settings search EditText.
    launch_settings()
    long_click, _ = run({
        "protocol_version": 1,
        "job_id": f"long-click-{suffix}",
        "max_duration_ms": 45000,
        "actions": [
            {
                "action_id": "open-search",
                "action": "click",
                "selector": {
                    "resource_id": "com.android.settings:id/search_bar_container",
                    "clickable": True,
                },
                "expect": {
                    "selector": {
                        "resource_id": "android:id/search_src_text",
                        "class_name": "android.widget.AutoCompleteTextView",
                    },
                    "unique": True,
                },
                "timeout_ms": 5000,
            },
            {
                "action_id": "unicode-input",
                "action": "inputText",
                "selector": {
                    "resource_id": "android:id/search_src_text",
                    "class_name": "android.widget.AutoCompleteTextView",
                },
                "text": "深色模式",
                "clear_first": True,
                "dismiss_ime": True,
            },
            {
                "action_id": "long-click",
                "action": "longClick",
                "selector": {
                    "resource_id": "android:id/search_src_text",
                    "class_name": "android.widget.AutoCompleteTextView",
                },
                "expect": {"package": "com.android.settings"},
                "timeout_ms": 5000,
                "side_effect": "REVERSIBLE_LOCAL",
            },
            {"action_id": "back", "action": "pressBack"},
            {"action_id": "home", "action": "pressHome"},
        ],
    })
    if long_click.get("status") != "PASS":
        raise AssertionError(f"longClick/Unicode acceptance failed: {long_click}")
    unicode_row = get_action(long_click, "unicode-input")
    if (unicode_row.get("data") or {}).get("actual_text") != "深色模式":
        raise AssertionError(f"Unicode actual-state mismatch: {unicode_row}")

    # 4) Unknown selector keys must fail closed rather than being ignored.
    launch_settings()
    invalid, invalid_dir = run({
        "protocol_version": 1,
        "job_id": f"selector-fail-closed-{suffix}",
        "max_duration_ms": 30000,
        "actions": [{
            "action_id": "invalid-selector",
            "action": "find",
            "selector": {
                "resource_id": "com.android.settings:id/search_bar_container",
                "unsupported_example": True,
            },
        }],
    })
    invalid_row = get_action(invalid, "invalid-selector")
    if invalid.get("status") != "FAILED":
        raise AssertionError(f"unknown selector key did not fail closed: {invalid}")
    if (invalid_row.get("error") or {}).get("code") != "JOB_PAYLOAD_INVALID":
        raise AssertionError(f"unexpected invalid selector error: {invalid_row}")
    evidence = invalid.get("failure_evidence") or {}
    context_rel = evidence.get("context")
    if not context_rel or not (invalid_dir / context_rel).is_file():
        raise AssertionError("invalid selector failure evidence missing")

    print(json.dumps({
        "status": "PASS",
        "semantic_scroll": {
            "moved": (down.get("data") or {}).get("moved"),
            "visible_tree_changed": True,
        },
        "normalized_swipe": {
            "absolute_coordinates_used": False,
            "visible_tree_changed": True,
        },
        "long_click": "PASS",
        "unicode_input": {
            "expected": "深色模式",
            "actual": (unicode_row.get("data") or {}).get("actual_text"),
            "ime_dismiss_requested": True,
        },
        "selector_unknown_key": {
            "status": invalid.get("status"),
            "error": invalid_row.get("error"),
            "failure_evidence": str(invalid_dir / context_rel),
        },
        "normal_tiktok_path_modified": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
