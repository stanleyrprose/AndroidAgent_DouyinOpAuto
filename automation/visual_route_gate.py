"""Rev3.7 D-G3 production release authority, deliberately CLOSED.

This is NOT a user request flag, route selector option, environment toggle,
or evidence-provider assertion. No real-device D-G3 acceptance artifact has
been merged. Even apparently valid visual evidence is non-authoritative.

Opening this gate later requires a reviewed source change plus an accepted
real-device D-G3 receipt and corresponding Android-driver JIT verifier.
"""
from __future__ import annotations

# Immutable deployment baseline for Sprint 1/1A. Runtime requests cannot
# change this. The Java interactive driver separately hard-blocks visual
# mutations until its own real-device JIT verifier is accepted.
DG3_PRODUCTION_ENABLED = False


def is_visual_mutation_accepted() -> bool:
    return DG3_PRODUCTION_ENABLED is True
