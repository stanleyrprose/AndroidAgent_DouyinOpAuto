# Y700 Vision Locator — Sprint V2 Current-Production Revalidation

Date: 2026-10-07  
Status: **PASS / REVALIDATED**  
Scope: Revalidate the frozen Sprint V2 capability on the current production runtime. No new V3 behavior was exercised by this revalidation.

## Why this revalidation was required

The original Sprint V2 Gate passed on 2026-10-06. Since then the shared Action Executor and production runtime advanced. During the 2026-10-07 revalidation, the first OCR sanity attempt failed before Android instrumentation with exit code 127.

Root cause was production workspace path integrity, not OCR:

- the stable workspace symlink had been promoted with an absolute `/opt/y700/...` target;
- `/opt/y700` exists in the Debian chroot namespace but not as the same absolute path in the Android host namespace;
- Android-host jobs therefore could not resolve `bridge/android-runtime-env.sh`;
- the wrapper itself and the accepted OCR runtime were healthy.

The stable release invariant is now:

```text
/opt/y700/workspaces/y700-agent
  -> y700-agent-release-<commit>
```

The target is deliberately relative because the Android host and Debian chroot share the same physical workspace directory under different namespace paths.

Preventive controls added:

- `scripts/promote-stable-release.sh` creates only basename/relative stable targets and records rollback;
- `scripts/production-sot-status.sh` reports `DRIFT` for an absolute stable symlink;
- regression tests cover both invariants.

## Current production baseline

At revalidation:

```text
main/stable = 3b93308c64487de83ba4193bec6e970610e5e30d
stable raw target = y700-agent-release-3b93308
rollback = y700-agent-release-a428cf3
production_sot = HEALTHY
android_bridge_instances = 1
overall health = HEALTHY
Cloudflare tunnel connections = 4
```

The release promotion changed runtime scripts/docs only; Android app/test source was unchanged from the immediately preceding production release.

## V2-only production sanity

Fresh jobs were run using only the V2 paths; none used a mixed Template+OCR selector.

```text
semantic:
  job = prod-current3-v2-semantic-1791356302046
  PASS
  locator_source = semantic
  ocr_enabled = false

template:
  job = prod-current3-v2-template-1791356302047
  PASS
  locator_source = vision_template
  confidence = 0.9544264674
  postcondition = PASS
  ocr_enabled = false

OCR:
  job = prod-current3-v2-ocr-1791356302048
  PASS
  locator_source = vision_text
  confidence = 0.9999981523
  postcondition = PASS
  ocr_enabled = true
```

All three reported `hybrid_template_to_ocr_fallback_count = 0`.

## Full current-production V2 component Gate

Durable evidence:

```text
/opt/y700/runtime/ocr-v2/ocr-v2-component-gate-20261007-065959.json
```

Result:

```text
OCR contract                         7/7 PASS
normalization/context safety         7/7 PASS
cache/change gating + timeout        2/2 PASS
lifecycle load/reuse/unload/reload   1/1 PASS
cold latency                         1/1 PASS
real dataset accuracy                1/1 PASS
200-run warm stress/resource         1/1 PASS

GATE_PASS
```

Real Settings dataset:

```text
screens = 6
targets = 99
located = 96
accuracy = 96/99 = 96.97%
required = >= 96%
min_confidence = 0.85
```

Measured current-production latency:

```text
cold request:
  P50 = 65.01 ms
  P95 = 96.17 ms

runtime cold load:
  P50 = 34.5 ms
  P95 = 50.05 ms

warm OCR, 200 runs:
  P50 = 45.20 ms
  P95 = 49.09 ms

real-dataset target wall:
  P50 = 33.34 ms
  P95 = 63.56 ms
```

Stress/resource result:

```text
warm runs = 200
temperature = 38.1 C -> 38.1 C
thermal delta = 0 C
PSS delta = +129,058 KB
PSS reclaimed after unload = 54,654 KB
native memory reclaimed after unload = 87,837,008 bytes
```

## Low-confidence no-click revalidation

Current evidence:

```text
/opt/y700/runtime/ocr-v2/current-revalidation-20261007/low-confidence-no-click.json
```

The test used `min_confidence=1.0` from an unclicked benchmark state.

```text
status = FAILED
terminal error = VISUAL_TIMEOUT
ocr_request_count = 4
ocr_success_count = 0
ocr_low_confidence_rejected_count = 4
click_point = absent
VISION_V1_CLICKED in failure tree = absent
hybrid_template_to_ocr_fallback_count = 0
safety result = PASS
```

The terminal error differs from the historical V2 acceptance because the current shared executor contains later bounded visual retry behavior. The frozen V2 safety invariant remains satisfied: **low-confidence OCR never produces a click**.

## Canonical current-production summary

```text
/opt/y700/runtime/ocr-v2/current-revalidation-20261007/current-production-v2-revalidation-summary.json
```

Final decision: **Sprint V2 remains PASS on current production.**
