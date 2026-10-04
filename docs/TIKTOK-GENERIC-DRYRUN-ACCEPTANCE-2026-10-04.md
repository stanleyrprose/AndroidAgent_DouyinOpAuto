# TikTok Generic Android Core — DRY_RUN Acceptance

Date: 2026-10-04  
Target: Lenovo Y700 / Android 16 / Debian 13 chroot  
Acceptance baseline: `4c19067bc63d43df1472668ec0abeff98bc82283`

## Result

**PASS — FROZEN DRY_RUN BASELINE**

The TikTok DRY_RUN controller path has been migrated to the generic Android
Automation Core without adding a final publish action to the generic adapter.
The accepted path is:

```text
force-stop TikTok
-> cold launch
-> semantic HOME readiness
-> create/upload
-> Y700Agent album
-> exactly one staged media item
-> edit
-> POST_CONFIG
-> caption
-> PRIVATE visibility
-> publish button reachable/asserted only
-> evidence screenshot
-> force-stop
```

No DRY_RUN action clicks the final TikTok Publish button.

## 20-run real-Y700 gate

Acceptance source:

`/opt/y700/runtime/tiktok-regression/4c19067.jsonl`

Result:

- runs: 20
- PASS: 20
- FAIL: 0
- pass rate: 100%
- PRD threshold: >=95% / >=19 of 20
- host workflow P50: 41,217.9 ms
- host workflow maximum: 49,640.7 ms
- `home-create` P50: 9,053.5 ms
- `home-create` maximum: 9,391 ms
- maximum recorded action latency: 9,391 ms
- regression job: `v03-dryrun-001`
- visibility: PRIVATE

All 20 runs used cold launch behavior through the generic controller.
Media staging was performed once for the fixed regression media; each counted
run exercised the UI/controller path required by the PRD.

## Reliability fixes incorporated before freeze

- one instrumentation session per workflow;
- bounded UiAutomator implicit idle wait to avoid video/animation surfaces
  producing multi-minute hidden waits;
- semantic selectors only; no absolute coordinates;
- deterministic cardinality; no implicit first match / no `index` selector;
- staged album contract presents one media item and fails closed if selection
  becomes ambiguous;
- PRIVATE selection separates sheet-close confirmation from final summary wait;
- DRY_RUN and COMMIT routing remain separate;
- generic TikTok adapter exposes no final publish API.

## Freeze rule

`apps/tiktok/controller.py` and the DRY_RUN routing in
`publisher/publish_job.py` are frozen at this accepted behavior.

Core recovery/evidence/operations work may continue, but it must not modify the
accepted TikTok DRY_RUN business path unless the gate is explicitly reopened.
If a future change alters TikTok selectors, action ordering, staging
cardinality, visibility handling, or normal Android driver semantics used by
this path, the 20-run gate must be rerun before acceptance is restored.

## Not covered by this freeze

- COMMIT / final Publish execution;
- future TikTok UI redesigns;
- hard physical Mac-Off acceptance for the overall Android Automation Core;
- remaining generic Core failure-evidence / recovery acceptance work.
