# Vision Locator Sprint V1 Acceptance — 2026-10-05

Status: **PASS**

Scope: PRD v0.3 Sprint V1 Production Template Vision capability only. Sprint V2
OCR and Sprint V3 hybrid routing remain out of scope and disabled.

## Accepted architecture

- Vision remains a locator backend inside the existing Android Automation Core.
- Selector routing remains semantic-first.
- Template Vision is considered only through an explicit `vision_template`
  fallback when the semantic selector does not resolve.
- Action execution, postcondition evaluation, recovery/evidence and durable
  workflow state remain shared with the semantic path.
- External irreversible / COMMIT actions remain Vision-denied by default.
- Bridge v2 remains the durable workflow/session SOT.
- No new public listener, message queue, socket transport or per-frame filesystem
  protocol was introduced.

## Real-device environment

- Device: Lenovo TB323FU / Android 16 / arm64.
- OpenCV: Maven `org.opencv:opencv:4.12.0`.
- Primary capture path: Android-side in-memory screenshot path accepted in Sprint V0.
- V1 target: debug-only custom Canvas control with no useful semantic child.
- Production-style action: template bbox -> shared UiDevice click -> shared semantic
  postcondition.

## Native OpenCV integration closure

The Android 16 device initially exposed two independent integration issues:

1. `extractNativeLibs=false` left the installed target app native-library
   directory empty even though OpenCV was present in the APK.
2. OpenCV 4.12's generated `Core.NATIVE_LIBRARY_NAME` is
   `opencv_java4120`, while the Android AAR's own `StaticHelper` and packaged
   native library use `opencv_java4`.

Final source behavior:

- `packaging.jniLibs.useLegacyPackaging=true` makes the target APK install with
  extracted arm64 native libraries.
- The target app owns OpenCV initialization through `OpenCVLoader.initLocal()`,
  so loading occurs in the target application's class loader/native namespace.
- Instrumentation retains fail-closed fallback diagnostics if bootstrap fails.
- JNI availability is proven by a native `Core.getVersionString()` call after load.

Real-device verification:

```text
extractNativeLibs = true
libc++_shared.so   present
libopencv_java4.so present
single Vision fallback smoke = PASS
```

## Gate V1 result

Durable acceptance result:

```text
vision-v1-20261005-074917.json
```

Gate:

| Check | Result |
| --- | --- |
| semantic-first path wins without Vision request | PASS |
| repeated locate -> click -> postcondition | 20/20 PASS |
| success-rate threshold >= 95% | PASS (100%) |
| alpha-aware template | PASS |
| ambiguity fail-closed | PASS |
| wrong template SHA fail-closed | PASS |
| postcondition failure surfaced with durable evidence | PASS |
| high-risk Vision blocked | PASS |
| Vision disabled returns to semantic behavior | PASS |
| wrong-target destructive action | 0 |
| absolute-coordinate primary path | not used |

Observed host end-to-end latency across the 20 repeated runs:

```text
P50 = 5305.7 ms
max = 6708.5 ms
```

Matcher/capture timing remains separately exposed through the Vision metrics; the
host timing above includes instrumentation and workflow orchestration overhead.

## Acceptance defect fixes

Two test-only lifecycle defects were exposed by the first post-OpenCV gate:

- `benchmark_clicked=true` changed the Canvas rendering but did not initialize
  the accessibility content description, so the semantic-first test incorrectly
  fell through to Vision.
- benchmark activity foreground readiness used a fixed 500 ms sleep and produced
  one intermittent `TEST_BENCHMARK_UNAVAILABLE` in an otherwise passing 20-run
  sequence.

Accepted fixes:

- initialize `VISION_V1_CLICKED` semantic state when the benchmark starts in
  clicked mode;
- replace the fixed 500 ms sleep with a bounded 2500 ms foreground-readiness
  poll used only by the test benchmark.

The final gate then completed at 20/20.

## Artifact deployment path

The same V1 work also hardened Mac -> Y700 binary delivery:

```text
Mac build
-> capability-scoped artifact manifest
-> Y700 HTTPS pull to .part
-> byte-size + SHA-256 verification
-> atomic completed bundle
-> second SHA-256 gate
-> root bridge
-> pm install
```

SSH/CodexPro remains the control plane; APK bytes no longer depend on long-lived
SCP transfer. Existing media export semantics remain backward compatible.

Final accepted installed candidate hashes:

```text
app  = f2c691a71dfcb9471dd65b0b0a640ffe6efb0535ac5b17ef0391abb6e96d9e43
test = 35578bc7ae8d2823aae596907bd3c0abc2610cd6eb83c488930ad3302d09bb8f
```

## Regression

Post-gate regression:

```text
Vision policy/evidence unit tests       13/13 PASS
TikTok/state/publish routing tests      19/19 PASS
Artifact gateway tests                   4/4 PASS
Python compile checks                    PASS
Android app + androidTest build          PASS
```

The accepted TikTok semantic DRY_RUN implementation was not modified.

## Safety / rollback

V1 capability acceptance does not require global Vision enablement.

```text
vision.enabled = false
```

continues to bypass Vision and preserve semantic behavior. Template Vision can
therefore be enabled only for explicitly migrated selectors/workflows.

Production OCR remains disabled. No V2 OCR runtime or V3 hybrid routing was
introduced.

## Gate V1 disposition

```text
semantic path unchanged / preferred                 PASS
explicit semantic -> template fallback              PASS
20 repeated locate-click-verify runs                20/20 PASS
successful postcondition >= 95%                     PASS (100%)
zero wrong-target destructive action                PASS
no absolute-coordinate primary path                 PASS
alpha / ambiguity / asset integrity                 PASS
postcondition failure evidence                      PASS
high-risk Vision default deny                       PASS
independent Vision disable rollback                 PASS
semantic/publish regression                         PASS
```

**Gate V1 = PASS.**

## Production release closure

The accepted executable baseline was fast-forwarded to GitHub `main` at
`330be74` and released on Y700 as immutable worktree
`/opt/y700/workspaces/y700-agent-release-330be74`. The stable
`/opt/y700/workspaces/y700-agent` pointer was atomically switched to that
release; the prior `y700-agent-release-a0dc24d` remains the recorded rollback
target.

After the switch:

- CodexPro, Cloudflare tunnel, Android bridge and job directory reported HEALTHY;
- root bridge round-trip returned `uid=0(root)`;
- semantic-first real-device sanity PASS with `locator_source=semantic`;
- template fallback real-device sanity PASS with `locator_source=vision_template`,
  confidence approximately 0.9544 and postcondition PASS.

Accepted capability state:

```text
Template Vision capability: READY
default/global Vision routing: OFF unless explicitly requested
OCR: OFF
V3 hybrid routing: NOT STARTED
```
