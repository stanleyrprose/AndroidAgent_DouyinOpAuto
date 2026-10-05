# TG → TikTok Zero-touch E2E Acceptance — 2026-10-05

Status: **PASS / FROZEN BASELINE**

Frozen runtime/code baseline:

- commit: `0dc50cf`
- semantic release: `tg-tiktok-zero-touch-e2e-v1.0.0`
- freeze branch: `frozen/tg-tiktok-zero-touch-e2e-v1`
- Mac production runtime: pinned to `0dc50cf`
- Y700 canonical runtime: pinned to `0dc50cf`

## Scope

This acceptance freezes the first fully verified zero-touch Telegram-to-TikTok
workflow for `AndroidAgent_DouyinOpAuto`:

`Telegram Douyin URL -> Mac ingest/analysis/localization/render -> Y700 handoff -> TikTok DRY_RUN -> exactly-one PUBLIC COMMIT -> post-publish verification -> Mac VERIFIED -> Telegram terminal receipt`

The acceptance does not freeze unrelated future Android automation capabilities.
Future work may extend the system, but this business path must remain regression
protected.

## Acceptance job

Zero-touch acceptance job:

- job id: `dy-7692795483655254393`
- aweme id: `7692795483655254393`
- route: `visual_review`
- content type: `visual_only`
- visibility: `PUBLIC`
- video SHA-256: `1af09627de84405b8a438127c25087ae1371f0fa11c6fdc1b155adbc6dc621bf`

The job was initiated by sending a Douyin share link to the dedicated Telegram
control plane. No ChatGPT/manual command was required to carry the accepted run
from ingress through TikTok publication and terminal workflow completion.

## Acceptance evidence

### 1. Telegram ingress

PASS.

The dedicated `y700automation` Hermes gateway accepted the Douyin share message
and created one durable Mac job.

### 2. Mac production plane

PASS.

The accepted job reached durable Mac state `VERIFIED`.

Localization used schema v2 and contained `caption_basis`, including observable
frame evidence. For this visual-only job, `source_transcript` was empty and
`source_frames` contained sampled source timestamps.

### 3. Y700 handoff

PASS.

The Y700 job used the same job identity and media hash as the Mac production
artifact. Runtime truth was held outside Git under the Y700 durable media/state
roots.

### 4. TikTok DRY_RUN

PASS.

The reversible workflow validated the media, Burmese caption, PUBLIC visibility,
and publish-ready UI before crossing the irreversible boundary.

### 5. Exactly-one PUBLIC COMMIT

PASS.

Y700 durable publisher state records:

- `submission.accepted = true`
- confirmation: `generic_commit_dispatched`
- one recorded `commit_workflow_job_id`
- visibility: `PUBLIC`

The accepted architecture uses `scripts/approve-public-commit.sh` as the only
supported Telegram one-shot transition from `READY_TO_COMMIT` + `DRY_RUN` into
COMMIT. The wrapper owns preconditions, the atomic manifest transition,
one-attempt audit evidence, and publisher start.

### 6. Post-publish verification

PASS.

Y700 durable state reached `PUBLISHED` and the published job directory exists.
Verification succeeded with:

- `verified = true`
- method: `generic_profile_public_exact_caption`
- accepted candidate: current/public profile item

### 7. Mac finalization and Telegram terminal receipt

PASS.

Mac durable state reached `VERIFIED` with publication evidence
`generic_profile_public_exact_caption`.

The dedicated Telegram gateway emitted the terminal response after the accepted
run. The detached publication-closure path is regression-protected so future
ambiguous post-click states can reconcile and finalize without granting the
watcher any COMMIT capability.

## Frozen contracts

The following contracts are frozen for this baseline:

1. A bare valid Douyin URL on the dedicated Telegram control plane is standing
   authorization for exactly one PUBLIC COMMIT attempt after mandatory DRY_RUN,
   unless the same message narrows or revokes publication.
2. New localization artifacts use schema v2 and require `caption_basis` grounded
   in observable frame and/or transcript evidence.
3. Telegram publication crosses the irreversible boundary only through
   `scripts/approve-public-commit.sh`.
4. `publish-async.sh --commit` alone is not authorization and does not replace
   the atomic manifest transition.
5. Ambiguous COMMIT state never causes blind replay. Reconciliation happens
   before any possible retry.
6. The detached publication-closure watcher may poll, reconcile, finalize Mac
   state, and send Telegram terminal notifications, but it has no publication
   capability.
7. Runtime truth remains outside Git. Git freezes code/config/docs; Mac/Y700
   durable runtime state remains the operational SOT for individual jobs.

## Regression gate

The frozen path is guarded by tests covering at least:

- localization schema v2 / `caption_basis`;
- secure unlock/keyguard recovery;
- TikTok semantic DRY_RUN/COMMIT selectors;
- atomic PUBLIC COMMIT transition and retry refusal;
- Cloudflare/Y700 remote-plane self-heal semantics;
- detached publication closure with no publish capability.

A future change that intentionally alters a frozen contract must create a new
acceptance baseline rather than silently redefining this one.

## Change policy

`0dc50cf` is immutable. Do not amend, force-move, or repurpose the tag/freeze
branch. New work starts from a normal development branch. If the accepted path
changes materially, run a new zero-touch Telegram E2E acceptance and freeze a
new version (`v1.1.0`, `v2.0.0`, etc.) as appropriate.
