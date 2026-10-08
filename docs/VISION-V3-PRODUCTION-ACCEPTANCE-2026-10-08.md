# Y700 Vision Locator — Sprint V3 Production Acceptance

Date: 2026-10-08

Status: **DRAFT — PRODUCTION AUTHORIZED / FINAL CLEAN REVALIDATION PENDING**

## Authorization

The user explicitly authorized Sprint V3 production hybrid routing on
2026-10-08.

Production behavior remains explicit-request only:

```text
Semantic Locator = primary
Template Vision = fallback when explicitly enabled/requested
OCR Vision = fallback when explicitly enabled/requested
global/default Vision routing = OFF
external irreversible / COMMIT Vision = DENY by default
```

## Current-main real-Y700 gate

Gate code baseline:

```text
feat/vision-locator-v3 = 36ec11618bb1bdf1aa9d68f7b2bb4bb98a4aaa27
origin/main baseline   = 120a0265492b724541f4746fb7fb46394571a0a4
```

Durable result:

```text
/opt/y700/runtime/vision-v3-current-main/vision-v3-20261008-033237.json
```

Accepted results:

```text
status = PASS
semantic_only_no_regression = true
invalid_recovery_fail_closed = true
mixed_template_to_ocr = true
representative_mixed_pass = true
known_popup_recovery = true
known_popup_template_fallback = true
stale_target_reresolve = true
vision_commit_blocked = true
metadata_only_route_evidence = true
cold_start_passes = 20/20
cold_start_success_rate = 1.0
duplicate_target_actions = 0
duplicate_commit_actions = 0
target_click_count_proved_by_postcondition = true
```

Cold-start end-to-end latency on this production-authorization rerun:

```text
P50 = 10610.95 ms
P95 = 11192.30 ms
max = 11620.10 ms
```

The slower latency versus the historical 2026-10-07 engineering gate does not
change the frozen correctness threshold; the PRD V3 acceptance threshold is
workflow correctness (>=95% PASS) with zero duplicate commit action and no
semantic-only regression.

## Candidate artifact identity

The authorization-only code change does not alter the Vision algorithms. The
accepted Android artifacts are byte-identical to the historical V3 engineering
candidate:

```text
app  = 791478bb3ee74dca52503bbd62fa704143f76de3ed485d4a7d1412c129268956
test = 38566b77fa65afc24bf0eea5d58ad04205ece265b326639ac0d16dd9bf6f877f
```

## Safety invariants retained

- semantic resolution remains first and bypasses Vision when unique;
- hybrid fallback order is deterministic: template before OCR;
- template ambiguity remains fail-closed;
- stale/rotation-invalid targets are discarded before input and may re-resolve
  only before the side effect;
- a failed postcondition after input does not cascade into another locator/action;
- known-popup recovery remains package/context bound;
- fallback remains bounded to at most eight Vision candidates;
- global/default Vision remains OFF;
- external irreversible / COMMIT Vision remains denied by default;
- Bridge v2 durable state and the shared Action Executor/postcondition remain
  authoritative.

## Production decision

Gate V3 is accepted for production promotion. Hybrid routing may be used only
when a workflow explicitly enables Vision and supplies bounded Vision fallback
candidates.
