#!/usr/bin/env python3
"""Collect Android 16/ZUI window inventory without creating an allowlist automatically."""
from __future__ import annotations
import hashlib
import re
import subprocess
from common import PASS, FAIL, emit, repo_root

root_exec = repo_root() / "bridge" / "root-exec.sh"
proc = subprocess.run(
    [str(root_exec), "dumpsys window windows"],
    text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45,
)
raw = proc.stdout
interesting = []
for line in raw.splitlines():
    stripped = line.strip()
    if not stripped:
        continue
    if any(token in stripped for token in (
        "Window #", "mCurrentFocus", "mFocusedApp", "type=", "InputMethod",
        "Toast", "Accessibility", "PictureInPicture", "overlay", "split",
    )):
        interesting.append(stripped[:500])
packages = sorted(set(re.findall(r"\b(?:com|android)\.[A-Za-z0-9_.]+", "\n".join(interesting))))
ok = proc.returncode == 0 and bool(raw.strip())
raise SystemExit(emit("zui-overlay-inventory", PASS if ok else FAIL,
    raw_sha256=hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest() if raw else None,
    candidate_lines=interesting[:160],
    observed_packages=packages,
    proposed_exact_allowlist=[],
    wildcard_allowlist=False,
    note="no window is allowlisted by presence alone; exact benign signatures are accepted only after scenario evidence"))
