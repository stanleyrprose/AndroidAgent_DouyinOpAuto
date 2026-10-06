# Y700 Vision Locator — Sprint V2 OCR Benchmark & Integration

Status: **PASS / FROZEN — Gate V2 accepted on real Y700 (2026-10-06)**

Baseline: Gate V1 PASS. Template Vision remains available as an explicit
semantic fallback; global/default Vision routing remains off.

## Authorization boundary

Sprint V2 is authorized. Sprint V3 hybrid routing is not authorized.

V2 must not silently introduce:

- OCR before semantic/template according to the frozen routing order;
- OCR for external irreversible / COMMIT actions;
- a new daemon, MQ, socket protocol or per-frame Bridge transport;
- a permanent heavyweight OCR process without benchmark evidence;
- production OCR enablement before Gate V2 passes.

## Gate V2 requirements

The benchmark must select the minimum sufficient runtime from real Y700 evidence.

Required production-facing capability:

```text
OCR ROI
substring match
bounded regex match
bbox / center output
confidence handling
cache / ROI-change gating
structured timeout
```

Acceptance:

```text
real-app text test set
target-location accuracy >= 96%
no low-confidence click
cold + warm P50/P95 documented
memory behavior documented
thermal behavior documented
lifecycle stability documented
```

If no candidate meets the approved envelope, OCR stays disabled and V3 must not
depend on OCR.

## Candidate set

Two real mobile deployment paths are benchmarked before selection:

1. **ML Kit Text Recognition v2, bundled models**
   - bundled Latin + Chinese recognizers;
   - no first-use network/model download;
   - bbox output and OCR metadata through the Android API;
   - low integration complexity;
   - candidate adapter exists only in the debug source set until Gate V2 passes.

2. **PaddleOCR official Android ONNX Runtime path**
   - upstream benchmark baseline pinned to a specific PaddleOCR Git commit;
   - PP-OCRv6 tiny/mobile-class detection + recognition models;
   - Android/ARM64 ONNX Runtime;
   - explicit release lifecycle and stage-level timing;
   - benchmarked externally before any source/vendor integration into the
     production app.

Candidate choice is measurement-driven, not architecture preference.

## Runtime-private real-app dataset

`tests/collect_ocr_v2_dataset.py` collects screenshots plus accessibility-derived
ground-truth boxes from real Android Settings surfaces on the Y700.

The screenshots and text manifest are stored only under:

```text
/opt/y700/runtime/ocr-v2-dataset
```

and staged into the debug target app for instrumentation. They must not enter
public Git.

Ground-truth semantics are used only to score the benchmark. Production OCR does
not depend on those semantics.

Each target stores:

```text
text
script family
ground-truth bbox
bounded OCR ROI
```

Target-location success requires both matching text and a geometrically valid OCR
bbox at the expected screen location.

## ML Kit benchmark

Debug-only implementation:

```text
OcrMlKitCandidate
OcrV2MlKitBenchmarkTest
```

The benchmark records:

- first/cold request latency per script;
- warm P50/P95 latency;
- target-location accuracy;
- confidence availability/coverage;
- process PSS and native-heap delta;
- battery temperature before/after;
- per-target result metadata.

It performs no input action.

## Lifecycle work after candidate selection

The selected runtime must implement the PRD lifecycle contract:

```text
first OCR request
-> lazy load
-> in-flight reference held
-> inference
-> release in-flight reference
-> reset idle deadline
-> unload only when:
     in_flight == 0
     AND minimum residency elapsed
     AND idle timeout elapsed
```

Benchmark defaults:

```text
idle_unload_timeout = 10 minutes
minimum_residency_after_load = 60 seconds
```

Load/unload transitions must be serialized and idle-boundary requests must not
cause unload/reload thrash.

## Safety

Production OCR remains separately feature-flagged from Template Vision.

Gate V2 passing does **not** enable OCR globally or by default:

```text
vision_enabled = false by default
ocr_enabled = false by default
external irreversible / COMMIT Vision = denied by default
```

Mixed Template Vision + OCR fallback routing remains reserved for Sprint V3 and
is not enabled by this gate.

## Gate V2 final acceptance — PASS

Accepted on the real Y700 on 2026-10-06.

Selected runtime:

```text
PaddleOCR PP-OCRv6 tiny
Android ARM64
ONNX Runtime
OpenCV 4.12
runtime id = paddle-ppocrv6-tiny-onnx
```

The candidate choice is measurement-based:

