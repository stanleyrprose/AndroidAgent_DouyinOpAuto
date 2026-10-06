# Cloud GPT Runbook — PRD v0.4

## Human contract

The user does only:

1. paste one Douyin share URL;
2. review preview when useful;
3. explicitly approve publication.

Everything else is orchestrated by Cloud GPT across Mac and Y700.

## 1. Submit on Mac

```bash
./scripts/pipeline.sh submit '<douyin-url>'
```

Expected terminal state:

```text
ANALYZED
```

If `DUPLICATE`, stop.
If `BLOCKED_LOGIN`, open Douzy login once and resume.
Do not fall back to unauthenticated direct scraping.

## 2. Review evidence

Read:

```text
runtime/jobs/<job>/analysis/analysis.json
runtime/jobs/<job>/analysis/transcript.zh.json
runtime/jobs/<job>/analysis/frames/contact-sheet.jpg
runtime/jobs/<job>/analysis/localization_request.json
```

Routing rules:

- meaningful Chinese speech -> speech/mixed candidate;
- weak/no speech -> inspect visual text;
- never turn music/noise hallucination into dialogue;
- `visual_only` may have no overlay cue.

## 3. Create localization.json

Cloud GPT writes evidence-grounded Burmese localization:

```json
{
  "content_type": "speech|visual_text|mixed|visual_only",
  "source_summary": "...",
  "title_my": "...",
  "caption_my": "...",
  "caption_basis": {
    "type": "speech|visual_text|mixed|visual_only",
    "reason": "why this caption fits the source evidence",
    "source_frames": [1.8, 4.6],
    "source_transcript": ["exact source-language transcript snippet"]
  },
  "visibility": "PUBLIC",
  "cues": [
    {"start": 0.2, "end": 5.1, "text_my": "..."}
  ]
}
```

Default visibility is PUBLIC.

`caption_basis` is mandatory for new localization artifacts. It stores concise
editorial provenance, not hidden reasoning: why the caption fits the video and
which observable frame timestamps and/or source transcript snippets support it.
`caption_basis.type` must match `content_type`; visual-only captions need frame
evidence, and speech captions need transcript evidence.

## 4. Render + export on Mac

```bash
./scripts/pipeline.sh localize <job> <localization.json>
./scripts/pipeline.sh render <job>
./scripts/pipeline.sh export <job>
```

Review `production/preview.jpg` when visual layout changed.

The capability URL lives only in:

```text
runtime/jobs/<job>/export/handoff.json
```

Do not print it unnecessarily.

## 5. Pull to Y700

Use the manifest URL from handoff.json:

```bash
python3 publisher/pull_job.py '<manifest-url>'
```

The Y700 job id equals the Mac job id.

## 6. Start asynchronous DRY_RUN

```bash
./scripts/publish-async.sh <job>
```

Poll:

```bash
./scripts/publish-status.sh <job>
```

Expected terminal status:

```text
DRY_RUN_PASS
```

Then mark Mac:

```bash
./scripts/pipeline.sh mark-dryrun <job> --y700-job-id <job>
```

## 7. Ask for approval

Do not commit automatically.

The explicit human approval must clearly refer to the current job/content.

On approval, record Mac state:

```bash
./scripts/pipeline.sh approve <job> --note 'explicit user approval'
```

## 8. COMMIT on Y700

Before COMMIT, use the single atomic Y700 entrypoint. It verifies the current job is `READY_TO_COMMIT`, confirms `PUBLIC`, refuses concurrent/already-armed retries, atomically changes manifest `publish_mode` from `DRY_RUN` to `COMMIT`, records one-attempt approval evidence, and then starts the publisher:

```bash
./scripts/approve-public-commit.sh <job> 'explicit user/standing workflow authorization'
```

Do not manually split the manifest transition from `publish-async.sh --commit`; the atomic wrapper exists specifically to prevent a false COMMIT that only reruns DRY_RUN.

Poll with `publish-status.sh`.

Never rerun COMMIT just because the remote tool call timed out.

If status is:

```text
AMBIGUOUS_COMMIT_NEEDS_RECONCILE
```

run:

```bash
python3 publisher/reconcile_private.py <job>
```

This verifies TikTok Profile first and never taps Publish.

## 9. Finalize Mac state

After Y700 reports verified PUBLISHED:

```bash
./scripts/pipeline.sh finalize <job> --verified --evidence 'profile_private_exact_caption'
```

## 10. Dedupe

Dedupe is enforced twice:

1. Mac by share-URL hash + aweme_id index.
2. Y700 before COMMIT by source_aweme_id scan of published history.

A historical v0.3 publication can be imported with:

```bash
./scripts/pipeline.sh register-published <aweme_id> <legacy_job_id> --source-url '<url>' --verified
```

## Recovery principle

Durable state is the truth source.

Do not infer success from one tool timeout.
Do not retry a COMMIT until publication absence is positively established.

## Telegram explicit intent routing

The dedicated Telegram profile no longer treats a bare Douyin link as an execution request.
Use exactly one of these prefixes:

```text
自动发布+<Douyin share text or URL>
自动发布：<Douyin share text or URL>
存到相册+<Douyin share text or URL>
存到相册：<Douyin share text or URL>
```

`自动发布+` follows the established full PUBLIC workflow and carries standing authorization for exactly one PUBLIC COMMIT attempt after mandatory DRY_RUN.

`存到相册+` follows the same Mac ingest / evidence / localization / render / export path, then stops after the Y700 album-only handoff:

```bash
bash mac/production-pipeline/scripts/store-to-y700-album.sh <job> Y700Agent
```

The album-only path stores the rendered video non-destructively at
`/sdcard/Movies/Y700Agent/<job>.mp4`, verifies it through MediaStore, saves the final `caption.my.txt` text into ZUI Notes via its exported `ACTION_SEND text/plain` receiver, updates the Mac job to `STORED_IN_ALBUM`, sends `ALBUM_STORED`, restores the original Y700 screen power state, and never launches TikTok or crosses a publish boundary.


## Resume a retry-safe Telegram job

Use the deterministic controller only:

```bash
bash mac/production-pipeline/scripts/start-resume-job.sh <job_id>
```

The starter is detached and idempotent by PID. The controller reads the job's write-once `workflow_intent`. `STORE_ALBUM` reuses existing Mac production artifacts and regenerates only an expired export capability before retrying Y700 album + Notes storage. `AUTO_PUBLISH` may repeat DRY_RUN but never blindly repeats COMMIT. Observed COMMIT/ambiguous/published state is handed to publication closure/reconciliation. Jobs without an intent marker are blocked rather than inferred from chat history.
