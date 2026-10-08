# Y700 Vision Locator — Sprint V3 Production Acceptance

Date: 2026-10-08

Status: **PASS / FROZEN — PRODUCTION HYBRID ROUTING AUTHORIZED**

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

## Clean serialized current-main real-Y700 gate

Final durable result:

```text
/opt/y700/runtime/vision-v3-production-final/vision-v3-20261008-034238.json
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

Cold-start end-to-end latency:

```text
P50 = 6040.7 ms
P95 = 7002.2 ms
max = 7010.9 ms
```

This final gate ran after the acceptance harness was hardened to use one
device-global lock across all runtime output directories. No other Vision V3
acceptance process operated the physical Y700 UI concurrently.

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

Gate V3 is accepted for production promotion. Hybrid routing may be used only when a workflow explicitly enables Vision and supplies bounded Vision fallback candidates. Global/default Vision remains OFF and external irreversible / COMMIT Vision remains denied by default.
