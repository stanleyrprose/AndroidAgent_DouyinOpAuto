#!/usr/bin/env python3
"""Read-only v0.5 to v0.6 upgrade safety gate."""
from __future__ import annotations
import json
from common import PASS, FAIL, emit, runtime_root

claim = runtime_root() / "android-ui.claim.json"
publisher = runtime_root() / "state" / "publisher.json"
publisher_state = None
publisher_job = None
if publisher.is_file():
    try:
        data = json.loads(publisher.read_text(encoding="utf-8"))
        publisher_state = data.get("status")
        publisher_job = data.get("job_id")
    except Exception:
        publisher_state = "unreadable"

unsafe = publisher_state in {"COMMITTING", "AMBIGUOUS_COMMIT_NEEDS_RECONCILE"}
ok = not claim.exists() and not unsafe and publisher_state != "unreadable"
raise SystemExit(emit(
    "v05-to-v06-upgrade-gate",
    PASS if ok else FAIL,
    durable_ui_claim_present=claim.exists(),
    publisher_state=publisher_state,
    publisher_job_id=publisher_job,
    unsafe_publish_state=unsafe,
))
