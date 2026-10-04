# Y700 Vision Locator — Sprint V0 Implementation

Status: **Gate V0 PASS / production routing disabled**

Accepted reproducible benchmark commit: `979c5779f8a1a1c5b8fd842f93371364b6954609`

## Authority boundary

This Sprint implements benchmark and feasibility only. It does not migrate any
production workflow and does not add OCR to production.

Production Android Automation remains:

```text
semantic selector
-> existing Action Executor
-> postcondition
```

Vision V0 is reachable only through the dedicated debug instrumentation test.

## Implemented V0 surfaces

- Android-side in-memory capture through `UiAutomation.takeScreenshot()`;
- bounded frame ownership counters;
- raw `screencap` diagnostic capture without disk;
- explicit 4-field / legacy 3-field raw header profiles with fail-closed parsing;
- absolute ROI and normalized `roi_ratio`;
- OpenCV 4.12 template matching;
- `TM_CCOEFF_NORMED` for normal templates;
- `TM_CCORR_NORMED` + alpha mask for alpha templates;
- low-information template/candidate variance guard;
- best vs second-best ambiguity delta;
- deterministic scale-set generator;
- normalized VisionTarget bbox/center/confidence/source/source_context;
- rotation/geometry and frame-fingerprint pre-action guards;
- exactly-one capture retry with 50 ms backoff;
- simulated memory-watermark fail-closed path;
- warm 20-run capture metrics;
- 200-run capture stability loop;
- raw screencap timing;
- 250x250 / 500x500 / full-screen template timing;
- alpha-mask timing;
- narrow multi-scale timing;
- foreground package + screen/keyguard benchmark preflight;
- benchmark-only Canvas locate -> EXACT UiDevice click -> visual postcondition.

Measured capture decision on the real Y700:

```text
primary: Android-side in-memory capture
raw screencap: diagnostic/fallback only
```

Measured search decision:

```text
ROI-first -> single scale first -> narrow multi-scale when justified -> full-screen last
```

See `docs/VISION-V0-ACCEPTANCE-2026-10-05.md` for the final same-version measurements and Gate V0 evidence.

## Routing policy

See `docs/VISION-ROUTING-POLICY-v0.md`.

Current defaults:

```text
vision_enabled=false
mode=benchmark_only
ocr_enabled=false
gate_v0_passed=false        # runtime default remains fail-closed despite accepted Gate V0
allow_high_risk_vision=false
```

No production selector schema or runtime workflow currently routes to vision.

## Real-device runner

On Y700:

```bash
python3 tests/run_vision_v0_acceptance.py
```

Durable benchmark output is written under:

```text
/opt/y700/runtime/vision-v0/
```

The benchmark contains no production media and does not invoke TikTok publish.
