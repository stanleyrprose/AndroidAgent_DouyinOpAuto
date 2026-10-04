# Vision Locator Sprint V0 Acceptance — 2026-10-05

Status: **PASS**

Scope: PRD v0.3 Sprint V0 benchmark / feasibility only. This acceptance does
not authorize production workflow migration, production OCR, or automatic
semantic -> vision fallback.

## Architecture boundary

- Vision remains a locator backend inside the Generic Android Automation Core.
- Production `AutomationInstrumentedTest#runWorkflow` remains semantic-first
  and is not wired to Vision in V0.
- Bridge v2 remains the durable workflow/session SOT.
- OpenCV 4.12 is a debug-only dependency for this benchmark path.
- No new daemon, socket, MQ, database, custom ADB protocol, or per-frame
  filesystem transport was introduced.
- No TikTok publish/COMMIT action was executed by this acceptance.

## Real Y700 environment

- Device: Lenovo TB323FU / Android 16 / arm64.
- Display: 1904 x 3040, density 440.
- OpenCV: 4.12.0.
- Benchmark target: debug-only custom Canvas view with no useful semantic child
  selector.
- Foreground package is asserted before capture.
- Screen wake and keyguard-dismiss preflight are performed before the benchmark.

## Capture decision

Final reproducible real-device result (source/build commit `979c5779f8a1a1c5b8fd842f93371364b6954609`; durable result `/opt/y700/runtime/vision-v0/vision-v0-979c577.json`):

| Capture path | Runs | P50 | P95 | Result |
| --- | ---: | ---: | ---: | --- |
| Android-side in-memory `UiAutomation.takeScreenshot()` | 20 warm | 39.35 ms | 47.04 ms | PASS |
| Android-side in-memory stability | 200 | 35.93 ms | 47.58 ms | PASS |
| raw `screencap` diagnostic path | 20 | 93.75 ms | 129.14 ms | PASS |

Selected primary path:

```text
Android-side in-memory capture
```

The raw `screencap` path is retained as a diagnostic/fallback benchmark path,
not the normal hot path.

The observed raw frame profile is:

```text
profile: ANDROID_4FIELD_Y700_A16
header_bytes: 16
width: 1904
height: 3040
pixel_format: 1
dataspace: 1
bytes_per_pixel: 4
row_bytes: 7616
payload_bytes: 23152640
tightly_packed: true
```

The parser therefore does not assume a legacy fixed 12-byte header.

## Template benchmark

The real Canvas target resolved at confidence approximately **0.9987**.

| Search | P50 | P95 | Selected result |
| --- | ---: | ---: | --- |
| 250 x 250 ROI, single scale | 7.25 ms | 14.11 ms | PASS |
| 500 x 500 ROI, single scale | 14.10 ms | 15.83 ms | PASS |
| full screen, single scale | 419.92 ms | 435.52 ms | PASS but expensive |
| 500 x 500 ROI, alpha mask | 23.96 ms | 37.24 ms | PASS, confidence ~0.9995 |
| 500 x 500 ROI, narrow multi-scale 0.90–1.10 | 105.51 ms | 106.22 ms | PASS, selected scale 1.0 |

Measured policy implication:

```text
known/effective ROI
-> single scale first
-> narrow multi-scale only when scale uncertainty justifies it
-> full-screen search only when no bounded ROI is available
```

## Safety / abnormal-path acceptance

PASS:

- visible Canvas target has no semantic text/content-desc target;
- absolute ROI and normalized `roi_ratio` resolve correctly;
- portrait, landscape, and alternate window geometry mapping checked;
- `roi` + `roi_ratio` conflict fails closed as `VISION_INVALID_ROI`;
- deterministic scale generation includes max exactly once and rejects invalid
  configuration;
- low-information masked template produces an unsafe raw score of 1.0 but is
  rejected by the variance guard;
- injected first capture failure performs exactly one bounded retry;
- repeated capture failure fails closed;
- rotation/geometry mismatch returns `VISION_ROTATION_MISMATCH` and performs
  zero click;
- stale frame fingerprint returns `VISION_STALE_TARGET`;
- simulated memory watermark returns `VISION_OOM_THROTTLED`;
- 200 capture cycles peak at one concurrent full-resolution frame;
- post-GC managed/native memory did not grow in the final run;
- benchmark-only locate -> EXACT UiDevice click -> visual postcondition PASS.

Final run memory observation:

```text
managed_delta = -1,468,656 bytes
native_delta  = -2,580,672 bytes
peak_concurrent_frames = 1
```

## Semantic regression

The existing real Settings reversible acceptance was rerun after the debug
Vision/OpenCV integration:

```text
Light -> temporary Dark -> verified -> restored Light
selector_mode = semantic
absolute_coordinate_used = false
mac_runtime_required = false
PASS
```

This confirms the V0 debug capability did not change the accepted semantic
production path.

After the benchmark, the temporary V0 APKs were replaced with the exact
pre-benchmark production backups and both installed SHA-256 values were
verified:

```text
app  = 6ddd31b28360ec47e14e2392730ed5806d2e9a0cf8d6cbbf5d945ba1f10300bc
test = 234d1f4d6c59df850e67721da1f9e0b200752f707392b61b0cc30d51921a6bb1
```

A second post-restore Settings acceptance again passed with semantic selectors,
no absolute coordinates, and the original Light mode restored.

## Routing policy decision

Gate V0 passing does **not** enable production Vision routing automatically.

Production default remains fail-closed:

```text
vision_enabled=false
mode=benchmark_only
ocr_enabled=false
allow_high_risk_vision=false
```

Future production routing, only after separate authorization, is:

```text
semantic RESOLVED
  -> use semantic target; do not invoke Vision

semantic NOT_FOUND / AMBIGUOUS / UNRELIABLE
  -> only consider an explicit vision fallback
  -> template before OCR
  -> OCR only after Gate V2
  -> postcondition still required
```

External irreversible / COMMIT actions remain **Vision-denied by default**.
A future exception would still require explicit workflow authorization,
independent secondary validation, current package/context validation, EXACT
input policy, the existing durable COMMIT boundary, and reconciliation-safe
postconditions.

## Gate V0 disposition

```text
capture stable under repeated runs                         PASS
primary capture selected from measured evidence           PASS
real Canvas/custom-rendered target resolved                PASS
low-information false-positive guard demonstrated         PASS
rotation mismatch prevents stale-coordinate action        PASS
capture-failure retry bounded / fail-closed                PASS
resolve-vs-rotation race produces zero stale click         PASS
memory-pressure guard observed                             PASS
no material/unbounded frame-memory growth                  PASS
semantic-only workflow regression                          PASS
```

**Gate V0 = PASS.**

Next authorized state remains unchanged: production Vision is disabled. Sprint
V1 production Template Vision, V2 OCR, and V3 hybrid routing require separate
authorization beyond this V0 acceptance.
