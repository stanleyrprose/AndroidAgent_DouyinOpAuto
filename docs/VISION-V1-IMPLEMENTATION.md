# Y700 Vision Locator — Sprint V1 Production Template Vision

Status: **candidate / Gate V1 pending real-Y700 acceptance**

Baseline: Gate V0 PASS.

## Runtime position

Vision is a selector backend inside the existing Generic Android Automation
Core. It is not a second workflow engine.

```text
workflow action
  -> semantic selector
       -> exactly one match: semantic action path
       -> zero/ambiguous:
            -> explicit vision_template fallback present?
                 -> no: preserve semantic failure
                 -> yes: routing policy
                      -> vision feature enabled?
                      -> action risk eligible?
                      -> template resolve
                      -> stale/rotation pre-action guard
                      -> shared UiDevice Action Executor
                      -> shared postcondition
```

## V1 routing policy

- semantic match always wins; Vision is not invoked;
- no implicit visual fallback is added to selectors;
- fallback must be explicitly declared as `vision_template`;
- production default remains `vision.enabled=false`;
- OCR / `vision_text` is rejected in V1;
- `EXTERNAL_IRREVERSIBLE` actions are blocked from Vision routing in V1;
- disabling Vision returns the original semantic failure/behavior without state
  migration or Bridge changes.

Example:

```json
{
  "vision": {
    "enabled": true,
    "mode": "fallback",
    "template_enabled": true,
    "evidence_max_bytes": 67108864
  },
  "actions": [{
    "action": "click",
    "selector": {
      "content_desc": "semantic-first",
      "fallback": [{
        "type": "vision_template",
        "template": "benchmark/target_idle.png",
        "template_sha256": "<sha256>",
        "template_version": "v1",
        "confidence": 0.90,
        "roi_ratio": [0.55, 0.37, 0.88, 0.56],
        "min_second_best_delta": 0.03,
        "click_policy": "EXACT"
      }]
    },
    "expect": {
      "selector": {"content_desc": "expected-state"},
      "unique": true
    }
  }]
}
```

## Template contract

- relative APK asset path only;
- SHA-256 required and verified before matching;
- optional version participates in cache identity;
- cache key: path + SHA-256 + version;
- same path with a changed hash/version invalidates the old cached bitmap;
- max cache: 16 entries / 24 MiB;
- normal template: `TM_CCOEFF_NORMED`;
- alpha template: `TM_CCORR_NORMED` with alpha mask;
- low-information and second-best ambiguity guards remain mandatory;
- deterministic scale generation reuses the Gate V0 implementation.

## Action safety

VisionTarget is bound to:

- captured frame dimensions;
- display rotation;
- normalized bbox/center;
- effective ROI fingerprint.

Before input injection, the driver captures again and verifies the same
rotation/geometry and ROI fingerprint. A mismatch yields
`VISION_ROTATION_MISMATCH` or `VISION_STALE_TARGET` and no click.

Click policy:

- EXACT by default;
- SAFE_JITTER only for low-risk, sufficiently large targets;
- target width/height < 48 px forces EXACT;
- V1 Vision never authorizes EXTERNAL_IRREVERSIBLE.

## Evidence and metrics

Normal success persists metadata only. Failure flows through the existing Core
Failure Evidence Contract and includes Vision context.

Vision evidence quota defaults to 64 MiB and is configurable from 8–512 MiB.
Only terminal, unpinned historical Vision evidence may be evicted. Active,
pinned, and RECONCILE_REQUIRED evidence is preserved, as are workflow/result/
state files and all Bridge durable state.

Metrics include request/success/failure/fallback/template/cache/stale/rotation/
capture/ambiguity/postcondition counters plus capture/template/total latency.

## Gate V1 runner

`tests/run_vision_v1_acceptance.py`

The real-Y700 runner verifies:

- semantic-first behavior;
- 20 repeated semantic-miss -> template fallback -> click -> postcondition;
- >=19/20 success;
- alpha-aware template;
- ambiguous duplicate target fails closed with no click;
- template SHA mismatch fails before click;
- postcondition failure emits Vision-aware evidence;
- EXTERNAL_IRREVERSIBLE Vision routing is blocked;
- `vision.enabled=false` restores semantic-only behavior;
- no absolute-coordinate primary workflow path.

Production TikTok/Settings selectors are not modified by Sprint V1.
