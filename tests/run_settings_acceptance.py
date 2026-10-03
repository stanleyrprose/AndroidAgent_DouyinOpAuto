#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("/opt/y700/workspaces/y700-agent")
RUNTIME = Path("/opt/y700/runtime/automation-driver")
ROOT_EXEC = REPO / "bridge" / "root-exec.sh"

sys.path.insert(0, str(REPO / "automation"))
import ui_job  # noqa: E402


def root_exec(command: str) -> None:
    p = subprocess.run([str(ROOT_EXEC), command], text=True, capture_output=True, timeout=30)
    if p.returncode != 0:
        raise RuntimeError(f"root_exec failed rc={p.returncode}: {p.stderr}")


def run(req: dict) -> dict:
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = RUNTIME / f"{req['job_id']}.json"
    ui_job.atomic_json(path, req)
    try:
        return ui_job.run_workflow(path)
    finally:
        path.unlink(missing_ok=True)


def get_checked(result: dict, action_id: str) -> bool:
    for action in result.get("actions", []):
        if action.get("action_id") == action_id:
            return bool(action["data"]["element"]["checked"])
    raise KeyError(action_id)


def main() -> int:
    suffix = secrets.token_hex(3)

    root_exec("am force-stop com.android.settings; am start -a android.settings.SETTINGS >/dev/null")
    time.sleep(0.5)

    search_result = {
        "class_name": "android.widget.LinearLayout",
        "clickable": True,
        "has_parent": {"resource_id": "com.android.settings:id/list_results"},
        "has_descendant": {"resource_id": "android:id/title", "text": "深色模式"},
    }

    nav = run({
        "protocol_version": 1,
        "job_id": f"settings-accept-nav-{suffix}",
        "max_duration_ms": 60000,
        "actions": [
            {"action_id": "stable-home", "action": "waitStable", "timeout_ms": 5000},
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
                        "editable": True,
                    },
                    "unique": True,
                },
                "timeout_ms": 5000,
            },
            {
                "action_id": "search",
                "action": "inputText",
                "selector": {
                    "resource_id": "android:id/search_src_text",
                    "editable": True,
                },
                "text": "深色模式",
                "clear_first": True,
                "dismiss_ime": True,
            },
            {
                "action_id": "wait-result",
                "action": "waitFor",
                "selector": search_result,
                "unique": True,
                "timeout_ms": 8000,
            },
            {
                "action_id": "open-result",
                "action": "click",
                "selector": search_result,
                "expect": {
                    "selector": {
                        "resource_id": "com.android.settings:id/dark_mode_white_check"
                    },
                    "unique": True,
                },
                "timeout_ms": 5000,
            },
            {"action_id": "stable-display", "action": "waitStable", "timeout_ms": 5000},
            {
                "action_id": "read-light",
                "action": "find",
                "selector": {
                    "resource_id": "com.android.settings:id/dark_mode_white_check"
                },
            },
            {
                "action_id": "read-dark",
                "action": "find",
                "selector": {
                    "resource_id": "com.android.settings:id/dark_mode_black_check"
                },
            },
            {
                "action_id": "initial-shot",
                "action": "screenshot",
                "filename": "initial-mode.png",
            },
        ],
    })
    if nav.get("status") != "PASS":
        print(json.dumps({"status": "FAILED", "phase": "navigate", "result": nav}, ensure_ascii=False, indent=2))
        return 1

    initial_light = get_checked(nav, "read-light")
    initial_dark = get_checked(nav, "read-dark")
    if initial_light == initial_dark:
        print(json.dumps({
            "status": "FAILED",
            "phase": "initial-state",
            "reason": "expected exactly one mode to be checked",
            "light": initial_light,
            "dark": initial_dark,
        }, ensure_ascii=False, indent=2))
        return 1

    target_mode = "dark" if initial_light else "light"
    target_parent = (
        "com.android.settings:id/dark_mode_black"
        if target_mode == "dark"
        else "com.android.settings:id/dark_mode_white"
    )
    target_check = (
        "com.android.settings:id/dark_mode_black_check"
        if target_mode == "dark"
        else "com.android.settings:id/dark_mode_white_check"
    )
    opposite_check = (
        "com.android.settings:id/dark_mode_white_check"
        if target_mode == "dark"
        else "com.android.settings:id/dark_mode_black_check"
    )
    restore_parent = (
        "com.android.settings:id/dark_mode_white"
        if initial_light
        else "com.android.settings:id/dark_mode_black"
    )
    restore_check = (
        "com.android.settings:id/dark_mode_white_check"
        if initial_light
        else "com.android.settings:id/dark_mode_black_check"
    )

    toggle = run({
        "protocol_version": 1,
        "job_id": f"settings-accept-toggle-{suffix}",
        "max_duration_ms": 60000,
        "actions": [
            {
                "action_id": "switch-target",
                "action": "click",
                "selector": {"resource_id": target_parent, "clickable": True},
                "expect": {
                    "selector": {"resource_id": target_check, "checked": True},
                    "unique": True,
                },
                "timeout_ms": 5000,
                "side_effect": "REVERSIBLE_LOCAL",
            },
            {
                "action_id": "assert-opposite-off",
                "action": "assert",
                "selector": {"resource_id": opposite_check, "checked": False},
            },
            {
                "action_id": "changed-shot",
                "action": "screenshot",
                "filename": f"changed-to-{target_mode}.png",
            },
            {
                "action_id": "restore-original",
                "action": "click",
                "selector": {"resource_id": restore_parent, "clickable": True},
                "expect": {
                    "selector": {"resource_id": restore_check, "checked": True},
                    "unique": True,
                },
                "timeout_ms": 5000,
                "side_effect": "REVERSIBLE_LOCAL",
            },
            {
                "action_id": "assert-restored-opposite-off",
                "action": "assert",
                "selector": {"resource_id": target_check, "checked": False},
            },
            {
                "action_id": "restored-shot",
                "action": "screenshot",
                "filename": "restored-original.png",
            },
            {"action_id": "home", "action": "pressHome"},
        ],
    })

    if toggle.get("status") != "PASS":
        print(json.dumps({"status": "FAILED", "phase": "toggle-restore", "result": toggle}, ensure_ascii=False, indent=2))
        return 1

    out = {
        "status": "PASS",
        "initial_mode": "light" if initial_light else "dark",
        "temporary_mode": target_mode,
        "restored_mode": "light" if initial_light else "dark",
        "navigation_job": nav["job_id"],
        "toggle_job": toggle["job_id"],
        "mac_runtime_required": False,
        "selector_mode": "semantic",
        "absolute_coordinate_used": False,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
