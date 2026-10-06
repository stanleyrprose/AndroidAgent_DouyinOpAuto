#!/usr/bin/env python3
from __future__ import annotations
import os
from common import PASS, FAIL, emit, runtime_root, safe_lstat, y700_root

required = [runtime_root(), y700_root() / "jobs"]
optional = [y700_root() / "ui-jobs", runtime_root() / "android-ui.lock", runtime_root() / "android-ui.claim.json"]
rows = [safe_lstat(p) for p in required + optional]
violations = []
for row in rows:
    if not row.get("exists"):
        continue
    if row.get("is_symlink") or row.get("group_or_other_write"):
        violations.append(row["path"])
    if os.geteuid() == 0 and row.get("uid") != 0:
        violations.append(row["path"] + ":owner")
missing_required = [str(p) for p in required if not p.exists()]
ok = not violations and not missing_required
raise SystemExit(emit("runtime-permission-baseline", PASS if ok else FAIL,
    paths=rows, missing_required=missing_required, violations=violations))
