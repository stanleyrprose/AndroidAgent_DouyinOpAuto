# Y700 Vision Locator — Sprint V2 OCR Benchmark & Integration

Status: **IN PROGRESS / Gate V2 pending real-Y700 measurements**

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

Production OCR will remain separately feature-flagged from Template Vision.

Before Gate V2 passes:

```text
ocr_enabled = false
```

remains the production state.
