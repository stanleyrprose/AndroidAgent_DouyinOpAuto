# TikTok PUBLIC Publish Flow Migration Acceptance

Date: 2026-10-04  
Feature baseline: `1a0499063d1f6059c4099b1a57b53eb2840f00ca`  
Target: Lenovo Y700 / TikTok / Generic Android Automation Core

## Decision

**CODE + REAL PUBLIC DRY_RUN + APPROVAL GATE PASS; REAL PUBLIC COMMIT PENDING EXPLICIT CONTENT APPROVAL**

## Production behavior

The production workflow default visibility is now `PUBLIC`.

```text
Douyin -> Myanmar localization/render -> Mac capability export
-> Y700 pull/checksum/stage
-> Generic TikTok workflow
-> select 所有人
-> verify PUBLIC summary + caption + Publish-ready
-> DRY_RUN stops
-> explicit current-content approval
-> manifest COMMIT + explicit --commit
-> durable COMMITTING
-> exactly one EXTERNAL_IRREVERSIBLE Publish click
-> PUBLIC Profile verification
-> PUBLISHED / or AMBIGUOUS_COMMIT_NEEDS_RECONCILE
```

## Real-Y700 acceptance

### PUBLIC DRY_RUN

PASS.

- public manifest transport: HTTP 200;
- Y700 pull: READY;
- visibility: PUBLIC;
- Generic Android Core: PASS;
- TikTok visibility selection: `所有人`;
- final state: READY_TO_COMMIT;
- evidence screenshot persisted;
- published artifact: false;
- no final Publish click.

### Explicit COMMIT approval gate

PASS.

With a `publish_mode=COMMIT`, `visibility=PUBLIC` job but without `--commit`:

- process exit: non-zero;
- failure explicitly requires `--commit`;
- new TikTok UI workflows: 0;
- TikTok foreground: false;
- no irreversible Publish action executed.

### PUBLIC post reconciliation

Implementation is present and fail-closed.

- verification begins from Profile's selected `视频` tab;
- candidate tiles are derived from current semantic `ev2` nodes;
- success requires exact caption match;
- any non-empty known restricted-visibility label (`tv_label`) disqualifies the candidate;
- no Publish API is called by reconciliation;
- an actual positive PUBLIC-profile match remains pending until the first explicitly approved real PUBLIC COMMIT exists.

Historical PRIVATE reconciliation remains available only for historical already-published jobs.

## Safety invariants retained

- DRY_RUN never clicks Publish;
- COMMIT requires manifest `COMMIT` plus explicit `--commit`;
- `COMMITTING` is persisted before the irreversible click;
- exactly one final Publish click exists in the Generic Core contract;
- after entering COMMITTING, verification failure becomes `AMBIGUOUS_COMMIT_NEEDS_RECONCILE`;
- ambiguous COMMIT has `retry_allowed=false`;
- no blind automatic retry.

## Remaining hard gate

One specifically approved current content item must be published PUBLIC once, then verified by exact caption in the public Profile `视频` tab. This is intentionally not executed as part of this migration.
