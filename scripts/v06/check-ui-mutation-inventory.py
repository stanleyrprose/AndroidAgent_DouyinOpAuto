#!/usr/bin/env python3
"""Inventory production UI mutation entrypoints without asserting post-Sprint1 migration."""
from __future__ import annotations
import re
from pathlib import Path
from common import PASS, emit, repo_root

root = repo_root()
patterns = {
    "pressHome": re.compile(r"pressHome"),
    "pressBack": re.compile(r"pressBack"),
    "root_input_tap": re.compile(r"\binput\s+tap\b"),
    "ui_lease": re.compile(r"ui_lease\s*\("),
    "android_ui_lock": re.compile(r"android-ui\.lock"),
}
rows = {key: [] for key in patterns}
for base in ("apps", "automation", "publisher", "scripts"):
    for path in (root / base).rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".sh", ".java", ".kt", ".kts"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for key, pattern in patterns.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                rows[key].append({"path": str(path.relative_to(root)), "line": line})
legacy_safe = False
ui_job = (root / "automation" / "ui_job.py").read_text(encoding="utf-8")
for line in ui_job.splitlines():
    if line.startswith("SAFE_ACTIONS") and "pressHome" in line and "pressBack" in line:
        legacy_safe = True
        break
raise SystemExit(emit("ui-mutation-inventory", PASS,
    inventory=rows,
    legacy_presshome_back_safe_classification=legacy_safe,
    migration_required=legacy_safe,
    production_assertion=False))
