# Telegram Y700 Automation Control Plane v0.1

Date: 2026-10-04
Status: **IMPLEMENTED / LIVE TELEGRAM E2E PENDING DEDICATED SECRET**

## Decision

Telegram becomes a second ingress and notification surface for the established `douyin-tiktok-publish` workflow. It does not replace the Mac production plane, filesystem-first Y700 bridge, TikTok publisher, or GitHub SOT.

The implementation reuses the existing Hermes messaging gateway with an isolated profile named `y700automation`. No new message queue, custom bot daemon, database, scheduler, or second Android control stack is introduced.

## Architecture

```text
Telegram dedicated bot
  -> Hermes gateway (profile: y700automation)
  -> douyin-tiktok-publish Skill
  -> Mac authenticated Douyin ingest / evidence / Burmese render
  -> capability handoff
  -> Y700 pull + SHA-256
  -> TikTok PUBLIC DRY_RUN
  -> exactly one PUBLIC COMMIT attempt
  -> Profile verification / reconciliation
  -> Telegram status receipts
```

Cloud ChatGPT remains an equivalent manual ingress. Both paths use the same workflow contract and the same Git/runtime sources of truth.

## Original v0.1 Telegram intents — historical / superseded

The following list documents the original v0.1 behavior only. The current production contract is defined in **Current explicit trigger contract** below.

- bare valid Douyin share URL: run the end-to-end workflow;
- `/status [job_id]`: read durable state;
- `/cancel <job_id>`: cancel only retry-safe pre-COMMIT work;
- `/help`: show the bounded interface.

The bot is not a generic shell, ADB console, root console, account-management interface, or free-form assistant.

## Original v0.1 authorization — historical / superseded

For the original v0.1 canonical Skill, one supplied Douyin URL was explicit authorization for one durable job and exactly one TikTok `PUBLIC` COMMIT attempt after the mandatory DRY_RUN gate. Current production requires an explicit publish intent prefix as defined below.

No blind second COMMIT is allowed after timeout, UI uncertainty, disconnect, or ambiguous durable state.

The Telegram executor must use Y700 `scripts/approve-public-commit.sh` for the one-shot boundary. That entrypoint owns the READY_TO_COMMIT/PUBLIC checks, atomic `DRY_RUN -> COMMIT` manifest transition, one-attempt audit record, and publisher start; `publish-async.sh --commit` is not a substitute because it deliberately does not mutate the manifest.

## Notifications

For Telegram-originated jobs the orchestrator emits public-safe transition receipts:

- `RECEIVED`
- `PRODUCING`
- `TRANSFERRING`
- `READY_TO_PUBLISH`
- `DRY_RUN_PASS`
- `COMMITTING`
- `PUBLISHED_VERIFIED`
- `PUBLISHED_WITH_LIMITED_VERIFICATION`
- `RECONCILE_REQUIRED`
- `FAILED_SAFE`
- `DUPLICATE`

The notifier uses Hermes `send` directly. Delivery is best-effort by default and is deliberately outside publisher truth: a Telegram outage must not change job state or cause a publication retry.

After the one-shot COMMIT starts, Mac launches `start-publication-closure.sh`. The detached watcher polls durable Y700 state, starts reconciliation at most once when required, finalizes the Mac job on verified publication, and emits the terminal Telegram receipt. The watcher has no COMMIT/publish capability, so it can survive an LLM/gateway turn timeout without creating duplicate-publication risk.

## Security boundary

- dedicated Telegram bot token; do not reuse the general/default Hermes bot;
- allowlist the intended Telegram user/chat identity;
- token, allowlist ids, home channel/thread and session state stay in the profile's local `.env`, never Git;
- dedicated profile has only the workflow Skill plus the built-in Hermes agent Skill;
- Telegram toolsets are reduced to terminal/file/vision/skills/todo/clarify;
- unrelated browser/web/generation/memory/delegation/cron/computer-use surfaces are disabled;
- the SOUL policy rejects arbitrary shell/ADB/root requests from Telegram;
- no credentials, capability URLs or auth databases appear in status receipts.

## Mac runtime isolation

The Telegram executor should run against a clean GitHub-driven runtime checkout rather than the user's dirty development worktree. Deployment-local `runtime/env.local` remains Git-ignored.

`scripts/pipeline.sh` must change to its production root before importing `pipeline.cli`, so Hermes can invoke it from the repository root or a background gateway process.

## Acceptance

Completed without dedicated Telegram secret:

- isolated Hermes `y700automation` profile created;
- no bundled Skill set inherited;
- canonical `douyin-tiktok-publish` Skill synchronized and load smoke PASS;
- Telegram tool surface reduced;
- clean Mac runtime checkout created;
- Mac production bootstrap PASS;
- existing media-server health PASS;
- deterministic Telegram status formatter/sender covered by unit tests.

Pending live gate:

1. inject the dedicated bot token and allowed Telegram identity;
2. install/start the profile gateway;
3. send one real Douyin URL from the allowed account;
4. verify intermediate Telegram receipts;
5. complete one-shot PUBLIC publish or safe terminal failure/reconciliation;
6. verify no duplicate COMMIT and no secret/capability leakage.

The control plane is not production-complete until this live gate passes.

## Current explicit trigger contract (2026-10-07)

The original v0.1 bare-link trigger has been superseded for current production use. Historical acceptance records remain unchanged.

Current Telegram execution intents are:

```text
自动发布+<Douyin share text or URL>
自动发布：<Douyin share text or URL>
Automatic Publish+<Douyin share text or URL>
Automatic Publish：<Douyin share text or URL>
存到相册+<Douyin share text or URL>
存到相册：<Douyin share text or URL>
Save to Album+<Douyin share text or URL>
Save to Album：<Douyin share text or URL>
```

A bare Douyin URL no longer authorizes or starts work.

`自动发布` and `Automatic Publish` normalize to the same `AUTO_PUBLISH` intent. It runs the full Mac production -> Y700 -> TikTok PUBLIC path and authorizes exactly one PUBLIC COMMIT attempt after mandatory DRY_RUN.

`存到相册` and `Save to Album` normalize to the same `STORE_ALBUM` intent. It runs Mac production through export, pulls the capability artifact to Y700, stores the rendered video non-destructively under `Movies/Y700Agent`, verifies MediaStore visibility, saves the final Burmese caption into ZUI Notes for manual copy/publish, emits `ALBUM_STORED`, restores the initial power state, and stops. This path has no TikTok/COMMIT capability.

English aliases are ASCII case-insensitive. For payload-bearing intents, `+`, ASCII `:`, and Chinese `：` are equivalent separators. Fixed English phrases are intentionally narrow; arbitrary synonyms are not inferred.


## Durable resume control (2026-10-06)

Telegram supports:

```text
继续任务：<job_id>
继续任务:<job_id>
继续任务+<job_id>
Resume Task：<job_id>
Resume Task:<job_id>
Resume Task+<job_id>
任务状态：<job_id>
Task Status:<job_id>
取消任务：<job_id>
Cancel Task:<job_id>
帮助
Help
```

A canonical job must carry a write-once `workflow_intent` of `AUTO_PUBLISH` or `STORE_ALBUM`. Resume never accepts or infers a replacement intent. `STORE_ALBUM` resumes only from safe exported handoff state; an expired capability URL is regenerated from existing Mac render/caption artifacts without re-downloading or re-localizing. `AUTO_PUBLISH` may resume retry-safe pre-COMMIT stages, but any COMMIT manifest, COMMITTING, ambiguous, or published state is transferred to the existing publication closure/reconciliation controller. A COMMIT with uncertain outcome is never replayed.
