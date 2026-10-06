#!/usr/bin/env python3
"""Collect Android 16/ZUI window inventory; never auto-allowlist observed windows."""
from __future__ import annotations
import hashlib, re, subprocess
from common import PASS, FAIL, emit, repo_root

root_exec=repo_root()/"bridge"/"root-exec.sh"
proc=subprocess.run([str(root_exec),"dumpsys window windows"],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
raw=proc.stdout
lines=[line.strip() for line in raw.splitlines() if line.strip()]
window_lines=[line for line in lines if line.startswith("Window #") or "mInputMethodWindow=" in line]
joined="\n".join(lines).lower()
scenario={
    "ime_present": ("inputmethod" in joined or "type=2011" in joined),
    "toast_present": ("toast" in joined),
    "accessibility_overlay_present": ("accessibility" in joined and "overlay" in joined),
    "pip_present": ("pictureinpicture" in joined or "pinned" in joined),
    "floating_sidebar_present": ("freeform.sidebar" in joined),
    "notification_shade_present": ("notificationshade" in joined),
    "system_decor_present": ("screendecoroverlay" in joined or "statusbar" in joined or "taskbar" in joined),
}
packages=sorted(set(re.findall(r"\b(?:com|android)\.[A-Za-z0-9_.]+", "\n".join(window_lines))))
ok=proc.returncode==0 and bool(raw.strip()) and scenario["ime_present"] and scenario["floating_sidebar_present"] and scenario["system_decor_present"]
raise SystemExit(emit(
    "zui-overlay-inventory", PASS if ok else FAIL,
    raw_sha256=hashlib.sha256(raw.encode("utf-8",errors="replace")).hexdigest() if raw else None,
    window_lines=window_lines[:80],
    observed_packages=packages,
    scenario_matrix=scenario,
    unobserved_scenarios=[k for k,v in scenario.items() if not v],
    proposed_exact_allowlist=[],
    wildcard_allowlist=False,
    note="presence alone never grants allowlisting; unobserved scenario classes remain fail-closed until explicitly exercised",
))