- bundled ML Kit was retained through the clean benchmark rerun but reached only
  **79/99 = 79.80%** target-location accuracy and was rejected;
- PaddleOCR reached **96/99 = 96.97%** on the clean real-Settings dataset and
  therefore satisfied the frozen **>=96%** location gate;
- the accepted implementation keeps `min_confidence=0.85`; it does not lower the
  threshold to pass the benchmark and does not apply generic `0/O` or `1/l`
  fuzzy correction;
- the request ROI remains the only acceptance/click region; on a first-pass miss,
  OCR may retry with a minimum 512 px inference-context height, but a returned
  bbox must still lie completely inside the original request ROI.

The canonical clean dataset contains **6 Android Settings screens / 99 targets**.
Ground truth is used only for benchmark scoring and is not a production OCR
dependency.

Final canonical component gate:

```text
/opt/y700/runtime/ocr-v2/ocr-v2-component-gate-20261006-090839.json
```

Gate composition:

- OCR contract: **7/7 PASS**;
- normalization/context safety: **7/7 PASS**;
- cache/change gating + structured timeout: **2/2 PASS**;
- lifecycle lazy-load/warm-reuse/idle-unload/reload: **1/1 PASS**;
- repeated cold-request latency gate: **1/1 PASS**;
- clean real-dataset accuracy gate: **1/1 PASS**;
- 200-run warm stress/resource gate: **1/1 PASS**.

Final latency evidence:

```text
cold request wall latency, 20 confirmed-unloaded runs:
  P50 = 63.72 ms
  P95 = 109.05 ms
  min = 59.40 ms
  max = 141.34 ms

runtime cold-load component, 20 runs:
  P50 = 34.00 ms
  P95 = 46.40 ms

warm OCR stress, 200 runs:
  P50 = 43.66 ms
  P95 = 49.78 ms
  min = 39.53 ms
  max = 76.74 ms

clean real-dataset target wall latency, 99 targets:
  P50 = 32.41 ms
  P95 = 60.66 ms
```

Resource/lifecycle evidence from the same final gate:

- 200/200 warm requests succeeded; timeout count **0**;
- temperature: **34.5 C -> 34.5 C**, delta **0 C**;
- warm PSS delta: **+128,381 KB**;
- warm native-heap delta: **+94,459,072 bytes**;
- after test unload, PSS reclaimed from warm: **54,808 KB**;
- after test unload, native memory reclaimed from warm:
  **87,836,896 bytes**;
- runtime finished the unload check with `loaded=false` and `in_flight=0`;
- production lifecycle defaults remain idle timeout **10 minutes** and minimum
  post-load residency **60 seconds**.

Low-confidence no-click was also verified through the real shared execution path:

```text
ui_job.py
-> AutomationInstrumentedTest
-> clickOcr()
-> OcrTextLocator
-> shared Action Executor
```

A normal benchmark action with `min_confidence=0.85` resolved the text `继续`
at confidence approximately **0.99999815**, clicked the resolved OCR center and
passed the shared postcondition. The same benchmark was then reset to
`clicked=false` and rerun with `min_confidence=1.0`.

The low-confidence run:

- failed closed with `VISION_OCR_NOT_FOUND`;
- recorded `ocr_low_confidence_rejected_count=1`;
- recorded `ocr_success_count=0`;
- contained **no `click_point`** anywhere in the durable job directory;
- captured failure-time evidence while
  `com.stanley.y700automation/.VisionBenchmarkActivity` was top resumed;
- captured a failure UI tree with no `VISION_V1_CLICKED` state.

Therefore the frozen requirement **no low-confidence click** is accepted on the
shared Action Executor path, not inferred only from locator unit tests.

Accepted Gate candidate APK hashes:

```text
app  = c134512e24008475a341dea3fbafdf106a19380971ae520b2950ee94969cd13d
test = 7f58a59300c5222c054f906e9fd6886feebc27f3376acad36575afb40ce5c4be
```

Gate code baseline: `a31cd65` on `feat/vision-locator-v2`, based on current
`main` at the time of the final gate.

## Frozen boundary after V2

Gate V2 means the OCR locator capability is ready to be merged into the Android
Automation Core. It does **not** change the default routing policy:

```text
Semantic Locator = primary
Template Vision = explicit fallback
OCR = explicit vision_text only, separately feature-flagged
OCR default = OFF
external irreversible / COMMIT Vision = DENY
mixed Template + OCR hybrid routing = NOT ENABLED
```

Sprint V3 remains **NOT AUTHORIZED / NOT STARTED**.
