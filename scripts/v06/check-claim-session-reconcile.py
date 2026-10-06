#!/usr/bin/env python3
from common import sprint_gated
raise SystemExit(sprint_gated(
    "resource-session-reconcile",
    owner="Sprint 3",
    contract="a recovery ownership session gets a new resource session id and generation; old mutating work is never rebound",
))
