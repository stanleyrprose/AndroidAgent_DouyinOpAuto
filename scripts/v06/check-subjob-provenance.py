#!/usr/bin/env python3
from common import sprint_gated
raise SystemExit(sprint_gated(
    "subjob-provenance",
    owner="Sprint 3",
    contract="mutating subordinate jobs require parent capability, top backend, role, and exact resource guard",
))
