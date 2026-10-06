#!/usr/bin/env python3
from common import sprint_gated
raise SystemExit(sprint_gated(
    "catalog-overlay-policy",
    owner="Sprint 2",
    contract="mutating catalog entries require global overlay guard; possible in-app modal requires versioned blockers",
))
