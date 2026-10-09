#!/usr/bin/env python3
"""Rev3.7 Sprint 1A offline fixture gate.

This is not production D-G3 acceptance: device pixel capture and latency
calibration are separate, explicitly blocking, real-device work.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


SUITES = ["tests.test_rev37_runtime_foundation.RouteSelectionTests"]


def main() -> int:
    suites = [unittest.defaultTestLoader.loadTestsFromName(name) for name in SUITES]
    result = unittest.TextTestRunner(verbosity=0, stream=sys.stderr).run(
        unittest.TestSuite(suites)
    )
    print(json.dumps({
        "gate": "SPRINT-1A-ROUTE-FIXTURES",
        "scope": "OFFLINE_FIXTURE_ONLY",
        "production_gate_passed": False,
        "status": "PASS" if result.wasSuccessful() else "FAIL",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
    }, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
