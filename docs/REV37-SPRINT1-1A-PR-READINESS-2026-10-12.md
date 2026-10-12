# Rev3.7 Sprint 1 / 1A — PR Readiness and Code-Complete Gate

Status: **SOURCE REVIEW ONLY / NOT CODE COMPLETE / NO TESTS RUN**.
Authority: `docs/PRD-Y700-AAC-v0.6-Rev3.7-Frozen.md`, sections 40.2, 40.2A, 46.2, 47, 50.1 and Review Approval Record. Authorized production implementation scope is **Sprint 1 + Sprint 1A only**. Sprint 2+ and TikTok BUSINESS activation remain unauthorized.

## Source inventory (presence does not imply acceptance)

| Frozen requirement | Candidate implementation | Pre-PR verification |
|---|---|---|
| Shared android_ui Claim, ownership, durable identity | `automation/resource_arbiter.py`, `automation/ui_core_v2.py` | Concurrent access, corrupted Claim and unclaimed mutation negative tests |
| Epoch/revision/hash and stale-state rejection | `automation/state_integrity.py`, `automation/ui_core_v2.py` | Crash/CAS, manual drift, ADMIN mutation, token invalidation tests |
| Mutation prepare/commit and crash reconciliation | `automation/ui_core_v2.py`, `automation/ui_job.py`, `automation/ui_recovery_inspector.py` | PREPARED/COMMITTED durability, terminal evidence, checkpoint/Claim identity tests; no automatic replay |
| Semantic schema and exact selectors | `automation/ui_core_v2.py` and semantic fixture scripts | Frozen vector parity, ambiguous selectors, pressHome/pressBack regression |
| Deterministic route and VERIFIED_NOOP | Rev3.7 route/dispatch modules and `scripts/v07/check-conditional-dispatch.py` | D-G2 and route-table regression; no caller downgrade |
| Frame/locator identity and JIT freshness | Rev3.7 frame/vision/driver modules and `scripts/v07/check-frame-freshness.py` | Stale/rotation/display/foreground drift zero-attempt evidence; D-G3 on device before enablement |
| Support/permission separation and stage health | `scripts/v07/delta-freeze-check.py` fixtures | D-G1/D-G5 before owning implementation merge; Sprint 2 production work excluded |

## Mandatory steps before first integration PR

1. Finish Sprint 1/1A source implementation and static review; explicitly enumerate uncovered requirements and avoid widening into Sprint 2+.
2. Obtain authorization for the **concentrated test phase**; run impacted unit/fault-injection tests, frozen vectors, CI-equivalent checks, D-G1/D-G2/D-G5 as applicable; repair failures on feature branch.
3. Review empirical evidence gates (P0/D-G) and classify merge-blocking versus activation-blocking gates according to the Frozen PRD. **D-G3 is mandatory before visual mutation enablement**, not permission to activate it by default.
4. Only after tests and relevant merge gates pass: create a single integration PR for `feat/aac-rev37-sprint1a` targeting `main`, run PR CI, review, then merge on authorization. Production deployment and TikTok BUSINESS commit are separate decisions.

## Current blockers / unknowns

- No concentrated test run or real-device empirical acceptance has been authorized or executed in this development phase; PASS must not be claimed.
- Exact Sprint 1/1A code-complete coverage and negative-test outcomes require verification; this document is a readiness inventory, not a pass matrix.
- Recovery resource release, native positive-stop producer and Capability outcome reconciliation have independent closed gates; **do not open them as a shortcut to this PR**.
- `.github/workflows/validate.yml` currently triggers `push` only for `main`, and `pull_request` for PRs; feature-branch push does not trigger this workflow as inspected on 2026-10-12. Recheck immediately before the next push.

## First concentrated test results (2026-10-12)

- Rev3.7 `test_rev37*.py`: **181/181 PASS** after fixing checkpoint comparison and making a directory-mode fixture independent of process umask; on macOS use `TMPDIR=/private/tmp` to avoid the `/tmp` symlink without weakening the symlink-denial policy.
- Rev3.6 Sprint 1 regression selection: **48 tests, 1 failure, 19 errors** on macOS. Multiple tests assume Linux `/proc/sys/kernel/random/boot_id`; do **not** interpret these as a Linux/Y700 regression verdict. An existing durable Claim fixture also conflicts with stricter Claim validation. Re-run under Linux CI and review fixture assumptions before PR merge.
- `scripts/v07/delta-freeze-check.py`: PASS for **fixture-level** D-G1/D-G2/D-G3/D-G4/D-G5; this is not physical D-G3 or production acceptance.
- `scripts/v07/check-frame-freshness.py`: 30/30 PASS, `OFFLINE_FIXTURE_ONLY`, production gate false.
- `scripts/v07/check-conditional-dispatch.py`: 8/8 PASS, `OFFLINE_FIXTURE_ONLY`, production gate false.
- PR/CI/Merge remain pending: Linux regression and CI-equivalent checks must be reconciled; real-device D-G3 remains an activation gate.
