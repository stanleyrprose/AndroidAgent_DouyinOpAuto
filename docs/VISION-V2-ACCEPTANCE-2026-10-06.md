# Y700 Vision Locator — Sprint V2 OCR Acceptance

Date: 2026-10-06  
Status: **PASS / FROZEN**  
Scope: PRD-Y700-Vision-Locator-v0.3 Sprint V2 OCR Benchmark & Integration only. Sprint V3 remains not authorized.

## Decision

Gate V2 passes on the real Lenovo Y700. The selected runtime is:

```text
PaddleOCR PP-OCRv6 tiny
Android ARM64
ONNX Runtime
OpenCV 4.12
runtime id = paddle-ppocrv6-tiny-onnx
```

Bundled ML Kit was rejected after the clean rerun because it did not meet the frozen >=96% target-location accuracy requirement.

## Canonical evidence

Final durable component gate:

```text
/opt/y700/runtime/ocr-v2/ocr-v2-component-gate-20261006-090839.json
```

Accepted supporting evidence:

```text
/opt/y700/runtime/ocr-v2/accepted-gate-summary.json
/opt/y700/runtime/ocr-v2/accepted-accuracy-report.json
/opt/y700/runtime/ocr-v2/accepted-cold-latency-report.json
/opt/y700/runtime/ocr-v2/accepted-stress-report.json
/opt/y700/runtime/ocr-v2/accepted-low-confidence-no-click.json
/opt/y700/runtime/vision-v2/ui-jobs/vision-v2-ocr-smoke-1fbce4/result.json
```

All runtime-private screenshots and benchmark manifests remain outside public Git.

## Accuracy gate

Clean real-app dataset:

```text
6 Android Settings screens
99 targets
min_confidence = 0.85
located = 96
accuracy = 96/99 = 96.97%
required = >= 96%
result = PASS
```

The accepted matcher does not use generic fuzzy substitution for `0/O` or `1/l`. It only applies deterministic normalization that was separately regression-tested.

The request ROI remains the acceptance/click boundary. On a first-pass miss, OCR may retry with a bounded minimum 512 px inference-context height, but a returned bbox still must be fully contained by the original request ROI.

## Contract and safety gates

```text
OCR contract                           7/7 PASS
normalization/context safety           7/7 PASS
cache/change gating + timeout          2/2 PASS
lifecycle load/reuse/unload/reload     1/1 PASS
cold latency gate                      1/1 PASS
real dataset accuracy gate             1/1 PASS
200-run warm stress/resource gate      1/1 PASS
```

Bounded regex validation rejects unsafe patterns. Structured OCR timeout drains in-flight state. ROI cache is invalidated by material visual change.

## Low-confidence no-click

The shared Action Executor path was validated end-to-end.

A normal `vision_text` request resolved the benchmark text `继续` at confidence approximately 0.99999815, clicked the OCR-resolved center, and passed the shared postcondition.

The same scenario with `min_confidence=1.0` failed closed with:

```text
VISION_OCR_NOT_FOUND
ocr_low_confidence_rejected_count = 1
ocr_success_count = 0
no click_point
```

Therefore the frozen requirement **no low-confidence click** passes on the real shared action path.

## Latency envelope frozen from benchmark

```text
cold request, 20 confirmed-unloaded runs:
  P50 = 63.72 ms
  P95 = 109.05 ms

runtime cold-load component:
  P50 = 34.00 ms
  P95 = 46.40 ms

warm OCR, 200 runs:
  P50 = 43.66 ms
  P95 = 49.78 ms

clean real-dataset target wall latency:
  P50 = 32.41 ms
  P95 = 60.66 ms
```

These are measured Y700 acceptance values, not pre-benchmark assumptions.

## Thermal and memory

Warm 200-run stress evidence:

```text
success = 200/200
timeouts = 0
temperature = 34.5 C -> 34.5 C
thermal delta = 0 C

PSS before = 47,984 KB
PSS after warm = 176,365 KB
PSS delta = +128,381 KB

PSS reclaimed after unload = 54,808 KB
native memory reclaimed after unload = 87,836,896 bytes
```

The runtime completed the unload check with no in-flight OCR work. Load/unload transitions remain serialized and race-safe.

Frozen lifecycle defaults:

```text
idle_unload_timeout = 10 minutes
minimum_residency_after_load = 60 seconds
```

## Candidate comparison

```text
ML Kit bundled:
  clean rerun = 79/99 = 79.80%
  Gate V2 = FAIL for accuracy

PaddleOCR PP-OCRv6 tiny:
  clean rerun = 96/99 = 96.97%
  Gate V2 = PASS
```

The selection is therefore evidence-driven.

## Accepted APK hashes

```text
app  = c134512e24008475a341dea3fbafdf106a19380971ae520b2950ee94969cd13d
test = 7f58a59300c5222c054f906e9fd6886feebc27f3376acad36575afb40ce5c4be
```

## Frozen post-V2 capability state

```text
Semantic Locator = primary
Template Vision = explicit fallback
OCR capability = READY via explicit vision_text
OCR default = OFF
global/default Vision routing = OFF unless explicitly requested
external irreversible / COMMIT Vision = DENY
mixed Template + OCR hybrid routing = NOT ENABLED
Sprint V3 = NOT AUTHORIZED / NOT STARTED
```

Gate V2 acceptance does not authorize hybrid routing or any V3 work.
