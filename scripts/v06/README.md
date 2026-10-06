# Y700 v0.6 Rev3.6 — Phase 0B validation tooling

This directory is validation-only. Rev3.6 does **not** authorize production Gateway/Core/Bridge behavior changes.

Every check emits one machine-readable JSON document with `status: PASS|FAIL`.

P0B checks required before Production Runtime Implementation Authorization include baseline, runtime permissions, UI mutation inventory, semantic vectors, fingerprint reference, synthetic admission/fsync load, proc visibility, clock/boot evidence, installed-app evidence, overlay inventory, suspend/wake-lock characterization, and the fault-harness self-test. Sprint-gated checks are represented now by executable fixtures/inventories only.

`clock-source.py` intentionally fails with `SUSPEND_DELTA_EVIDENCE_REQUIRED` until a controlled real-device suspend/wake sample has been captured. GitHub CI must not fake this hardware evidence.

GitHub CI runs only hardware-independent frozen-contract checks. Real-device empirical gates run on the Y700.

Examples:
```bash
python scripts/v06/semantic-vectors.py
python scripts/v06/ui-mutation-inventory.py
python scripts/v06/admission-lock-load.py
python scripts/v06/clock-source.py
```
