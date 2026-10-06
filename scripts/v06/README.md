# Y700 v0.6 Rev3.6 — Phase 0B validation tooling

This directory is validation-only. Rev3.6 does **not** authorize production Gateway/Core/Bridge behavior changes.

Every check emits one machine-readable JSON document with `status: PASS|FAIL`.

P0B checks required before Production Runtime Implementation Authorization include baseline, runtime permissions, UI mutation inventory, semantic vectors, fingerprint reference, synthetic admission/fsync load, proc visibility, clock/boot evidence, installed-app evidence, overlay inventory, suspend/wake-lock characterization, and the fault-harness self-test. Sprint-gated checks are represented now by executable fixtures/inventories only.

Hardware-independent frozen-contract checks run in GitHub CI. Real-device empirical gates must run on the Y700.

Evidence rules:
- `clock-source.py` and `suspend-wakelock-policy.py` stay FAIL until `--suspend-evidence-file` points to a controlled same-boot suspend/wake JSON sample.
- `zui-overlay-inventory.py` stays FAIL until `--coverage-evidence-file` declares all required scenarios (IME, transient notification, ZUI/game overlay, sidebar/split anchor, PiP, accessibility overlay), records whether each is present, captures every present scenario, and supplies the proposed exact allowlist.
- CI never fabricates either hardware evidence set.

Examples:
```bash
python scripts/v06/semantic-vectors.py
python scripts/v06/ui-mutation-inventory.py
python scripts/v06/admission-lock-load.py  # concurrent cold TikTok + media decode/I/O + fsync/admission contention
python scripts/v06/clock-source.py --suspend-evidence-file /path/to/evidence.json
python scripts/v06/suspend-wakelock-policy.py --suspend-evidence-file /path/to/evidence.json
python scripts/v06/zui-overlay-inventory.py --coverage-evidence-file /path/to/evidence.json
```
