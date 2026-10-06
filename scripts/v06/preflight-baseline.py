#!/usr/bin/env python3
from __future__ import annotations
import shutil
import subprocess
from common import PASS, FAIL, emit, repo_root, runtime_root, safe_lstat, y700_root

root = repo_root()
rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
branch = subprocess.run(["git", "branch", "--show-current"], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
target = y700_root() if y700_root().exists() else root
disk = shutil.disk_usage(target)
runtime = runtime_root()
claim = runtime / "android-ui.claim.json"
active_bridge = y700_root() / "jobs" / "active"
facts = {
    "git_revision": rev.stdout.strip() if rev.returncode == 0 else None,
    "git_branch": branch.stdout.strip() if branch.returncode == 0 else None,
    "free_bytes": disk.free,
    "runtime": safe_lstat(runtime),
    "claim_present": claim.exists(),
    "active_bridge_jobs": len(list(active_bridge.iterdir())) if active_bridge.is_dir() else None,
}
required = rev.returncode == 0 and disk.free > 512 * 1024 * 1024
raise SystemExit(emit("preflight-baseline", PASS if required else FAIL, **facts))
