# Vision Locator Routing Policy — V0 baseline

Status: **Gate V0 accepted / production routing disabled**

The Vision Locator is a locator backend inside the existing Android Automation
Core. It is not a second workflow engine and it does not own input injection.

## Decision order

```text
semantic resolve
  ├─ RESOLVED -> semantic target, stop
  └─ NOT_FOUND / AMBIGUOUS / UNRELIABLE
        -> explicit vision fallback present?
             ├─ no  -> unresolved/recovery
             └─ yes -> routing policy
                        ├─ V0 benchmark_only -> locate only, never authorize click
                        ├─ template eligible -> template
                        ├─ OCR eligible only after Gate V2
                        └─ none -> blocked/recovery
```

No selector receives an implicit visual fallback. The workflow/selector must
explicitly carry a `vision_template` or future `vision_text` fallback (or be an
explicit vision-only benchmark request).

## Production-risk policy

| Action/risk | Default vision policy |
| --- | --- |
| observe / wait / assertion | eligible after gate if explicitly requested |
| reversible local click | eligible after Gate V0/V1 policy enablement |
| external reversible | explicit workflow opt-in + postcondition |
| external irreversible / COMMIT | **DENY by default** |

For an irreversible action, future vision routing requires all of:

1. explicit workflow opt-in;
2. independent secondary validation;
3. current package/context validation;
4. deterministic EXACT click policy;
5. existing durable COMMIT authorization boundary;
6. meaningful postcondition/reconciliation.

Matcher confidence by itself is never sufficient authorization.

## Feature gates

```text
vision_enabled=false        # rollback / current production default
mode=benchmark_only         # Sprint V0
template_enabled=true       # benchmark backend
ocr_enabled=false           # until V2 benchmark
gate_v0_passed=false        # runtime default remains fail-closed after V0 acceptance
gate_v2_passed=false        # OCR gate
allow_high_risk_vision=false
```

Sprint V0 benchmark locate/click/postcondition passed on the dedicated test
activity, but the production `AutomationInstrumentedTest#runWorkflow` selector
resolution remains unwired to Vision. Gate V0 acceptance records feasibility;
it does not flip a production feature flag. V1 activation requires separate
authorization and an explicit production configuration change.

## Why this split

Routing policy answers **whether vision may be used**. The locator answers
**where the target is**. The Action Executor remains the only component allowed
to inject input. This keeps semantic-first behavior stable and makes vision
independently disableable.


Formal Gate V0 evidence: `docs/VISION-V0-ACCEPTANCE-2026-10-05.md`.
