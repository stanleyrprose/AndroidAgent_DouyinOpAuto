# AAC Rev3.7 — Local development WIP (no tests / no Git remote operations)

Status: **IN DEVELOPMENT / NOT VALIDATED / NOT RELEASED**
Date: 2026-10-09
Branch: `feat/aac-rev37-sprint1a` (Mac development worktree)
Frozen input: `docs/PRD-Y700-AAC-v0.6-Rev3.7-Frozen.md`

## Workflow instruction (2026-10-09)

The user requested a **development-first batch**: make code changes locally
without running any tests, PR/CI operations, `git push`, or merges until
the *entire* frozen PRD development is finished. No CI, unit tests, build,
Instrumentation, device test, smoke test, PR changes, push, or merge are
authorized as part of the current unvalidated development batch.
Local file creation/editing and reading documentation/source are allowed.

**Scope supersession:** On 2026-10-09 the user explicitly authorized code development for **all frozen PRD Sprints**, superseding the former Sprint 1/1A-only *development scope*. This is NOT permission to deploy, activate BUSINESS publishing, perform irreversible effects, change production APKs, bypass safety guards, or merge untested source. All development stays local until the complete PRD is implemented and the separate final validation batch begins.

## Existing validated baseline before this batch

The previously established local branch baseline was `7dafa24`. At that
point PR #41 was a Draft, D-G3 OPEN, no production visual click authority.
Previous tests/CI related to that baseline must not be misrepresented as
validation of any new files in this WIP.

## New local source files (not executed, compiled or tested)

| Path | Intended frozen-PRD area | Current limit |
|---|---|---|
| `automation/authoritative_state_reader.py` | Sprint 1 / 1A State Integrity read-only host SOT observation | Does not establish a native Android Driver channel; never authorizes dispatch |
| `automation/overlay_window_policy.py` | §18.6 global blocking-overlay versioned classifier | No complete trusted Y700 window inventory available; policy result is READ_ONLY |
| `automation/read_only_jit_boundary.py` | §18.8 exact frame/locator/boot/revision JIT composition | Calibration remains disabled; no production dispatch adapter or action |
| `automation/capability_axes.py` | Sprint 2, §§5.17/10.8 capability/support/permission/readiness separation | Static, diagnostic-only; no execution/admission/approval |
| `automation/stage_health_v3.py` | §33 stage-oriented health view | Advisory on-demand formatter, not state or mutation authority |

## Second local development batch: additional unvalidated source

- `automation/capability_job_store.py` — durable admission, exact submission identity, request/policy hashes, fsync, deterministic backend binding, read-only status
- `automation/gateway_coordinator.py` — dormant foreground coordinator with immutable release switch CLOSED; preview/status and no automatic backend retry
- `automation/effect_boundary.py` — exact approval/content identity, persistent effect-boundary-first ordering, no second COMMIT
- `automation/subjob_provenance.py` — durable `SUBJOB_BOUND` journal, exact current `claim_id + owner_id`, no stale claim rebind
- `automation/backend_reconcile.py` — exact backend identity and liveness/uncertain-effect classification, no retry
- `automation/ttl_clock_guard.py` — BOOTTIME same-boot TTL, reboot/clock-suspect fail closed
- `automation/release_lifecycle.py` — immutable manifest checks, patch drift, quiescent atomic switch and bounded rollback code; source-level release gate CLOSED
- `automation/capability_catalog.py` + `config/capabilities.json` — strict static Catalog, all entries shipping disabled pending App/UI contract acceptance
- `automation/capctl.py` — read-only list/describe/doctor/status, all mutating commands blocked
- `automation/frozen_route_contracts.py` — versioned, caller-nonoverrideable local routes; visual dispatch remains blocked

**None of the files above has been executed, tested, compiled or deployed.**

## Third local development batch: PRD-aligned durable lifecycle and migration (UNTESTED)

The latest user grant covers **all PRD development**, but neither the source
gate nor the operational environment is authorized for release/activation.
This batch adds or revises the following candidates, **without executing
a single build, unit test, instrumentation, CI, PR or remote Git operation**.

- `automation/capability_job_store.py`: revised toward frozen §13
  `.staging -> active -> archive`, atomic fsync, immutable identity/policy,
  monotonic `state_revision`, `transition.lock`, result.json-only terminal
  authority, pre-submit never-created positive proof.
- `automation/capability_cancellation.py`: durable cancel intent under the
  same transition lock as effect-boundary; boundary-before-cancel means
  `CANCEL_AFTER_EFFECT_BOUNDARY`, never `CANCELLED`.
- `automation/effect_boundary.py`: approval consumption derived solely from
  the durable `effect-boundary.json`; precise approval and fingerprint
  evidence, boundary-first, `RUNNING_UNSAFE` lifecycle update.
- `automation/publisher_boundary_guard.py` + local change in
  `publisher/publish_job.py`: optional Gateway-bound exact
  pre-COMMITTING boundary check; Legacy migration remains separately gated.
- `automation/effective_policy.py`: deterministic minimum/effective policy
  resolution; caller cannot reduce replay, approval, verification or TTL.
- `automation/backend_reconcile.py` +
  `automation/explicit_reconcile.py`: exact known backend identity/status
  classification; explicit positive final proof only, no second external
  effect attempt.
- `automation/ttl_clock_guard.py`: same-boot CLOCK_BOOTTIME TTL with
  CLOCK_SUSPECT pre-submit block on reboot/uncertain clock.
- `automation/subjob_provenance.py`: durable `SUBJOB_BOUND` before
  subordinate execution, current Claim ID/owner exact binding.
- `automation/tiktok_gateway_adapter.py`: no second Publisher; exact
  existing publisher/backend/content/resource receipt.
- `automation/settings_golden_adapter.py`: inert versioned semantic
  change-and-restore plan based on previously accepted Settings locators.
- `automation/release_lifecycle.py`: gated atomic symlink switch and one
  conditional rollback path, no currently permitted production activation.
- `automation/frozen_route_contracts.py`: static locally-owned route
  contracts, no caller-provided visual dispatch authorization.
- `automation/capability_catalog.py`,
  `config/capabilities.json`, `automation/capctl.py`: 4-capability
  Catalog, all disabled pending app/runtime/protocol acceptance;
  discovery/status-only CLI.

### Incomplete implementation (not acceptance / not tested)

1. **Native Android Driver authoritative action-boundary integration**:
   App/Host cannot yet retrieve a trustworthy synchronized boot,
   epoch/revision, foreground Activity, overlay classification and exact
   screenshot/locator frame identity at dispatch. Android-only JIT fixture
   is not a production bridge. D-G3 remains CLOSED.
2. **Capability Job recovery/activation**: persisted admission and status
   exist in candidate code, but frontend policy identity, exact runtime
   adapters, crash recovery, pre-submit clock evidence, resource lifetime
   and terminal normalization need complete production wiring.
3. **Publisher migration**: Gateway-bound precommit verifier candidate is
   written, but Gateway <-> existing Publisher approval/claim callback is not
   activated. Legacy COMMIT remains protected by its previous boundary,
   not yet made Gateway-only. BUSINESS remains CLOSED.
4. **Upgrades**: release link switch implementation is written behind a
   constant FALSE gate; no candidate manifest/signature validation,
   live quiescence observer, approved patch rollout, or rollback tests yet.
5. **Settings**: a no-input Golden workflow plan exists, but no accepted
   end-to-end adapter integration/restore/reconciliation; do not change
   actual Settings.
6. **All Sprint exits**, Android/Settings/TikTok real-device acceptance,
   crash/clock/claim/effect fault injection, packaging, Git commit/push,
   PR/CI/review and Merge remain DEFERRED until **full code development**
   is finished, as instructed.

No further claims of completion should rely on pre-development CI PASS.

## Continued local development — 2026-10-09 evening (UNTESTED)

Source-only implementation changes made after the previous WIP update:

- `automation/capability_job_store.py`: a non-creating shared status
  `transition.lock`, strict immutable request/policy identity on crash
  recovery, initial `ttl-clock.json` sealed within staged admission,
  bounded monotonic deadline witness matched to initial request/policy,
  and existing no-follow durable record reads / full write loops retained.
- `automation/gateway_coordinator.py`: removed old wall-clock-based
  pre-submit recalculation, uses first-admission durable TTL witness on
  replay; checks static Catalog and exact effective minimum policy;
  requires a fresh trusted RuntimeAuthority observation after waiting
  for `android_ui`, confirms boot/time/policy hash/identity/readiness;
  rechecks the exact resource session immediately before submit.
  RuntimeAuthority still needs a concrete production source adapter.
- `automation/publisher_boundary_guard.py`: a second immutable
  source-level `_GATEWAY_COMMIT_ACTIVATION_ENABLED=False` gate prevents a
  Gateway-bound manifest from incidentally enabling PUBLIC COMMIT;
  Legacy migration remains separately gated.
- `mac/android-automation/app/src/androidTest/java/com/stanley/y700automation/AutomationInstrumentedTest.java`:
  recursively detects vision-bearing mutation fields nested in
  selector/fallback/expect; bounds traversal and rejects too-complex trees.
- `automation/effect_boundary.py`: checks single-use approval,
  immutable capability/job/content binding, approved_by provenance,
  approval nonce, and absolute approval expiry before the durable
  external-effect boundary. Input source must remain trusted.
- `mac/android-automation/app/src/androidTest/java/com/stanley/y700automation/vision/Rev37NativeStateObserver.java`:
  read-only candidate for boot/revision/foreground/window facts. Cannot
  authorize production dispatch; full trustworthy overlay semantics and
  acceptance/calibration are still missing.

**NO build, syntax check, unit test, Android instrumentation, real-device
test, PR, CI, remote push, merge or production deployment was performed.**
The fact that a source file was written is NOT a PASS.

### Next required source-development integrations

- Native Android Driver mutation boundary must own frame capture, exact
  locator provenance, fresh SOT/window/foreground state and selected
  route contract at dispatch. Remove any opportunity for caller-passed
  override; keep D-G3 CLOSED until calibration and acceptance.
- Implement a real trusted `RuntimeAuthority` bridge, policy refresh,
  pre-submit resource cleanup and durable post-submit backend observation.
- Finish source-level claim/approval fingerprint checks, Publisher
  migration lock ownership, status/reconcile-resource/cancel/gc CLI,
  durable effect verifier, release manifest/discovery lifecycle,
  and no-bypass legacy migration semantics.
- Only once implementation is completed, run the separately requested
  unit, crash-injection, Android Settings, TikTok DRY_RUN and release
  acceptance testing batch; then Git push, PR/CI and gated Merge.

## Fourth local development batch: exact claim recovery and safety hardening (UNTESTED)

User reiterated "继续" and retained the prior authorization for **all Rev3.7
PRD code implementation before any tests/compile/PR/CI/push/merge**. New
source was written **only in the Mac local worktree**, still based on the
last previously validated commit `7dafa24`.

**Added or strengthened (manual source work, not executed):**

- `automation/capability_job_store.py`: bounded complete writes;
  no-follow duplicate-key-rejecting single-inode JSON read; root-mode checks,
  staging-created transition.lock, strict active/archive terminal authority,
  and prohibition on CANCELLED/FAILED after durable effect boundary.
- `automation/capability_cancellation.py`: corrected the candidate
  CANCELLING state update syntax, preserving the shared transition lock.
- `automation/publisher_boundary_guard.py`: reads the exact
  `capability-jobs/active` path, checks protected file owner/mode and
  read consistency, rejects ambiguous duplicate JSON keys.
- `mac/android-automation/app/src/androidTest/java/com/stanley/y700automation/vision/Rev37NativeModalGuard.java`:
  native versioned route/modal watchlist; all selector sets remain
  **NOT_ACCEPTED**. No caller-provided `modal_clear=true` shortcut.
- `Rev37NativeStateObserver.java`: native modal dependency now a fixed
  route contract ID rather than a user-controlled boolean. It still
  depends on unvalidated root/UiAutomation observation and is not accepted.
- `apps/tiktok/controller.py`: added exact CAPABILITY Claim inheritance
  context; existing Legacy ui_lease continues to work; nested scopes
  reassert the current durable claim rather than acquire a second flock.
  **Not connected to a production Gateway-Publisher invocation yet.**
- `automation/gc_maintenance.py`: read-only terminal archive retention
  candidate selection; uncertain staging and active/Reconcile data are not
  GC candidates. GC apply constant stays CLOSED.
- `automation/capctl.py`: added frozen CLI argument shapes for
  invoke/cancel/reconcile/reconcile-resource/gc/admin force-reset; mutating
  commands remain blocked. GC exposes read-only preview only.
- `automation/resource_reconcile_v37.py`: exact resource-only and ADMIN
  maintenance candidate code; positive liveness/quiescence proof and
  canonical lock, durable epoch bump before emergency stop, no routine
  external effect retry; both release gates remain CLOSED.

**Important outstanding development dependencies:**

- Trusted Android Driver ↔ host SOT direct dispatch-time protocol,
  independently collected foreground Activity, global overlay and
  in-app modal policies accepted against the real TikTok version, and
  monotonic action-age route calibration are NOT complete.
- Coordinator/Backend/Publisher resource-guard inheritance end-to-end
  is NOT fully connected; existing `before_irreversible` uses the
  candidate guard but BUSINESS migration remains inactive.
- Root authorization/approval identity and requested-content immutability
  verification, immutable release manifest identity and upgrade quiescence
  authority, terminal/race recovery and full CLI adapter activations
  remain under development.
- Nothing new from this batch has been built, linted, compiled, tested,
  executed on Y700, deployed, committed, pushed, placed into CI,
  updated in Draft PR #41, or merged.
- Incomplete security-critical components **MUST NOT** be activated as
  a quick workaround, even if a positive unit/instrumentation test is
  obtained in the eventual final acceptance batch.

## Fifth local development batch: adapter routing and native dispatch precondition (UNTESTED)

- `automation/gateway_adapters.py`: static four-Adapter function map;
  immutable payload/Backend intent validation, no plugin framework,
  resources, additional backend IDs, or model-chosen route relaxation.
- `automation/gateway_coordinator.py`: compile-time-dormant route to
  static prepared adapter intent before backend submission; repeated
  `submission_id` returns only durable existing identity/status rather
  than implicitly continuing a backend.
- `automation/resource_reconcile_v37.py`: ADMIN reset now observes the
  existing owner-protected SOT before calling epoch bump; cannot treat a
  missing/corrupted state file as authorization to bootstrap.
- `mac/android-automation/app/src/androidTest/java/com/stanley/y700automation/vision/Rev37NativeMutationBoundary.java`:
  independent Java mutation-time candidate frame/SOT comparison. It cannot
  authorize a click because modal contract, route max-age calibration and
  native production dispatch have not been accepted; `DG3_ACCEPTED=false`.
- `automation/effect_boundary.py`: adds a separate static closed release
  gate for entering the irreversible boundary, independent of Gateway and
  Publisher gates.

**Code-only checkpoint:** local Mac changes were inspected for file paths
(not compiled or executed). All new files remain uncommitted/unpushed in the
Mac worktree. The last validated baseline is still `7dafa24`; previous CI
status and earlier real-device receipts do not validate these additions.

**Before declaring the full PRD development complete:** finish trusted
Gateway-to-existing Publisher callback/witness integration; guarantee
per-capability resource ownership and no nested reacquisition throughout
all mutating UI subjobs; finish app-versioned modal/window contracts,
independent reusable locator templates, accepted route age source and
native Driver input dispatch integration. Also finish stable release
metadata/upgrade observers, positive terminal/reconcile proofs, frozen
Settings Golden workflow, all CLI maintenance pathways and exact backend
fault-state recovery. Only *after* the full code reaches a reviewable state
will the user-authorized test/build/device/PR/CI/merge batch begin.

## Sixth local development batch: Gateway/Publisher single-claim integration (UNTESTED)

User again authorized complete PRD **code development only**, with absolutely
NO builds, tests, Y700 runs, PR/CI, push or merge until all code is finished.

### Authored local source (not compiled or run)

1. `publisher/gateway_execution.py` — new **scoped entrypoint for the
   existing Publisher**, not an alternate publishing engine. Existing
   controller `prepare_dry_run`, `commit_public`, profile verifier, media
   staging, status and archive helpers are reused. Capability-bound jobs
   must inherit the Gateway's exact canonical Claim; Legacy auto-wake and
   second resource acquire are prohibited. Unlocked screen must be
   positively observed; otherwise blocked. Gate FALSE.
2. `publisher/publish_job.py` — capability-bound COMMIT is routed to that
   guarded entrypoint **before** the Legacy `ensure_device_unlocked`
   branch. Direct CLI invocation has no trusted runtime context and
   therefore cannot bypass Gateway.
3. `automation/tiktok_gateway_adapter.py` — write-once
   `gateway-binding.json` ties cap job, exact deterministic backend,
   Publisher's pre-existing ID, video and caption hashes, and Claim to a
   root-controlled durable record. Required request payload and Publisher
   manifest content must agree; no new Publisher created.
4. `automation/publisher_backend_adapter.py` — exact publisher Backend
   implementation: read-only exact status from protected Backend execution
   receipt, dedicated `prepare_exact` provenance then prospective
   synchronous submit through existing Publisher. Binding requires a
   separately supplied **trusted authority**; no always-true authorization.
   Backend submit gate FALSE.
5. `automation/capability_job_store.py` — fsynced
   `backend-execution.json` lifecycle: NEVER_CREATED → SUBMISSION_POSSIBLE
   (durable **before** backend call) → SUBMITTED_ACKNOWLEDGED. Crash after
   SUBMISSION_POSSIBLE can never return a second positive never-created
   witness. Correlated `BACKEND_SUBMITTING` and exact state progression.
6. `automation/canonical_ui_resource.py` — one canonical Android UI
   lease held by foreground coordinator; inherited through nested
   Controller/UiCore without nested flock acquisition. Safe release
   requires exact current claim and positive quiescence; uncertain backend
   conservatively retains durable claim.
7. `automation/gateway_coordinator.py` — `prepare_exact` before durable
   SUBMISSION_POSSIBLE, Backend submit afterward, and final
   `finish_exact` clean/retain path. Frozen DRY_RUN/COMMIT immutable
   mode distinction; external TikTok COMMIT has a separate FALSE gate.
8. `publisher/job_contract.py` — durable Publisher status transition
   now fsyncs file, atomically replaces it, and fsyncs parent directory;
   especially required for COMMITTING before the one external Publish.
9. `automation/publisher_boundary_guard.py` — verifies actual video
   **and caption** bytes against both pinned Publisher manifest hashes and
   immutable Gateway binding before COMMITTING. Gate remains FALSE.
10. `automation/effect_boundary.py` — re-reads canonical Claim and
    authoritative SOT **under transition.lock** and requires explicitly
    accepted, immutable TikTok App UI Contract. Upper effect boundary
    remains the single authority for single-use approval consumption.
11. `automation/settings_golden_adapter.py` — prospective end-to-end
    existing UI Core v2 change/restore adapter with precise subjob
    provenance and initial-mode durable receipt. No direct click, no
    automatic stale-state retry. Execution gate FALSE.

### Pending whole-PRD code-completion blockers

- **D-G3/native Driver**: independent accepted locator templates,
  app-version-pinned overlay selectors and signing/version facts, trusted
  foreground Activity, calibrated frame age, native last-mile click
  envelope and full dispatch-time boot/epoch/revision/geometry guard.
- **Runtime authority**: production binding of authenticated local caller,
  dynamic support/permission/readiness, fresh post-wait facts and exact
  app-version signature to Gateway and Native Android. These cannot be
  simulated by booleans from request JSON.
- **Approval/Publisher business state**: trusted one-URL authorization →
  immutable request/approval → exact native precommit receipt → effect
  boundary → Publisher COMMITTING → one click → verified result →
  terminalization and safe resource reconciliation. New connector code
  exists but is still dormant and not end-to-end accepted.
- **Capability adapters/CLI**: finish read-only observation and root
  command adapters, exact Settings backend dispatch and cancellation,
  reconcile-resource/GC/ADMIN positive-proof transitions, lifecycle
  orchestration and real operational diagnostics.
- **Release lifecycle**: immutable release manifest and signature
  generation/check, positive quiescence/upgrade observer, bounded rollback
  integration and staged rollout; no production switch authorized.
- **Whole PRD exit gates**: all final builds, tests, fault injection,
  Android real-device/UI acceptance, review, Git push, PR/CI and Merge
  remain explicitly deferred until code development itself is complete.

**Code Complete = NO. D-G3 = OPEN. BUSINESS COMMIT = CLOSED.** Earlier CI
passes do not constitute validation of the present uncommitted local code.

## Seventh local development batch: full-scope backend and code-completion gaps (UNTESTED)

Authorization for this batch remains **code development only**. Do not run
unit/instrumentation/UI tests, compilations, packaging, device deployment,
commit/push, PR/CI or Merge until full code implementation is finished.

### Newly authored or connected code

- `automation/local_fixed_backends.py`: foreground-only static registration
  of all **four** frozen Catalog capabilities, each with exact deterministic
  backend identity, durable status, prepare/submit interface, and separate
  release-closed execution gates. No plugin loader or generic scheduler.
  `android.root.exec` uses the existing `bridge/root-exec.sh` with a
  literal fixed allowlisted command, epoch bump before UNKNOWN state effect,
  and no request-controlled shell. `android.device.observe` reads root SOT
  and never acquires android_ui.
- `automation/capability_job_store.py`: deterministic
  `--observe-01` backend identity added; existing
  `SUBMISSION_POSSIBLE` pre-call witness remains the non-replay boundary.
- `automation/capability_axes.py`: added ADMIN/root capability and made
  Catalog advertisement an explicit trusted input, preventing falsely
  permanent `CAPABILITY_CATALOG_DRIFT` after accepted activation.
- `automation/release_integrity.py`: root-owned pinned public key,
  offline detached signature over full candidate file hash inventory,
  same-inode/no-follow reads, exact source inventory equality, and
  arbitrary symlink/unlisted-source refusal; read-only and no installer.
- `automation/release_lifecycle.py`: switch function re-verifies
  candidate offline signature + complete file digests at actual
  pre-switch boundary; `_RELEASE_SWITCH_ACCEPTED=False` remains.
- `automation/release_quiescence.py`: conservative read-only pre-upgrade
  inventory for claim, active jobs, unsafe effects and candidate files.
  Missing independently accepted native-mutator, admission-stop and offline
  gate facts force BLOCKED. It cannot synthesize a passing proof.
- `automation/trusted_ingress_approval.py`: root-owned one-URL explicit
  authorization bound to deterministic submission/job ID, request/policy
  hashes, Douyin URL, video/caption hashes, source principal, nonce and
  expiry. Added both **pre-admission** and **post-admission** verification.
  No grant is created from caller fields. Reader rejects duplicate JSON
  keys, symlinks and a changed root-owned record.
- `automation/effect_boundary.py`: approval creation reopens the exact
  protected trusted ingress witness and compares all pinned fields rather
  than accepting caller-provided `approved=true` alone. The boundary
  remains separately gated.
- `automation/gateway_coordinator.py`: future BUSINESS COMMIT preflight
  uses the above **pre-admission** authority; retains post-resource fresh
  state and expiry checks, with production Gateway and COMMIT gates closed.
- `automation/gateway_adapters.py`: COMMIT requires pinned source Douyin
  URL and hashes; static adapter cannot silently change intended content.
- `mac/android-automation/app/src/androidTest/java/com/stanley/y700automation/AutomationInstrumentedTest.java`:
  original interactive v2 Driver visual-mutation branch invokes
  `Rev37NativeMutationBoundary.compareAtNativeBoundary` before any
  executeWithRetry/click, emits read-only native JIT refusal receipt and
  still reports zero attempts, D-G3 CLOSED. This is the ORIGINAL Driver,
  not a second Android input framework.

### Source-only closure matrix (NOT final acceptance)

| PRD workstream | Source state | Missing for actual Code Complete |
|---|---|---|
| Sprint 0 / baseline | Prior tooling and evidence retained | Remaining frozen inventory/acceptance harness review; no runs this batch |
| Sprint 1 / ownership and SOT | Existing Core/arbiter + candidate Gateway resource | Final actor/claim lifecycle integration, clock/owner fault logic |
| Sprint 1A / visual route | Original driver branch calls native refusal JIT | Independently minted FrameToken/locator, approved icon/template, accepted modal signatures, calibrated age, native dispatch proof |
| Sprint 2 / Catalog/Policy/Job | Four static entries, effective policy, durable admission | Trusted control-plane/runtime observer closure, stronger phase/contract invariants |
| Sprint 3 / coordinator | Fixed backends, one Claim, exact submit witness | Complete Backend proof sources, crash/reconcile and release of subordinate claims |
| Sprint 4 / effect/approval | Trusted one-URL source, approval binding, unsafe journal | Native precommit proof → effect callback → Publisher COMMITTING → terminalization wiring |
| Sprint 5 / Settings | Candidate reversible generic Core v2 adapter | Versioned settings contract, restart/restore runtime evidence, final code review |
| Sprint 6 / TikTok | Existing Publisher reused through scoped Gateway adapter | Accepted current TikTok UI contract, one-click dispatch, Profile reconcile/effect outcome convergence |
| Cross-cutting release | Signed candidate tree, atomic switch, rollback candidate | Independent quiescence/admission fence, source signing artifact, restart recovery/safe upgrade supervision |

**Important:** Much of the candidate source is newly authored and may
contain unresolved integration/compile defects. No static inspection is
a replacement for final tests, and no prior CI result validates this
uncommitted development batch. `Code Complete = NO`, `D-G3=OPEN`,
`BUSINESS COMMIT=CLOSED`, `RELEASE SWITCH=CLOSED`.

## Eighth local development batch: terminal-outcome convergence (UNTESTED)

**Source work only.** The user's explicit instruction still prohibits all
tests, compilation, Y700 deployment, Git push, PR, CI or Merge until
full PRD code development is finished.

- `automation/capability_job_store.py`: positive `VERIFIED` now demands
  a **capability-specific durable verifier**. TikTok consumes exact
  Publisher `publish-result.json` (PUBLISHED/PUBLIC/Profile verified,
  matching Capability and Backend ID); Settings consumes
  `settings-restore-result.json` (initial = restored); observation and
  root use exact source-owned receipts. `OUTCOME_NOT_ACHIEVED` requires
  separate positively proved negative evidence, never mere Profile
  absence. Pre-submit CANCELLED/EXPIRED additionally require actual
  `backend-execution.json` to remain `NEVER_CREATED`.
- `automation/local_fixed_backends.py`: observation/root synchronous
  backends durably write exact verifier receipts before returning a
  positive Backend ACK. An uncertain exception remains reconcile-only.
- `automation/gateway_coordinator.py`: synchronous accepted backend
  response is NOT automatically `VERIFIED`. Only an exact positive
  typed verifier + durable receipt permits `finalize_terminal()`.
  Android UI resource release remains orthogonal to BUSINESS outcome.
- `automation/trusted_ingress_approval.py` + `automation/effect_boundary.py`:
  post-admission single-use PUBLIC approval is re-read from the same
  protected root-owned ingress record and matched against all immutable
  identifiers before any approval is written. No new identity provider
  is invented, and request fields cannot authorize themselves.
- `automation/capability_axes.py`: support advertisement can follow
  the exact reviewed static Catalog enabling state without hiding
  `CAPABILITY_CATALOG_DRIFT` before activation.

### Remaining source-level Code Complete blockers

1. Complete native screenshot-origin FrameToken *issuance* and matching
   independent UI template/locator provenance; current native JIT call
   is read-only **and rejects every visual mutation**.
2. Pin/test-versioned TikTok app signing certificate, modal inventory,
   foreground Activity and JIT route age; these must not be guessed.
3. Wire authenticated first-party transport/clock/runtime probe into
   `TrustedInvocation` and exact `RuntimeAuthority.observe_fresh`;
   existing root-owned ingress evidence reader is necessary but not a
   complete live runtime authorization adapter.
4. Finalize safe startup/admission fence, upgrade quiescence observation,
   offline signed release artifact production and crash-resume handling.
5. Review/close strict state schemas, unfinished Reconcile/GC/admin
   mutation operations, remaining Settings abnormal restore cases and
   remaining PRD Sprint 0 baseline harness work.

At this checkpoint: `CODE_COMPLETE = NO`; `D-G3 = OPEN`;
`PRODUCTION_GATEWAY = CLOSED`; `BUSINESS_COMMIT = CLOSED`;
`RELEASE_SWITCH = CLOSED`. No tests or builds run in this batch.

## Ninth local source batch: root-owned fresh runtime authority (UNTESTED)

User asked whether coding was ongoing. Reopened the Mac development worktree
on branch `feat/aac-rev37-sprint1a` without touching Git or the Y700.
Authored `automation/runtime_authority.py`: bounded no-follow root-only
`capability-authority/cap-<id>.json` reader, exact capability/backend/request/
effective-policy identity, boot/epoch/revision double SOT observation,
monotonic <=750ms evidence age, strict typed support/permission/readiness
facts, clock-health fail-closed and no diagnostics leaking raw identifiers.
Its independently trusted evidence producer is **NOT ACCEPTED**; source
constant `_EVIDENCE_PRODUCER_ACCEPTED=False` prevents use in production.

Wired `ForegroundCoordinator` to a fixed `LocalRootRuntimeAuthority`
rather than caller-injected RuntimeAuthority booleans. Missing, stale,
malformed or mismatched evidence remains a blocked outcome. This closes
part of the coordinator's *source-level consumer interface*, but does
not build the separate accepted evidence producer or establish a reliable
source for pre-admission identity facts.

**Not code complete:** the authenticated producer/control plane, native
dispatch FrameToken issuer, versioned TikTok UI modal/template facts,
crash-reconcile recovery, release/admission fence and full exit conditions
remain missing. `CODE_COMPLETE=NO`; `D-G3=OPEN`; all BUSINESS/release
gates stay closed. No compile/test/commit/push/PR/CI/merge/device action.

## Tenth Mac-only development batch: Native provenance, runtime producer, foreground wiring (UNTESTED)

**User directive:** Continue Rev3.7 development until PRD Code Complete;
do not compile, run ANY test, install/deploy, push, create PR, run CI, or
merge before development has finished. This batch remained within Mac
local source edits, with all independent production activation gates FALSE.

### New code connected this batch

- `mac/android-automation/app/src/androidTest/java/com/stanley/y700automation/vision/Rev37NativeFrameRegistry.java`:
  screenshot-origin ephemeral in-process one-use FrameToken. Real
  `VisionV0Harness.Frame` generation/fingerprint/boottime and independently
  observed Android state identify the frame; matching locator must originate
  from that exact native frame. Caller JSON cannot self-mint one-time
  provenance. Template acceptance remains false and no external pixels
  are persisted. Exact payload fields checked explicitly (not JSONObject
  `similar()`). D-G3 still CLOSED.
- `Rev37NativeMutationBoundary.java`: consumes exact registered native
  frame/locator evidence before any read-only native JIT comparison;
  unknown provenance returns `FRAME_NATIVE_PROVENANCE_UNAVAILABLE`.
  Still never dispatches a click.
- `Rev37NativeAppContract.java`: queries Android PackageManager for
  actual installed TikTok versionCode and APK contents signing certificate
  SHA-256; unsigned/multisigner/unknown package or mismatch blocks. The
  genuine accepted version+certificate pair remains UNSET, so the
  observer strictly returns `APP_UI_CONTRACT_NOT_ACCEPTED`.
- `Rev37NativeStateObserver.java`: reads the independent native App UI
  Contract before modal/window/SOT checks, no package-name-only trust.
- `AutomationInstrumentedTest.java`: adds `observeNativeFrame` as a
  read-only action using UiAutomation capture from a static full-display
  ROI, no caller coordinates or screenshot export. It cannot mint an
  accepted action target before frozen contracts are installed.
- `automation/recovery_inventory.py`: no-input crash/startup reader of
  active/staging directories and exact Backend durable witness, no
  automatic re-submit, resource reset or staging cleanup.
- `automation/capctl.py`: source-wires read-only `startup-status` and
  `reconcile JOB --dry-run` to exact original Job/Backend evidence.
  Mutating reconcile still gated.
- `automation/pre_admission_authority.py`: privileged nofollow,
  root-protected immutable request+policy evidence verification,
  pre-admission boot/epoch/revision and typed identity/runtime facts.
  Missing accepted producer/clock -> blocked, never trust invocation JSON.
- `automation/runtime_evidence_producer.py`: potential root foreground
  evidence publisher for pre-admission and after-resource-wait samples;
  requires separately recorded first-party Principal, root-owned
  trusted-clock receipt, immutable policy and actual local SOT/arbiter
  inventory. All independent writer/source acceptance gates FALSE; no
  fabricated Principal or clock validity.
- `automation/gateway_coordinator.py`: source-wires fixed pre-admission
  authority and post-wait privileged evidence refresh, eliminating
  acceptance of workflow-origin identity/runtime booleans as gate truth.
- `automation/foreground_entrypoint.py`: one static four-Capability
  foreground entrypoint; uses existing Catalog, existing Publisher,
  existing UI resource arbiter, and durable Backend Coordinator. Fully
  release-gated; no new daemon, queue, background CI or second Publisher.
- `automation/resource_arbiter.py`: original canonical durable UI Claim
  SOT read hardened to no-follow, root-owned 0600, bounded single-inode
  consistent data and duplicate-key rejection. Corruption means
  UNAVAILABLE/RECONCILE, never an available Claim.
- `automation/offline_release_builder.py`: proposed Mac-offline full-tree
  digest and detached signature production. No key is copied to Y700;
  signing is a separate release-gated explicit operation and has NOT run.

### Precise remaining Code Complete gaps / acceptance prerequisites

1. Native TikTok version-specific **accepted** app fingerprint and source
   template image, accepted overlay/modal signatures, calibrated JIT
   maximum frame age, and live native click adapter. These facts cannot be
   safely invented or inferred from an earlier read-only fixture.
2. Real first-party authenticated Principal publisher and healthy clock
   sensor receipt provenance need integration with the Y700 runtime. The
   consumer/foreground producer code paths now exist but have not been
   exercised or authorized.
3. Explicit resource-only positive-proof cleanup, cancellation, durable
   per-Backend outcome reconciliation and safe lifecycle release deserve
   a full integration review. An ambiguous Publish remains reconcile-only.
4. Release admission-fence/native mutator-quiescence observation, source
   integrity signing issuance, PATCH_SAFE upgrade and rollback remain
   source-gated and must not be claimed accepted.
5. Full test and build acceptance, fault injection, live Y700 App UI
   version/Template receipts, signoff and migration cannot occur until
   user permits final validation phase after Code Complete.

**Code Complete is NOT yet proven.** No development-code test/build was
executed; D-G3, BUSINESS COMMIT, final release switch and all source
activation flags remain CLOSED. This is an honest implementation inventory,
not a release readiness statement.

## Eleventh Mac-only development batch: end-to-end source integration (UNTESTED)

**Exact user boundary:** Continue Rev3.7 Frozen PRD source development
until Code Complete. During development run **NO builds, compilation,
tests, USB/Y700 deployment, commit, Git push, PR, CI or Merge**. This
batch consists only of Mac local source edits and read-only repository
inspection. All production acceptance switches remain FALSE.

### New or corrected implementation paths

1. **TikTok single approval authority:**
   `automation/gateway_coordinator.py` now resolves existing root-owned
   one-URL ingress evidence and durably records one exact COMMIT approval
   before Publisher `prepare_exact`; source `_BUSINESS_EFFECTS_ENABLED`
   and independent effect gates remain OFF.
2. **Publisher actual binding and callback:**
   `automation/publisher_backend_adapter.py` verifies durable Claim,
   request/policy hashes, recorded approval, and **fresh** trusted
   runtime facts. `automation/publisher_effect_authority.py` builds the
   *internal* exact precommit callback tied to original
   Capability/Backend/Claim/approval and a separately trusted native
   receipt. `publisher/gateway_execution.py` requires this callback
   only for COMMIT, not DRY_RUN. There is still NO accepted native
   effect-receipt producer; all irreversible actions stay CLOSED.
3. **Resource-only reconcile ≠ BUSINESS outcome:**
   `automation/resource_reconcile_v37.py` no longer ties UI Claim release
   to resolved business effect; positive STOPPED proof is still required
   from actual kernel/Backend/subordinate evidence.
   `automation/resource_stop_observer.py` uses exact boot/PID/proc-start
   ticks (ZOMBIE, DEAD, PID_REUSED acceptable; stopped T/t unsafe).
   Caller-boolean proof no longer suffices. Native positive-stop issuer
   is still not accepted.
4. **ADMIN emergency path:** new `automation/admin_stop_adapter.py`
   uses pidfd identity-bound signals (no unsafe bare PID kill fallback),
   only after root-owned one-shot ADMIN receipt, exact Claim and durable
   epoch bump. ADMIN replay/effect stays forbidden. Wired to
   `capctl admin force-reset-ui-runtime`; activation flag FALSE.
5. **Exact Capability reconciliation:** new
   `automation/capability_reconcile_runtime.py` can inspect the original
   Publisher's durable Profile verification and source-gated
   `finalize_terminal` without replaying Publisher. Connected
   `capctl reconcile`; unknown results remain RECONCILE_REQUIRED.
6. **Shared admission fence:** new `automation/admission_fence.py`
   holds the SAME durable submission admission flock as
   `CapabilityStore.admit`; existing immutable binding replay/status
   remains read-only, but new admissions stop during source-gated release
   quiescence. Safe removal requires reviewed lifecycle state.
7. **Release quiescence:** `automation/release_quiescence.py` now derives
   real candidate signing/admission-fence/native-mutator/offline gate
   facts from protected sources, not passed booleans.
   `automation/release_lifecycle.py` reobserves them immediately
   pre-switch. Sources and release switch remain gated.
8. **Native Create route:** new `Rev37NativeTemplateRoute.java`
   supplies fixed packaged asset SHA256, native screenshot identity and
   OpenCV `VisionV0Harness.matchTemplate`. Reuses the existing
   `VisionTemplateLocator` bootstrap; native template/Modal/App-version
   evidence remains unaccepted and asset hash deliberately UNSET.
   `Rev37NativePostcondition.java` defines version-specific positive
   Create-screen marker checks, also not accepted yet.
9. **Original Android Driver:** conditional same-stack native
   single-click branch in `AutomationInstrumentedTest.java` consumes
   *only* independently matched in-process bounds and JIT proof, attempts
   no retries and records RECONCILE_REQUIRED on any exception after
   click entry. It reuses Core v2 for durable MUTATION_PREPARED/COMMITTED,
   retains an independent `REV37_NATIVE_CREATE_CLICK_ACCEPTED=false`
   switch. New read-only `observeNativeLocator` path never exports
   coordinates. Host `automation/ui_job.py` recognizes the read-only
   native observation actions.
10. **Settings Golden:** uses actual foreground `observe` result and
    full fresh navigation during restore rather than a hardcoded assumed
    Settings foreground or old page position. Exact Claim/subjob
    protocol v2 retained, execution gate FALSE.
11. **GC:** `automation/gc_maintenance.py` has a conservative
    source-gated terminal auxiliary cleanup path that preserves
    result/identity/request/policy/Backend submission SOT, archive and
    submission index. Full archive/index tombstone GC still requires
    a reviewed crash-safe identity/retention protocol and cannot be
    claimed complete.
12. **Runtime age:** `runtime_evidence_producer.py` distinguishes an
    exact healthy in-flight self Backend from OTHER unresolved jobs.
    Publisher binding and effect boundary refresh privileged evidence
    again (pre-wait facts are not reusable as effect authorization).
    Source gates remain closed.

### Code Complete status and blocking objective facts

**NOT CODE COMPLETE**: source-level implementation and acceptance
prerequisites remain incomplete. Specifically: independent TikTok
template asset, SHA256, PackageManager version+signer, modal/overlay
selector contract, JIT max frame-age calibration, accepted native
commit-receipt issuer, independent trusted Principal/clock/native-stop
producers, full bounded archive/index GC, and reviewed
release/rollback/quiescence operation. The first-party receipts cannot
be fabricated by boolean flags or by this WIP record. Final static
review/compile/tests/device/fault injection have NOT occurred.

`D-G3=OPEN`; `BUSINESS_COMMIT=CLOSED`;
`PRODUCTION_GATEWAY=CLOSED`; `RELEASE_SWITCH=CLOSED`.
Source edits are uncommitted/unpushed; prior PR/CI statuses are NOT
evidence for any current WIP changes.

## Twelfth Mac-only integration closure: normal/admin recovery, GC, quiescence (UNTESTED)

Only Mac local source edits; this batch **did not run tests, compile, deploy,
stage/commit, push, create PR, run CI, or merge**.

- `automation/capability_reconcile_runtime.py`: source-gated normal
  `capctl reconcile` resolves only exact pre-existing Publisher Profile
  receipt/Backend ID, then calls terminal archive after independent
  `CapabilityStore.finalize_terminal` verification. Unknown and
  non-publisher outcomes remain RECONCILE_REQUIRED; no second Publish.
- `automation/resource_stop_observer.py`: new live-foreground
  `positive_synchronous_ui_quiescence`, requiring the accepted native
  Android/Bridge all-subordinate-terminal receipt under current exact
  Claim and boot/epoch. Gated FALSE until independent real observation.
- `automation/canonical_ui_resource.py`: safe Release now splits
  **durably NEVER_CREATED pre-submit** (can release without a UI session)
  from **SUBMISSION_POSSIBLE or later** (requires positive native
  mutator-stop proof). No release from mere Backend ACK or absent
  `active_ui_job_id`.
- `automation/resource_reconcile_v37.py`: root-owned exact Admin
  force-reset authorization receipt tied to Claim, Backend, reason SHA256,
  boot, short expiry and original principal, rather than a CLI
  `trusted_admin_authenticated=true` boolean. Exact proof reobtained
  under canonical flock. Release gate remains FALSE.
- `automation/admin_stop_adapter.py`: best-effort exact Linux owner
  SIGTERM now uses kernel `pidfd_open` and `pidfd_send_signal` to
  eliminate raw PID reuse race; never sends signals on unsupported kernel.
  Never equates signal sent with a positive stopped UI state. Integrated
  with `capctl admin force-reset-ui-runtime`, source gate CLOSED.
- `automation/gc_maintenance.py`: conservative source-gated foreground
  `gc --apply` implementation prunes ONLY proven aged terminal archive
  `.terminal-tmp` files. It retains all authoritative archive results,
  submission indexes, journal, immutable job identity and Backend effect
  evidence. Broader archive/index deletion requires a crash-safe
  tombstone/retention protocol and is NOT claimed complete.
- `automation/runtime_evidence_producer.py`: exact current in-flight
  healthy Backend is no longer misclassified as OTHER unresolved work;
  any actual `effect_uncertain`/mutation uncertain or separate unresolved
  job remains BLOCKED.
- `automation/publisher_backend_adapter.py` and
  `automation/publisher_effect_authority.py`: reissue source-owned fresh
  post-wait runtime facts at binding and immediately before the external
  effect boundary, instead of reusing expired earlier evidence.
- `VisionTemplateLocator.java` and `Rev37NativeTemplateRoute.java`:
  reuse original existing OpenCV initialization instead of reimplementing
  native bootstrap.
- `automation/ui_job.py`: recognizes read-only native frame/locator
  actions in its observation whitelist; mutation rules still unchanged.

**Static code/acceptance closure is NOT achieved.** Missing: real TikTok
template/version/signature/overlays, approved empirical frame age, trusted
native effect and UI-stop receipt producers, real root-owned Principal/clock
source acceptance, full GC tombstone lifecycle, release/source-signature
final integration and complete frozen Sprint 0-6 exit implementation.
Even source-level integrated paths have not been compiled or checked
against real Y700. Do NOT flip `DG3_ACCEPTED`, BUSINESS, Gateway, ADMIN
or release flags based on this WIP note.

## Current local checkpoint: admission fence / release authority (UNTESTED)

- Verified by **source inspection only** that `CapabilityStore.admit()` acquires
  the same `.admission.lock` as `admission_fence.py`, permits immutable
  submission-ID lookups during upgrade freeze, and denies new admissions
  before completing incomplete-index recovery or creating any staging job.
- Removed an early `proof.complete()` caller-boolean dependency in
  `release_lifecycle.switch_release_after_acceptance()`; the release path
  re-reads root-owned candidate signature, admission fence, active jobs,
  native mutator absence and offline-gate evidence itself before symlink
  mutation. A separate source constant still prevents actual activation.
- All code changes remain local and unvalidated. There was no compilation,
  test execution, Commit, Push, PR, CI, Merge, or Y700 deployment.
- Remaining Code Complete tasks include accepted native JIT/FrameToken and
  TikTok App UI facts, authenticated Principal/clock evidence producers,
  exact positive resource Reconcile, and release health/rollback contracts.

## Eleventh local source checkpoint: admission/release boundary (UNTESTED)

The user asked whether development was continuing; the Mac workspace was
reopened and existing local edits confirmed. Resumed source work at the
admission/release race. Under the **same** `.admission.lock`, a matching
immutable existing submission may be read-only replayed during a release
fence, but an index-missing/new admission cannot proceed if the fence is
present. The upgrade quiescence check separately requires a durable held
fence and independently observed absence of active capability jobs.

Hardened `automation/release_lifecycle.py::_read_limited` to use bounded
root-owned no-follow fd reading, strict duplicate-key rejection and
single-inode before/after consistency validation. This applies to both
release manifests and authoritative release-state metadata. It never
creates, switches or repairs a release.

**NO compilation, lint/test, CI, PR, commit, push, Merge, or Y700 action was
performed.** All source activation gates are still closed. Code Complete
and PRD exit acceptance remain **NOT ACHIEVED**; remaining gaps are recorded
below. This checkpoint is not a tested result.

## Eleventh Mac-only development batch: business effect wiring, resource and release consistency (UNTESTED)

User confirmed continue Rev3.7 development until Code Complete. This
batch changes **local source only**, without compilation, tests, Git
commit/push, PR, CI, merge, or Y700 deployment.

- `automation/gateway_coordinator.py`: newly admitted TikTok COMMIT
  records the original protected one-URL approval before Publisher
  preparation. Re-read and compare again immediately before effect.
- `automation/publisher_backend_adapter.py`: exact Publisher binding
  authority now derives from the protected claim, original request,
  policy and durable approval; a caller-injected `True` cannot grant it.
  The irreversible-effect callback is built in-process from the exact
  Backend identity and is not request-supplied.
- `automation/publisher_effect_authority.py`: fixed-source proof
  collector for the unique Publisher `before_irreversible` boundary,
  comparing SOT boot/epoch/revision, exact claim, single-use approval,
  video/caption SHA-256, app UI version and accepted native evidence.
  The independent native issuer/dispatch gate remains CLOSED.
- `publisher/gateway_execution.py`: DRY_RUN no longer incorrectly
  requires a COMMIT-only callback; COMMIT continues to require it.
- `automation/resource_reconcile_v37.py` and
  `automation/resource_stop_observer.py`: BUSINESS result uncertainty
  is separate from proven UI quiescence. The normal resource-only
  reconcile source path uses original Backend, kernel PID/start-ticks and
  accepted native descendant-stop proof under the canonical resource
  flock. Stale native stop receipts now fail closed.
- `automation/capctl.py`: source command wiring for exact
  `reconcile-resource --dry-run` and subsequent gated normal
  release, never BUSINESS terminalization or effect retry.
- `automation/admission_fence.py`:
  durable named release fence uses the SAME admission lock.
  Ordinary read-only transport replay remains visible while brand-new
  admission and partial admission-index recovery are refused.
- `automation/capability_job_store.py`:
  checks the admission fence only on the new-admission path after
  existing immutable replay-index lookup, preventing release race.
- `automation/release_quiescence.py` and
  `automation/release_lifecycle.py`:
  release switch rechecks actual source-owned admission fence,
  active jobs, UI claim, native quiescence, offline acceptance and
  candidate signature at the switch boundary. Unreadable/unknown
  native receipts are rejected; request booleans cannot mint proof.
- `automation/release_integrity.py`: Mac signer/verifier file-count and
  catalog-size contracts now match; root-level release files besides
  `release-manifest.json` are valid only as normalized, non-traversing
  signed paths. The whole candidate inventory must still match.
- `automation/admission_fence.py`: absent/corrupt lock or state now
  reports a blocked read-only evidence result instead of escaping as a
  misleading healthy readiness result.

**Still NOT Code Complete:** independent trustworthy physical native
visual contracts + calibrated frame freshness, accepted clock/Principal
producer, full release supervisor crash-window recovery, and all PRD
source/witness integration exit criteria remain incomplete or unverified.
No source-acceptance flags have been flipped. `D-G3=OPEN`,
`BUSINESS_COMMIT=CLOSED`, `RELEASE_SWITCH=CLOSED`.

## Admission fence / Backend submit linearization follow-up (UNTESTED)

In response to continued Code Complete development on 2026-10-10:

- `CapabilityStore.admit()` retains read-only exact submission replay
  even when an upgrade fence is active, but new admission or recovery
  of an unindexed job must check the fence inside the exclusive
  `.admission.lock`.
- `CapabilityStore.begin_backend_submission()` now holds the **shared
  canonical admission lock** and the exact job transition lock through
  fence recheck and fsynced `SUBMISSION_POSSIBLE` update. Installation
  of the upgrade fence holds that same lock exclusively, preventing an
  already-admitted WAITING_RESOURCE job from starting its backend after
  an apparently quiet release snapshot.
- `ForegroundCoordinator.preview_invocation()` now maps
  `RuntimeEvidenceUnavailable` to a fail-closed source reason, rather
  than an unclassified thrown exception.
- Pure static edits only; no test/compile/device commands, staging,
  commit, push, PR, CI, Merge, or production activation.

**Still NOT Code Complete:** independently authenticated clock/principal
producer, accepted TikTok signing/version/modal/template facts, native
mutation dispatch acceptance, no-retry crash recovery and complete
release/source-signature/rollback path. Keep D-G3, BUSINESS, release
and admin gates CLOSED.

## Eleventh Mac-only development batch: admission fence replay and fail-closed missing-file semantics (UNTESTED)

- Preserved the frozen submit-index replay rule: with the common admission
  flock held, a fully persisted existing submission can resolve read-only
  during release admission freeze. New admissions and crash-window index
  creation are blocked by the SAME root-owned release fence.
- Hardened `automation/admission_fence.py` to distinguish actual ENOENT
  from an unreadable/untrusted root, symlink, nonregular or corrupt fence.
  Any ambiguous filesystem error blocks admission; fence does not expire
  automatically after reboot. This addresses a fail-open risk of checking
  only `Path.exists()`.
- Inspected current `CapabilityStore.admit`, fence observer, pre-switch
  signature/quiescence boundary without running any source/test process.
- **Outstanding**: code-complete is still NOT established. Final native
  app acceptance, actual principal/clock and native quiescence producers,
  full durable crash/reconcile/rollback integration and real UI acceptance
  still require work. D-G3 / BUSINESS / release switches remain CLOSED.

This batch involved Mac local source edits only. **No compile, tests, Y700
deployment, git commit/push, PR, CI or merge.**

## Latest Mac-only source batch: admission concurrency and typed recovery (UNTESTED)

User again requested uninterrupted Rev3.7 PRD development. This batch
was source editing / read-only source review **only**; no tests, builds,
Git commit/push, PR/CI, merge or Y700 deployment.

- Verified source-level common admission flock semantics:
  transport replays return only original read-only identity/status during
  release fence, but new admission and first Backend submission both check
  the SAME durable admission fence under canonical flock.
- `automation/capability_reconcile_runtime.py` now observes typed positive
  durable verifier receipts for ALL four fixed backends: original TikTok
  Publisher Profile, Settings initial=restored, read-only SOT observation,
  root-owned fixed maintenance command. Absence, corruption or mismatch
  remains `RECONCILE_REQUIRED`; it never replays input, silently allocates
  another backend, or considers absence of Publisher evidence proof of
  negative outcome. Explicit mutation reconcile gate remains FALSE.
- `automation/release_quiescence.py` now also refuses upgrade when
  `capability-jobs/.staging` contains unresolved/incomplete admissions,
  even when `active/` happens to be empty. All accepted independent
  native/CI evidence gates remain FALSE.
- `automation/capability_job_store.py` prevents malformed/symlinked
  `result.json` from being silently read as a nonterminal `state.json`,
  and refuses symlinked active job path.
- The job-store terminal recovery logic already records
  `SUBMISSION_POSSIBLE` as potentially executed even if state.json
  still says `backend_submitted=false`, so a crash after an actual
  backend action cannot safely be mistaken for NEVER_CREATED.

**Code Complete NOT YET claimed.** Outstanding source closure includes
the native end-to-end mutation/action envelope, accepted TikTok UI
version/cert/template/modal identities, authenticated Principal+clock
producer provenance, resource lifecycle and explicit cleanup activation,
Settings abnormal restore recovery, review of remaining release/rollback
and CLI schema invariants. Separately permitted end-stage acceptance,
builds, tests, Y700 real UI runs, Git push/PR/CI/merge remain deferred.

## Mac-only code integration batch: typed recovery, upgrade staging, cancel source (UNTESTED)

This round followed the user's explicit **Code Complete development-only**
directive. No compile, tests, real device execution, deployment, Git commit,
Git push, PR, CI or Merge were run.

- `automation/capability_reconcile_runtime.py`: the original exact-Backend
  positive-verifier lookup now handles all four fixed capabilities:
  TikTok Profile receipt, Settings Golden restored mode, read-only device
  SOT observation and fixed root command completion. Missing, unbound or
  forged receipts remain RECONCILE_REQUIRED; there is NO external replay,
  substitute Backend, forced UI stop or negative-outcome inference.
- `automation/capability_job_store.py`: detects malformed/symlinked
  terminal `result.json` and disallows symlinked active job paths.
  Confirmed existing implementation treats durable
  `SUBMISSION_POSSIBLE` as an ambiguous real Backend submission even
  when state.json has not yet received a Backend ACK, permitting only
  exact independently verified terminal reconciliation.
- `automation/release_quiescence.py`: an unresolved `.staging` admission
  now blocks positive upgrade quiescence even when active/ is empty.
  Admission/new Backend first-submission use the same canonical fence
  lock; read-only exact transport replay remains possible.
- `automation/capability_cancellation.py` + `automation/capctl.py`:
  CLI cancel path requires a separately accepted root-owned first-party
  authorization record binding original Job/request, principal, boot,
  epoch and monotonic freshness. Source gate remains FALSE; recording
  cancel intent does not imply terminal CANCELLED or stop external work.

Remaining code-complete blockers are significant: accepted Native Driver
action envelope is not yet a production APK path; version-pinned
TikTok signature/modal/template/calibrated age are not established;
trusted Principal/clock producer is still unaccepted; cross-process
release quiescence/rollback and abnormal Settings/PUBLISH effect recovery
are still gated. Final code and device acceptance have NOT occurred.

**Code Complete=NO; D-G3=OPEN; BUSINESS COMMIT=CLOSED; release and
maintenance mutation gates=CLOSED.**

## Latest local Code Complete integration pass (2026-10-10; UNTESTED)

User authorized continued source-only development until Rev3.7 Code Complete.
This batch used Mac CodexPro **read/edit only**; no compile, static checker,
test, Y700 deployment, Git commit/push, PR, CI, merge or effectful device
command occurred.

**Confirmed and fixed from frozen-route static source inspection:**

1. `automation/capability_job_store.py`: preserve ordinary read-only
   submission-id replay during a release admission fence, but block
   **new** admission after replay lookup. `begin_backend_submission` uses
   the *same* admission shared flock and rechecks the fence before
   durably recording `SUBMISSION_POSSIBLE`. Existing partial-index
   recovery remains blocked while fenced.
2. `automation/resource_arbiter.py`: durable claim corruption/audit
   failures in context manager cleanup can no longer skip the outer
   kernel flock/file-descriptor cleanup. Corrupt Claim remains for
   explicit reconcile; never silently marks resource free.
3. `automation/capability_job_store.py`: terminalizer now uses exact
   `backend-execution.json` `SUBMISSION_POSSIBLE` witness, not just
   `state.backend_submitted`, to distinguish an ACK-loss crash from
   genuinely `NEVER_CREATED`. Positive VERIFIED requires exact durable
   per-capability result even after submission ACK loss. Post-submit
   FAILED requires separate positive no-effect/stopped Backend proof;
   CANCELLED/EXPIRED cannot close an attempted external effect.
4. `automation/capability_job_store.py`: active job transition.lock
   cannot be silently created in a production transition; staged
   admission remains the sole lock-inode minting boundary.
5. `automation/capability_reconcile_runtime.py`: explicit exact
   same-Backend positive-terminal proof now includes Settings restore,
   observation SOT receipt and root allowed-command exit receipt in
   addition to TikTok Publisher Profile verification. No external retry,
   new backend or side-effecting reconciliation.
6. `scripts/publish-preflight.sh` and `publisher/gateway_execution.py`:
   **actual legacy preflight script originally called androidctl wake and
   unlock**, including from Gateway. New `--gateway-readonly` branch
   performs disk/temperature preflight but NO wake/unlock. Legacy
   default invocation remains compatible; accepted Gateway reuses the
   existing script via the safe explicit mode.
7. `publisher/stage_job.py` and `publisher/gateway_execution.py`:
   **actual legacy MediaStore staging originally ran `find
   Movies/Y700Agent -delete`**, including from Gateway. New
   `--gateway-bound` branch requires same canonical exact CAPABILITY Claim,
   frozen existing Publisher binding, media SHA-256 source and post-copy
   hash, no-clobber per-job temporary rename, and post-MediaStore claim
   recheck. It NEVER clears other videos. Legacy entry retained pending
   separate migration. Android shell flags are untested on Y700.
8. `automation/ui_job.py`: protocol-v2 Capability-owned
   `EXTERNAL_IRREVERSIBLE` now source-gated at the host boundary before
   any instrumentation session. For each mutating driver command, the
   foreground Host independently re-reads current root-owned Claim and
   overwrites the internal `rev37_capability_bound` provenance field;
   request JSON cannot override it.
9. `AutomationInstrumentedTest.java`: the existing interactive-v2
   **Android Driver** now separately denies Capability-owned irreversible
   external effects with zero UI attempts *before the fast semantic
   click branch*. This fixes a real route bypass: prior visual fallback
   restrictions could be avoided by a unique semantic selector. Legacy
   verified host-minted owner marker keeps the existing migration path
   distinct. Native independent Publish acceptance remains CLOSED.

**Remaining before true Code Complete:**
- Native accepted TikTok Publish action envelope and complete semantic
  state/foreground/modal/postcondition native pre-dispatch authority.
  Current hard block is correct; without this new external effect adapter,
  whole-PRD Code Complete cannot be claimed.
- Real signed/versioned TikTok App UI contract, supported video-stage
  shell operations on physical Y700, accepted selector/overlay templates,
  measured frame age and real-vs-fixture comparison receipt.
- First-party authenticated Principal and trustworthy clock receipt
  producers; pinned release signing, native mutator-stop/quiescence proof,
  admission-fence safe resume, Settings adverse restore and crossprocess
  fault recovery wiring.
- Final source review/compile/static tests/unit/instrumentation/real Y700
  acceptance/PR/CI/merge are explicitly **deferred** per user.
- All independent release constants remain FALSE. No successful test,
  running Gateway or production deployment is claimed.

**State: CODE_COMPLETE=NO; D-G3=OPEN; BUSINESS_COMMIT=CLOSED;
RELEASE_SWITCH=CLOSED.** Worktree changes are uncommitted locally.

## Local source follow-up: exact native owner and CLI integration (UNTESTED)

This pass remains under the user's instruction **complete all Rev3.7 PRD
source development before testing or Git remote operations**. No build,
test, APK, deployment, staging, commit, push, PR, CI or merge was run.

**Additional source changes:**
- `automation/ui_job.py`: for EVERY interactive v2 mutation command,
  reassert current host root-owned exact `android_ui` Claim and overwrite
  internal `rev37_capability_bound` + `rev37_claim_id` fields. Request
  JSON cannot demote CAPABILITY to LEGACY. Additionally reject a
  Capability-owned EXTERNAL_IRREVERSIBLE request while the native Publish
  effect dispatcher is not accepted.
- `Rev37NativeResourceOwner.java`: new fixed-path, bounded, no-input,
  Android-native independent read of the same root-owned Linux Claim SOT.
  Verifies Claim ID and owner kind; unknown/unreadable/su failure fails
  closed. It never issues permission or starts an external operation.
- `AutomationInstrumentedTest.java`: original interactive-v2 Driver
  blocks externally irreversible input if no exact native matching
  Legacy Claim, and repeats the exact native Claim lookup immediately
  before a semantic `target.click()`. This fixes the prior dangerous
  semantic-fast-path bypass, not only the vision-fallback branch.
  A future approved CAPABILITY Publish requires its OWN separately
  accepted native one-shot effect envelope; Legacy migration is not
  silently activated or disabled.
- `automation/capctl.py`: connects dormant `invoke` to the existing
  single in-process Foreground Gateway using a restricted root-owned
  `trusted-capability-requests/*.json` first-party request file; invokes
  no caller-provided tool path. Connects `cancel` to the existing
  protected ingress-and-shared-lock cancellation state machine. Both
  remain independently release-gated in their real runtime components.
- `scripts/disk-guard.sh` inspected: it only reads `df` and prints a
  disk status, and has no file deletion/wake/unlock behavior. Gateway
  `--gateway-readonly` preflight remains safe at this script layer.

**Open source-level gaps:** capability-scoped accepted NATIVE TikTok
Publish dispatcher (not just rejection), accepted package/UI signatures,
modal selectors and image template/route calibration, real trusted
clock/Principal evidence producers, native mutator stop receipts and
signed PATCH_SAFE quiescence/rollback edge handling. Those facts cannot
be invented while Y700 real-device tests are disallowed. Existing gates
remain FALSE; code complete CANNOT yet be asserted.

## Mac source batch — exact Native TikTok Publish, stage health and DRY_RUN bypass (UNTESTED)

User's source-only authorization applies unchanged. This batch made only
connected Mac source changes: NO compile, test, APK build, Y700 run/deploy,
Git staging, commit, push, PR, CI or merge.

**New Native Capability Publish action-time path (still source CLOSED):**

- `Rev37NativePublishBoundary.java`: a separately gated native, read-only
  irreversible Publish dispatch witness tied to the same existing
  `android_ui` Claim (CAPABILITY owner, exact cap/backend id), durable
  `effect-boundary.json`, stored `approval.json`, the immutable
  `request.json`, original Publisher `COMMITTING` record, current
  root SOT boot/epoch/revision, Android foreground Activity, windows,
  native modal guard and versioned TikTok package/signing contract.
  The accepted boundary-age calibration is **unset (-1)** and the
  native Publish gate is FALSE; it cannot authorize any input until real
  device evidence is reviewed. All paths reuse the existing Android
  instrumentation driver and existing Publisher, not a second engine.
- `Rev37NativeResourceOwner.java`: exposes fixed root-owned Claim
  observation to its same-package Native Publish observer; no mutation.
- `Rev37NativeAppContract.java` / `Rev37NativeModalGuard.java`:
  add frozen-route identity for `tiktok.publish-control.v1`, still NOT
  ACCEPTED because TikTok version/certificate/modal signatures are not
  measured/frozen.
- `automation/effect_boundary.py`: the single durable boundary now
  includes independently observed kernel boot, epoch and monotonic
  crossed-boottime for native dispatch JIT comparisons; no new mutable
  approval-used store.
- `AutomationInstrumentedTest.java`: native Capability Publish
  candidate is gated at the original interactive-v2 command entrance
  and re-checked directly before its one semantic `target.click()`.
  No production action is reachable because native acceptance, App UI
  contract, modal and compiled D-G3 release gates remain FALSE.
  Critical: `executeWithRetry` forces `maxRetry=0` for
  `EXTERNAL_IRREVERSIBLE` regardless of malicious `retry_safe=true`.
- `apps/tiktok/controller.py`: `build_commit_actions` and
  `commit_public` accept an optional trusted Gateway-only
  `capability_bound` flag to attach the frozen Publish route ID to the
  sole irreversible action. The Legacy default action schema is unchanged.
  `publisher/gateway_execution.py` supplies the route only in the
  Gateway-scoped existing Publisher invocation.

**Operational diagnostics and route safety:**

- `automation/node_health_v2.py`: new on-demand read-only Health v2 with
  independent stage inventory: connectivity, observation, frame,
  freshness, localization, permission, dispatch, postcondition,
  verification. Missing independently accepted source receipts remain
  UNKNOWN; alive != ready and health never grants execution.
- `automation/capctl.py`: `doctor` uses the Health v2 snapshot rather
  than claiming ready from a static Catalog; persistence stays separately
  release-gated.
- `publisher/publish_job.py`: recognizes `gateway-binding.json` for
  BOTH COMMIT and DRY_RUN **before** Legacy unlock/preflight. Previously
  a bound DRY_RUN executed via old CLI could fall back to Legacy and
  wake/unlock/acquire another owner. Gateway-bound direct CLI is
  blocked without authenticated foreground context.

**Still needs full Code Complete review:**

- Native durable receipt file mode/identity robustness, exact
  Action-time Publisher receipt and UI caption postcondition checks,
  independent real-device App UI version/signature, native modal/blocker
  signatures, real JIT boundary latency calibration and acceptance.
- Static exit gates for D-G1 through D-G5, full cross-layer request/claim
  fault-injection harness, signed release activation/rollback sequencing,
  and full first-party trusted clock/Principal deployment.
- The entire uncommitted development worktree has NOT been compiled or
  exercised. Source integration is not verified by older CI receipts.
  **CODE_COMPLETE=NO; D-G3=OPEN; BUSINESS_COMMIT=CLOSED;
  RELEASE_SWITCH=CLOSED.**

## Latest local development batch: cancel / resource / admission linearization (UNTESTED)

The user reiterated to continue Rev3.7 PRD code development, keeping all
tests/builds/devices/Git commit/push/PR/CI/Merge deferred. **Only Mac
source edits and source reads were performed** in this batch.

### Completed source changes

- `automation/capability_cancellation.py`: added
  `finalize_pre_submit_cancel_from_durable_proof`, a source-owned
  CANCELLED terminalization path requiring exact durable cancellation,
  Job/Backend identity, `backend-execution.json == NEVER_CREATED`, no
  prior possible submission, no effect boundary, no uncertain mutation,
  and no canonical android_ui Claim owned by that capability. A trusted
  one-job cancel ingress can attempt this safe terminalization; otherwise
  it stays `CANCELLING` and reports explicit reconciliation required.
- `classify_cancel_completion` no longer accepts user/caller-provided
  positive-stop booleans. Its read-only candidate verdict uses the
  actual exact durable Job/Backend/Claim records, not input flags.
- `automation/capability_job_store.py`: permits safe pre-backend-bound
  `CANCELLING -> result.json(CANCELLED)` only with a matching durable
  `cancel.json`; the existing post-submit and effect-boundary
  prohibitions remain intact.
- `automation/canonical_ui_resource.py`: eliminated cancellation vs
  delayed-Claim-acquire race. After obtaining canonical android_ui flock,
  it checks active Job's immutable identity, Backend, state, cancel,
  terminal marker and effect boundary again under `transition.lock`.
  If cancellation/archive won during the resource wait, it releases
  only its just-created Claim before any Backend invocation. The
  subsequent `begin_backend_submission` independently checks the same
  cancel/effect predicates after the shared upgrade admission fence.

### Distinct remaining Code Complete blockers

- Code has NOT been compiled or run. Static source inspection is not an
  acceptance outcome; all completion/compatibility claims remain pending.
- Native real TikTok app signature/version, independent template,
  overlay/modal signatures, on-device calibrated JIT maximum frame age,
  native action-time effect receipt and accepted last-mile input proof
  require genuine evidence, not invented constants.
- Authenticated first-party Principal and clock witness issuers, native
  subordinate stop proof and release quiescence producers still require
  accepted integration with the portable Y700 environment.
- Need whole-PRD cross-layer source review of any remaining
  CLI/reconcile/Settings/upgrade state flows before declaring code
  complete; final tests/CI/deploy remain explicitly deferred.

**CODE_COMPLETE=NO; D-G3=OPEN; BUSINESS_COMMIT=CLOSED;
RELEASE_SWITCH=CLOSED. No test, compile, commit, push, PR, CI, merge or
Y700 action was performed.**

## Local development batch: strict archive recovery and measured runtime support (UNTESTED)

User continued to authorize complete Rev3.7 code development but explicitly
deferred **all compilation, tests, Y700 deployment, Git Commit/Push,
PR/CI and Merge** until development Code Complete. This batch is Mac-only.

**Actual source changes:**

- `automation/terminal_archive_recovery.py`: separated durable terminal
  `result.json` truth from physical archive move. If result fsynced and
  active→archive rename crashed, explicit source-gated recovery checks
  exact request/policy/result identities under the **same transition.lock**,
  then performs only the idempotent archive rename and parent fsync. No
  Backend allocation, input, effect replay, or outcome reclassification.
- `automation/capability_reconcile_runtime.py`: distinguishes
  `TERMINAL_ARCHIVE_PENDING_READ_ONLY` from unresolved Backend, and wires
  the explicit archive-completion path behind independent source gate.
  Existing terminal outcome remains authoritative before directory move.
- `automation/runtime_evidence_producer.py`: replaced the former
  hardcoded support/readiness `True` with an independent, root-owned,
  bounded, versioned per-capability Y700 Device+Bridge probe. It must agree
  on boot/epoch/revision, actual device contract, exact static Catalog
  runtime probe ID, required dependency measurements, and (for TikTok)
  accepted app version/signing certificate/UI contract. Unknown evidence
  fails closed. The separate physical probe producer is **NOT ACCEPTED**
  so production readiness is not claimed.
- `mac/android-automation/app/src/androidTest/java/com/stanley/y700automation/vision/Rev37NativeFrameRegistry.java`:
  closing a pixel Frame invalidates its single-use in-process FrameToken;
  recycled screenshot evidence cannot be reused at mutation boundary.
- `automation/capctl.py`: removed a duplicate CANCEL dispatch branch;
  the source-gated explicit reconcile and resource-only repair remain
  separately classified.

**Engineering conclusion:** code paths are further integrated but
`PRD CODE COMPLETE = NOT YET CLAIMED` (no compilation/static import check,
no independent full-PRD coverage review, no real Y700 accepted TikTok app
contract/locator/overlay age, no accepted runtime probe publisher, no
native mutator quiescence/upgrade fence acceptance). The only defensible
runtime status remains: `D-G3 OPEN`, `BUSINESS COMMIT CLOSED`, and
`RELEASE SWITCH CLOSED`. Previously passing tests and CI are baseline
results only; they DO NOT validate these uncommitted Mac edits.

## Current local development batch: admission, Publisher crash windows, Reconcile (UNTESTED)

Explicit user instruction remains **continue toward complete PRD code**,
but **no build, test, Y700 deployment, Commit, Push, PR, CI or Merge** during
the implementation phase. These are source edits, NOT acceptance evidence.

### Source-level integration work completed this batch

1. `automation/capability_job_store.py` admission and first backend-submit
   boundaries were reviewed against the shared release `.admission.lock`.
   Existing exact submission bindings are still observable as read-only
   replays under a release freeze, while *new admission* and a previously
   admitted Job's *first possible backend submission* are serialized
   against the same release-fence lock. Job state, results and transition
   locks require owner+mode checks; fixed Y700 SOT paths require root
   ownership; isolated Mac temporary roots remain fixture-compatible.
2. `automation/capability_reconcile_runtime.py`: removed duplicate
   non-Publisher verifier branches; introduced exact publisher COMMIT
   `PUBLISHER_ARCHIVE_PENDING` classification for a positively verified
   publish-result durable in `ready/` but not yet renamed to `published/`.
   DRY_RUN now has its own durable POST_CONFIG/caption/visibility/cleanup
   positive-verifier route and never masquerades as a public Profile post.
3. `publisher/gateway_execution.py`: Profile-verified BUSINESS COMMIT
   writes and fsyncs the exact `publish-result.json` (job, backend, request,
   video/caption hashes and Profile evidence) **before** atomic Publisher
   namespace rename. A post-success archive/status error cannot relabel
   the positive effect as uncertain or authorize a second publication.
4. `automation/publisher_archive_recovery.py`: explicit source-gated
   *archive-only* recovery validates the immutable Capability/Publisher
   binding, pinned actual video+caption bytes, existing positive Profile
   receipt, and independently accepted native/subordinate mutator-stop
   evidence. It performs only a same-ID filesystem rename, never an
   Android action, Publisher job creation or Backend re-submission.
5. `automation/capability_reconcile_runtime.py` exact reconcile now
   recognizes archive-only recovery, re-reads the positive Profile result
   after namespace repair, and only then delegates Capability terminal
   authority to `CapabilityStore.finalize_terminal`. All mutation gates
   remain source-closed before final acceptance.
6. `automation/capability_job_store.py` published Profile terminal
   verifier now requires exact job ID, Capability and Backend IDs, immutable
   request/video/caption hashes, PUBLIC visibility and a positive verifier;
   a superficial `verified=True` field alone is insufficient.

### Open code-completion and evidence dependencies

- No accepted native TikTok template/signing/version/modal signatures or
  independently calibrated dispatch-age threshold yet; D-G3 stays OPEN.
- Root-owned first-party Principal and clock producer acceptance, exact
  action-boundary Native Driver signed/protected receipt, all supervised
  cancellation/crash recovery and safe release rollout remain pending.
- Offline signed release candidate, positive admission/native quiescence
  receipt producer, PATCH_SAFE rollback acceptance and operator sign-off
  are not complete. None of these flags have been enabled here.
- Newly written Java and Python code has **not been compiled, executed or
  tested**. The next phase must include source integration review before
  any statement that Code Complete or acceptance is reached.

**Code Complete = NO. D-G3 = OPEN. BUSINESS COMMIT = CLOSED.
Native input = CLOSED. Release switch = CLOSED.**

## Mac-only implementation pass — 2026-10-10: terminal/rollback closure (UNTESTED)

The user reiterated: develop until frozen PRD Code Complete but do
**not** compile, execute tests, deploy, commit, push, create PR, run CI or
merge during development. This pass made only local source edits.

**Connected fixes (NOT validated):**

- `publisher/gateway_execution.py`: Capability TikTok `DRY_RUN`
  verifies the actual `ui_state.state == POST_CONFIG` object, PUBLIC
  and caption, persists preview evidence, then invokes the existing
  controller's guarded `appForceStop` under the SAME Claim. Failure
  to clean up cannot return a positive preview. Records
  `DRY_RUN_COMPLETE` with zero external effect attempts.
- `automation/publisher_backend_adapter.py`: writes a root-protected,
  write-once `publisher-dryrun-result.json` bound to the original cap
  job, Backend ID, publisher ID, immutable request/video/caption hashes,
  POST_CONFIG preview, exact source UI workflow and positive local
  cleanup. No second Publisher, no COMMIT/approval consumption.
- `automation/capability_job_store.py`: distinguishes `DRY_RUN`
  success from a real PUBLIC Profile verification. Before the one
  `VERIFIED` result/archive, requires immutable preview identity,
  zero external effect attempts, absent effect boundary and independently
  accepted native/UI Core quiescence of the original exact Claim.
- `automation/gateway_coordinator.py`: recognizes the separate
  DRY_RUN terminal candidate only with positive native quiescence;
  COMMIT retains separate positive Profile business verification.
- `automation/capability_reconcile_runtime.py`: read-only DRY_RUN
  crash reconciliation from its exact durable preview plus native
  quiescence, no new backend or UI attempt. Removed duplicate
  unreachable DRY_RUN branch and redundant COMMIT guard.
- `publisher/publish_job.py`: Legacy COMMIT may no longer recursively
  delete an existing `published/<job>` directory to reuse a stable
  identity. Conflicts now enter reconcile and preserve old evidence.
- `automation/release_postcheck.py`: new fixed root-owned release health
  and no-effects observer matching candidate, boot, baseline epoch/revision
  and fresh monotonic time, plus admission fence, original Claim,
  active/staged jobs and independent native mutator evidence.
- `automation/release_lifecycle.py`: records the exact switch SOT
  baseline and consumes ONLY fixed post-switch evidence for retained
  activation vs rollback; removed injectable caller boolean callbacks.
  The release-switch and both observer-producer acceptance gates remain
  FALSE. No release activation, rollback or signing occurred.
- `automation/capctl.py`: dropped redundant import only; all mutating
  commands remain source-gated.

**Source inspection clarified an already implemented protection:** the
existing `CapabilityStore.begin_backend_submission` holds the SAME
shared Admission Fence flock through fsync of
`SUBMISSION_POSSIBLE`, so no additional implementation was needed there.
This was confirmed by reading source, not by running a race test.

**Still preventing an honest Code Complete claim:** real accepted TikTok
package/certificate and selector/modal/visual template contract,
calibrated native JIT action-age threshold, independent root-signed
clock/Principal and Native stop/health evidence producers, any remaining
release/fault-recovery contract issues, and final static/compile/unit/
instrumentation/real-device acceptance. All production gates remain
CLOSED and no new source in this pass has been built or tested.

### Integration hardening: exact Publisher immutable manifest (UNTESTED)

- `automation/tiktok_gateway_adapter.py` now binds both
  `publish_mode` and `manifest_sha256` beside source-bound video/caption
  hashes. The immutable binding is written once before backend
  `SUBMISSION_POSSIBLE`.
- `automation/publisher_boundary_guard.py` rechecks that Publisher
  Manifest bytes still match the exact root-owned binding on every
  Gateway-bound read, then requires COMMIT mode and digest match
  immediately before the irreversible Publisher COMMITTING phase.
- `publisher/gateway_execution.py` carries the mode+Manifest hash
  in its exact runtime context rather than relying on a caller-selected
  Publisher mode; Legacy stays separately protected.
- `automation/publisher_archive_recovery.py` checks Manifest bytes/mode
  again before performing any post-success namespace-only repair.
- `automation/publisher_boundary_guard._hash_file` now hashes a
  no-follow regular inode, rechecking dev/inode/size/mtime afterwards.
  Mid-read media mutation and writable-by-others artifacts fail closed.

This is **code-only**, not acceptance. No compilation, tests, Y700
deployment, Commit/Push, PR/CI or Merge took place, and no source release
flag was enabled. Actual TikTok version/Template acceptance, native JIT
calibration and trusted native-stop receipts remain prerequisite facts.

Additional 2026-10-10 source-only DRY_RUN safeguard: Gateway Publisher
records `DRY_RUN_RECONCILE_REQUIRED` (nonterminal, retry disabled, zero
external Publish attempts) if guarded UI cleanup fails. No tests, build,
APK deployment or Git remote operations followed this edit.

## Current source-only iteration: admission/release race closure (UNTESTED)

The user asked whether coding was continuing. The Mac local worktree was
reopened, and actual edits were performed without compiling or executing
any code. The existing `CapabilityStore.admit` implementation already
allows exact durable submission replays as read-only observations while
holding the admission lock, but checks the release fence before creating
a new admission or recovering an incomplete index.

**New change**: `automation/release_lifecycle.py` now holds that same
canonical `submissions/.admission.lock` in shared mode for the entire
signed-candidate validation, quiescence observation, symlink switch,
post-switch health verification and optional bounded rollback sequence.
The candidate fence observer takes compatible shared mode; both new
admission and removal of the release fence need an exclusive lock.
This closes the check/switch window where an independent release operator
might remove the fence after the snapshot but before the symlink switch.

No release operation was attempted. `_RELEASE_SWITCH_ACCEPTED=False`
remains the independent production switch gate. This source change
has not been compiled, tested or validated, and must not be interpreted
as release readiness. The Mac worktree was inspected and contained
**66 uncommitted modified or untracked paths** as of this source-only
checkpoint; none were staged, pushed or deployed.

Remaining Code Complete blockers still include accepted native
action-boundary evidence and app-specific templates, trusted independent
sensor provenance, exact administrative recovery proof, and final
cross-module integration review. D-G3 OPEN; BUSINESS COMMIT CLOSED.

## Latest local source correction: Release/Admission durability (UNTESTED)

- Checked the original `CapabilityStore.admit` against
  `admission_fence.assert_admission_unfenced_readonly`. Existing exact
  `submission_id` bindings remain read-only discoverable during a release
  freeze; new or partial-index admissions fail closed under the SAME
  `.admission.lock` flock. No new admission or recovery was executed.
- `automation/release_lifecycle.py`: changed the crash-durable
  `_save_release_state` to loop on partial `os.write`, `fsync`
  the complete file before atomic rename and directory `fsync`, and
  remove an incomplete temp record even when the write phase fails.
  Existing approved release remains unchanged; `_RELEASE_SWITCH_ACCEPTED`
  stays FALSE.
- `automation/release_quiescence.py`: removed unused
  `trusted_native_mutator_absence` and `trusted_offline_gates_passed`
  boolean parameters from the quiescence entrypoint; release admission
  and native/UI/CI readiness come exclusively from protected local source
  receipts.
- Remaining: static code-only safety review cannot claim that the
  authenticated sensor, versioned TikTok modal/template, calibrated JIT
  maximum frame age, native-action effect witness and release rollback
  observers are accepted. `Code Complete=NO`, `D-G3=OPEN`,
  BUSINESS COMMIT/production release gates CLOSED.
- No builds, tests, device actions, Git commit/push, PR, CI or Merge.

## Latest source-only development: UI quiescence and capability probe integration (UNTESTED)

The user reiterated “继续” and retained the full frozen-PRD code-development
authorization. All changes remain in the **Mac local branch**, with **NO**
unit/Android/UI tests, compilation, CI, PR, commit, push, merge, device
deployment or any action on the Y700.

1. `automation/publisher_backend_adapter.py`: a completed synchronous
   Publisher method plus empty `active_ui_job_id/active_session_id`
   no longer constitutes positive lock-release evidence. Exact native/UI
   Core subordinate completion is independently checked through
   `resource_stop_observer.positive_synchronous_ui_quiescence()`.
2. `automation/local_fixed_backends.py`: Settings Golden's returned
   `VERIFIED` is solely restore-state evidence. It now separately
   queries source-accepted exact native UI/subjob quiescence before
   acknowledging that the UI resource is safely releasable.
3. `automation/gateway_coordinator.py`: shared foreground coordinator
   independently reconfirms the same exact Claim's native/UI Core
   quiescence before `resource_safe_to_release=True`. A backend
   `ui_mutators_quiesced_positive` boolean alone is insufficient.
   BUSINESS outcome and resource stop remain separate dimensions.
4. `automation/offline_release_builder.py`: Mac signing-side path and
   per-file-size constraints now mirror Y700 offline verification
   (canonical relative path, ≤24 MiB per file), preventing candidates
   that are signed on Mac but necessarily rejected by the verifier.
5. `automation/capability_probe_producer.py`: new fixed, foreground-only
   device/Bridge probe source aligned to existing
   `androidctl status/screen-state/keyguard-state` commands. It
   refuses caller-supplied shell, UI input, launch/wake/unlock,
   fabricated app version or native-sensor acceptance. Positive
   receipt production requires separately accepted native facts,
   matching boot/epoch/revision, Catalog readiness and exact TikTok
   installed version/signing certificate when applicable.
   `_PROBE_ISSUANCE_ACCEPTED=False` and
   `_NATIVE_PROBE_SOURCE_ACCEPTED=False` remain in source.

The local worktree currently reports **67 modified or untracked files**,
all unstaged and uncommitted. Those files have NOT been validated.
**Code Complete = NO**, **D-G3 = OPEN**, **BUSINESS COMMIT = CLOSED**,
**Release/Probe activation = CLOSED**.

Remaining material implementation gaps include accepted native template
bytes and app-specific modal signatures, calibrated JIT age, independently
authenticated runtime/clock native receipt issuers, administrative positive
stop observers, full post-switch quiescence and rollback evidence production,
and final interface/contract code review. These are not solved by adding
an unverified `approved=True` flag or turning on a gate.

### Native TikTok app identity read-only capture (UNTESTED)

The original Android Core v2 instrumentation source now includes
`observeNativeAppContract`: a read-only PackageManager observation of
the installed TikTok long versionCode and SHA-256 APK signing certificate.
It does not export certificate bytes, invoke UI input or install an App
contract. It returns `app_ui_contract_accepted=false` and
`production_dispatch_authorized=false` even when the physical package
identity was observed successfully. The frozen source constants remain
unset until a separate real-device acceptance phase.

Only local Java source edits were made; no instrumentation, Gradle build,
Android installation, screenshot or other test was run.

## Next Mac-only development batch: frozen admission ordering and exact pre-submit replay (UNTESTED)

User continues authorizing Rev3.7 source implementation only. **No build,
compiler, test, Y700 deployment, Commit, Push, PR, CI, or Merge** executed.

**New source corrections (reviewed by read-only inspection, NOT tested):**

- `automation/capability_job_store.py` now uses the frozen §13 ordering:
  fully fsynced `.staging/cap-...` → **durable submission binding first**
  → atomic stage-to-active rename/fsync. Previously the active directory
  was visible before binding, contrary to §13. A crash after binding
  fsync but before Job activation can now activate only its exact,
  pre-effect `ADMITTED` stage under the same admission flock, after
  verifying original request/policy hashes, state revision 0, immutable
  identity, absent Backend/effect/cancel/result evidence and TTL witness.
  Upgrades with an active admission fence forbid even this activation;
  already-activated same-submission lookups remain read-only.
- A pre-existing active Job **without** its submission binding is treated
  as `ADMISSION_INDEX_MISSING_RECONCILE_REQUIRED`, not silently rebound.
  Unbound incomplete stages are not dropped on age or given a second ID.
  Dangling/symlinked binding paths also fail closed.
- `automation/capability_job_store.py` now durably records only
  allowlisted `CLOCK_SUSPECT_PRE_SUBMIT` or `RESOURCE_BUSY_PRE_SUBMIT`
  prerequisite failures into `WAITING_RESOURCE`, requiring a positively
  durable original Backend `NEVER_CREATED` witness and no mutation/effect
  uncertainty, cancel, or terminal marker.
- `automation/gateway_coordinator.py` implements frozen §13's narrow
  same-submission **pre-submit availability recovery exception**:
  exact original request/policy/submission, allowlisted durable blocked
  reason, same original Backend identity and NEVER_CREATED witness.
  It re-enters only the existing coordinator path; fresh policy, TTL,
  source-owned runtime facts, canonical Claim, Backend lookup and release
  admission fence must still pass. All uncertain/unknown/post-effect
  replays remain strictly read-only and never mint another Backend.
  `CLOCK_SUSPECT_PRE_SUBMIT` gets its durable marker at the actual
  pre-submit TTL refusal. Generic backend/transport errors do not qualify.
- `automation/recovery_inventory.py` now distinguishes a **durable
  bound stage awaiting activation** from a partial/corrupt stage by
  inspecting the original submission registry under the shared admission
  flock. It never activates, deletes or retries a staged Job.
- `automation/backend_reconcile.py` refuses to classify a Backend
  identity mismatch as `NEVER_CREATED` simply because a returned
  lookup document claims positive noncreation.
- `automation/effect_boundary.py` and
  `automation/capability_cancellation.py` harden the shared
  cancel-vs-effect decision against symlinked/dangling durable
  markers. A corrupt marker is not treated as an absent effect/cancel.
  All irreversible release gates remain FALSE.
- `Rev37NativeFrameRegistry.java` now references the ONE packaged
  `Rev37NativeTemplateRoute.templateContractAccepted()` contract
  instead of a second unrelated template-acceptance boolean. Independent
  production D-G3 and native dispatch gates remain unchanged/CLOSED;
  this avoids a permanently unreachable accepted route after future
  factual template review.

**Status:** SOURCE DEVELOPMENT CONTINUES, `CODE_COMPLETE=NO`,
`D-G3=OPEN`, `BUSINESS_COMMIT=CLOSED`, `RELEASE_SWITCH=CLOSED`.
Critical remaining code/acceptance dependencies include real TikTok
version+signer/template/modal evidence, empirically calibrated native
JIT frame age and effect/stop witness issuers, authenticated Principal/
clock source acceptance, and complete integration review. Previous CI
results do not validate any uncommitted edits. No source activation flag
was relaxed.

## Local integration hardening: admission/release and source-level trust (UNTESTED)

This checkpoint follows the user's repeated instruction to keep coding toward
Rev3.7 **Code Complete**, with NO builds, tests, commits/push, PR, CI, merge
or Y700 deployment before full development concludes.

- `CapabilityStore.admit()` preserves a read-only exact transport replay
  during a release fence, but blocks new admission and any staged
  `.staging -> active` activation under the same durable admission flock.
  It does not grant a second Backend submit.
- `release_lifecycle.switch_release_after_acceptance()` now acquires a
  **separate exclusive release transaction lock** before the shared
  admission lock. Shared admission ownership blocks new jobs and fence
  removal; exclusive release ownership serializes concurrent switchers.
  Missing accepted release evidence still blocks before changing symlinks.
- Canonical `resource_arbiter` runtime and lock inode handling now fail
  closed on untrusted parent, symlink, ownership or mode. Claim reads and
  append-only audit entries use no-follow bounded/root-owned regular
  files and durable writes; no implicit chmod of an existing untrusted
  resource lock.
- `Rev37NativeFrameRegistry.bindMatchedLocator()` refuses a closed
  native screenshot, recycled bitmap or non-template match even if token
  strings and target geometry otherwise agree. The independent template,
  App version, modal and D-G3 gates remain CLOSED.

These are manually inspected source edits, **NOT compiled, unit-tested,
instrumented, deployed or acceptance-verified**. Existing green CI for
older commits cannot be used to validate these local changes.

**Code Complete remains NOT PROVEN.** Genuine TikTok version/certificate,
versioned template and modal signatures, native postcondition proof,
independent producer acceptance, fault recovery and release signoff still
require further source closure and the eventual user-authorized final
acceptance batch.

## Continued local integration: admission fence SOT and failure attribution (UNTESTED)

User requested continued coding. **No compilation, test execution,
deployment, commit/push, PR, CI, or merge** was performed. This is
source-only implementation work on the existing Mac development branch.

### Source changes in this batch

- `automation/admission_fence.py`: `assert_admission_unfenced_readonly`
  accepts the *exact Job Store submissions root* (defaults to production
  `SUBMISSIONS`). Filesystem identity, root-only owner/mode, no-follow
  fence and trusted ENOENT-only "unfenced" status remain fail-closed.
- `automation/capability_job_store.py`: the existing canonical
  `self.submissions/.admission.lock` now shares the same fence root in
  all three paths — staging-to-active crash recovery, brand-new
  submission admission and durable `SUBMISSION_POSSIBLE` before the
  first Backend call. A release fence cannot be checked against a
  different hard-coded source than the admission lock.
- `automation/gateway_coordinator.py`: canonical failure-stage mapping
  with `failure_stage`, `source_phase`, `last_success_stage`,
  `retry_class` and explicit effect-retry denial. On ambiguous Backend
  submission/ACK, `action_attempts` and
  `external_effect_attempts` are UNKNOWN/null rather than fabricated
  zeros, and `retry_class=RECONCILE_ONLY`. Confirmed pre-submit blocks
  retain zero attempts and may permit REOBSERVE_ONLY when appropriate.

### Still not source-level Code Complete

Native visual mutation remains intentionally CLOSED pending version-pinned
TikTok acceptance/locator evidence. Independent UI descendant
quiescence, accepted sensor/provenance and the full resource/effect
recovery operational chain still require integration work and final
verification. Explicit GC currently only permits protected auxiliary
terminal-temp pruning when its separate apply gate is accepted;
full archive/index tombstone protocol and proven orphan staging cleanup
are NOT implemented. Real release/admission-fence/rollback semantics
need accepted native quiescence and signed release evidence.

No prior CI PASS or old Android receipt proves these changes.
`CODE_COMPLETE=NO`; `D-G3=OPEN`; `BUSINESS_COMMIT=CLOSED`;
`RELEASE_SWITCH=CLOSED`.

## Local coding continuation: single durable Reconcile authority (UNTESTED)

- `automation/explicit_reconcile.py`: legacy
  `reconcile_exact_final` no longer independently calls
  `CapabilityStore.finalize_terminal` using a caller-created
  `ReconcileProof` or operator boolean as authority. For compatibility it
  may classify input read-only, but the ONLY terminal action delegates to
  `automation/capability_reconcile_runtime.py` and its independently
  source-gated `reconcile_exact_after_acceptance`, which re-reads exact
  durable Publisher/Profile, Settings restore, observation or root receipts.
  No additional executor, Backend ID, external retry or TikTok input path.
- Final Gateway failure classification now distinguishes *known zero
  actions before possible submission* from *unknown after submission*;
  the latter is `RECONCILE_ONLY` and may not be automatically replayed.
- Admission fence points to the exact same submission root as the
  canonical Job Store. Status/replay, staging activation, new admission
  and backend first-submit rules remain distinct and reviewable.

**No compilation, tests, Git operations or Y700 actions.** This source
still requires final contract closure/empirical TikTok version/template
inputs, native quiescence witness acceptance and whole-PRD verification.
Independent production gates remain FALSE.

## October 10 — targeted integration hardening (MAC SOURCE ONLY, UNTESTED)

Continued under the user's standing **develop-first** instruction:
no compilation, lint/test execution, real Y700 actions, installation, Git
commit/push, PR/CI or Merge before full PRD source implementation.

Focused on existing end-to-end wiring rather than adding another
independent Gateway/Publisher:

1. `publisher/gateway_execution.py`: Publisher COMMIT failure handling
   preserves the **original** error even if the advisory singleton
   `publisher.json` update also fails. The success path keeps its durable
   Profile-verified receipt and never rewrites it with an ambiguous result
   after an archive-only failure. No second Publish attempt.
2. `automation/resource_stop_observer.py`: active original Backend
   durable binding is now checked against the exact Capability ID,
   original request SHA-256 and current Claim; archived terminal proof also
   requires the request hash and `external_effect_retry_allowed=false`.
   Fixed the missing `Mapping` import used by the positive synchronous
   quiescence observer. Resource-only release still cannot derive success
   from a process PID or unavailable native stop evidence.
3. `automation/settings_golden_adapter.py`: completed subordinate UI
   request JSON is retained as a **non-replay tombstone** rather than
   deleted after success; writes a bounded durable `.receipt.json`
   containing exact Job/Backend/subjob/Claim identity and PASS marker.
   Any crash/uncertainty retains original request and blocks silent replay.
4. `automation/backend_reconcile.py`: an exact,
   `durable_never_created_proof=true` Backend lookup no longer
   contradicts itself by setting `identity_verified=false`; preserves
   immutable identity while still denying automatic Backend reallocation.
5. `automation/release_postcheck.py`: completed the referenced `Any`
   typing import; no release activation performed.

### Source completion versus activation
- **Code Complete remains unproven**: these are uncompiled/unvalidated edits.
- D-G3 OPEN; TikTok BUSINESS COMMIT, final source activation and Release
  Switch remain CLOSED.
- Genuine Y700 TikTok version/cert, accepted image/template and app modal
  signatures, calibrated action-time frame age, trusted sensor/clock and
  native quiescence acceptance cannot be invented in Mac-only development.
- Before final testing, continue to reconcile interface contracts of
  original UI Core/Publisher, producer source acceptance, release/GC
  and exact crash recovery. Once source is complete, follow the separate
  user-authorized consolidated testing/CI stage, not earlier.

## October 10 — same-lock subordinate provenance and pre-submit reconciliation (UNTESTED)

Additional Mac-only Rev3.7 source edits, **no execution/compilation/test/
deployment/Git commit or remote operation**:

- `automation/subjob_provenance.py`: under the original
  `capability_job_id/transition.lock`, `SUBJOB_BOUND` now re-reads the
  canonical `resource_arbiter.assert_guard` Claim and requires exact
  `owner_kind=CAPABILITY`, Job ID, top Backend ID, request SHA-256,
  claim_id and owner_id. It no longer trusts two identical but potentially
  stale caller-provided dictionaries as source of ownership truth.
- `automation/backend_reconcile.py`: a positively proven never-created
  Backend keeps `identity_verified=true` when its ID/hash were exact.
- `automation/settings_golden_adapter.py`: same-ID UI subjob remains
  non-replayable after completion, with original request evidence retained
  and a durable, identity-bound success receipt. UI workflow executor is
  still not accepted for production.
- `automation/capability_cancellation.py` existing code was inspected;
  it already distinguishes durable `CANCEL_REQUESTED` from positively
  proven pre-submit `CANCELLED`. No new cancellation Backend or blind
  stop path was created.
- Resource outcome and BUSINESS outcome remain independent. A safe resource
  release does not imply the external TikTok effect has been verified or
  is retryable; the native mutator stop source stays NOT ACCEPTED.

**Code Complete/real-device acceptance: NOT CLAIMED.** Current safety
release constants remain FALSE, D-G3 OPEN. The user requires finishing
the entire source implementation before a consolidated test/PR/CI batch.

## Local continued development checkpoint — 2026-10-11 (UNTESTED)

The user asked whether Rev3.7 work continues and reiterated the existing
directive to finish all Frozen PRD source **without any compilation,
testing, device deployment, Git commit/push, PR, CI or Merge**. Reopened
Mac worktree on `feat/aac-rev37-sprint1a` and inspected the actual
admission fence, durable Job Store, Gateway and effect-boundary source.

### Source changes

- `automation/capability_job_store.py`: delayed ACK
  `record_backend_submission()` may **not regress** a job from
  `RUNNING_UNSAFE`, `VERIFYING` or another advanced state back to
  `BACKEND_SUBMITTED`. Only an exact `BACKEND_SUBMITTING` job may
  advance initially; idempotent calls in advanced states require the
  matching original fsynced `SUBMITTED_ACKNOWLEDGED` Backend receipt,
  deterministic Backend ID and request hash.
- `automation/effect_boundary.py`: in addition to the existing
  `backend_submitted=True` state flag, irreversible approval consumption
  requires the original `backend-execution.json` to confirm one
  `SUBMITTED_ACKNOWLEDGED` submission, `attempt_serial=1`,
  `submission_possible=true` and the exact Job/Backend/request identity.
- The existing admission-fence logic has been inspected: initial admission
  and stage recovery refuse a fsynced release fence; Backend's first
  possible submission checks the SAME admission flock. Existing
  read-only replays remain permitted without introducing a new Backend.

### Known constraints

These source edits are **not compiled or tested**, and they do not
authorize any production effect. This worktree contains many previously
written and still-unverified modules. Complete Code Complete requires
further source contract closure; in particular the native TikTok app
signing/version, accepted templates, modal signatures, calibrated JIT
age, positive effect/upgrade facts and full error-path integration have
not been accepted. D-G3 remains OPEN; BUSINESS and release gates CLOSED.
Current CI status is not validation of this source batch.

## Mac-only development continuation — durable Claim, terminal namespace and Settings tombstones (UNTESTED)

**Development-only changes.** No compile, test, deployment, Git commit/push,
PR, CI or Merge. Production/D-G3/Effect/Release gates remain CLOSED.

- `automation/resource_arbiter.py`: distinguish an unavailable/corrupt
  runtime root from actual absent `android_ui` Claim; only ENOENT for the
  exact claim file under an independently validated directory returns
  `None`. Any parent failure stays fail-closed, never interpreted as
  free resource.
- `automation/capability_job_store.py`: archived idempotent terminal
  results require a matching durable identity/result and absence of
  duplicate `active/` entry. Status lookup now rejects duplicate same-ID
  active/archive/other-archive namespaces; it no longer silently selects
  the first path and obscures an inconsistent final outcome.
- `automation/settings_golden_adapter.py`: Settings protocol-v2
  subordinate UI request is persisted with protected directory
  validation and O_EXCL atomic new/fsync, leaving the immutable request
  tombstone; no replaceable fixed `.tmp` for potential mutation replay.
- `automation/capctl.py`: already separately gated `gc --apply`
  returns a structured actual result on future acceptance instead of
  ignoring `gc_apply` and hardcoding exit status 2. No GC was executed.

### Cross-module invariants reviewed in this continuation

1. `CapabilityStore.admit()` allows exact bound-submission *read-only*
   replay with the admission fence active, but checks the fence under
   canonical admission lock before fresh or staged activation.
2. `begin_backend_submission()` rechecks that same fence while holding
   shared admission lock and durably enters `SUBMISSION_POSSIBLE` before
   calling any Backend adapter.
3. `LocalPublisherBackend.submit_exact()` records the exact Backend
   acknowledged identity *inside* synchronous Publisher execution;
   therefore `effect_boundary.cross_effect_boundary()` reads real
   acknowledged evidence at the final single-use callback. The
   Coordinator's later acknowledgement handling must be idempotent.
4. Post-submit UNKNOWN never becomes `VERIFIED` merely because a
   transport/Backend ACK exists; terminal positive receipt and exact
   original Backend binding are checked independently.
5. TikTok version/signature, immutable template, overlay/modal and native
   JIT calibration remain absent and source-gated. They are NOT inferred
   from developer fixture limits or source files.

**Code Complete: NOT YET**. The documented change set has NOT been
compiled, tested or deployed. Continue source-level contract convergence
and honest blocker inventory before final validation authorization.

## 2026-10-11 local source convergence: no tests, no Git or device actions

Continued user authorization: **finish all frozen Rev3.7 PRD code before
any tests, builds, PR/CI or Merge**. This round performed only Mac
CodexPro `read/search/edit` operations. The Mac branch remains the
uncommitted `feat/aac-rev37-sprint1a` worktree.

### Contract convergence edits

- `automation/runtime_evidence_producer.py`: capability-scoped
  `app_ui_contract_match` semantics. `android.device.observe` and
  `android.root.exec` require no application UI version contract;
  Settings UI workflow requires a **positive physical Settings contract
  probe**, and TikTok requires BOTH accepted Catalog UI contract and
  current accepted physical probe evidence.
- `automation/capability_probe_producer.py`: an accepted Settings
  runtime probe must affirm its actual App UI Contract; the produced
  record includes `app_ui_contract_match=true` only after positive
  independent native evidence. Neither root-owned Catalog configuration
  nor merely finding a package is sufficient.
- `automation/capability_job_store.py`: crash-resumed
  `result.json` -> archive step now rejects a result unless its
  version, terminal flag, exact immutable request and original
  Backend ID, completion timestamp and `external_effect_retry_allowed
  = false` all match. A partial or malformed result is not a terminal
  permission token.
- Reviewed the existing Publisher `publish-result.json` durable write
  before archive rename, Capability result verifier, cancel-before-effect
  ordering, single canonical UI Claim, and shared admission fence lock;
  did **not** claim these untested source paths had passed validation.

### Remaining explicit non-Code-Complete boundaries

1. Independent live Y700 acceptance facts (TikTok package signing cert,
   exact installed version, frozen Create template digest, overlay
   selectors, route-calibrated frame age and native Driver last-mile
   input dispatch) are **NOT** available. Never invent them or flip D-G3.
2. Root-owned first-party Principal + clock + runtime/native probe
   producers exist as gated code, but their provenance has not passed
   integration or physical acceptance.
3. Resource stop/release, cancel, ambiguous effect reconciliation,
   post-switch health, rollback and CLI maintenance are untested
   and remain fail-closed pending final review.
4. Final static/compile/unit/fault injection/Android acceptance,
   Git push, PR/CI and Merge are expressly deferred by user instruction
   until the entire code implementation is ready.

**Code Complete = NO; D-G3 = OPEN; BUSINESS COMMIT = CLOSED; release
activation = CLOSED.** No tests, compilation, Git operations or Y700
actions were performed this round.

## 2026-10-11 continuation: release-crash classification and native Publish provenance (UNTESTED)

All edits remain **Mac-local source only**. No build, compile, static-test
runner, unit/instrumentation test, device operation, Git commit/push, PR,
CI, or merge was initiated.

- `automation/release_lifecycle.py`: added a source-owned
  `inspect_release_restart_readonly()` under the existing release
  transaction/admission locks. It compares root-owned release SOT phase,
  exact candidate/previous/active paths, actual symlink target and
  immutable release manifest after a crash between SWITCH_PREPARED,
  pointer replacement and POST_SWITCH_VERIFY. Only exact, consistent
  ACTIVE/ROLLED_BACK records are classified as such; interrupted and
  conflicted states require operator Reconcile, with **no automatic
  rollback/admissions resume/backend retry**.
- `automation/capctl.py`: `upgrade --status` now uses that read-only
  inspector; source-specific admission, clock, Runtime, Release and
  Ingress errors produce structured BLOCKED results rather than a raw
  unhandled exception. Any upgrade mutation remains gated/disabled.
- `Rev37NativePublishBoundary.java` + existing
  `AutomationInstrumentedTest.java`: removal of externally passed
  `hostClaimedCapability` authority. At an irreversible semantic
  action boundary, the native Driver now reads the physical durable
  Claim to decide Legacy vs Capability, and requires the request route
  marker merely to AGREE with the observed owner. Unknown/ADMIN
  owner and contradictory flags fail CLOSED.
- `AutomationInstrumentedTest.java`: independently recognized known
  TikTok Publish button labels cannot be downgraded to a generic
  reversible click by a request-controlled `side_effect`. This is
  defense in depth, **not** complete locale/versioned Publish button
  acceptance. Native Publish and D-G3 release constants remain FALSE.

**Not yet Code Complete:** version-pinned TikTok UI assets/modal signatures,
accepted live native action age, source-attested runtime/clock/device probes,
and finally unified crash/resource/release fault handling still require
development/real-device acceptance. No earlier CI result validates these
source changes.

## Mac-only follow-up: durable release restart / native owner / audit lineage (UNTESTED)

Source-only continuation, **no test, compile, install, device action,
Git commit/push, PR, CI or merge**.

1. `automation/release_lifecycle.py`:
   `inspect_release_restart_readonly()` now classifies symlink/manifest/
   release-state identity across interrupted SWITCH_PREPARED /
   POST_SWITCH_VERIFY / rollback windows. It never autonomously repairs,
   rolls back or resumes admissions.
2. `automation/capctl.py`: `upgrade --status` invokes that read-only
   classifier; Runtime/Ingress/Release/Resource-specific errors are
   structured BLOCKED replies, avoiding uncaught `ResourceError` with
   no `.code` property.
3. `AutomationInstrumentedTest.java` +
   `Rev37NativePublishBoundary.java`: real durable native owner_kind
   determines whether an EXTERNAL_IRREVERSIBLE action belongs to the
   LEGACY or CAPABILITY path. A caller's mode flag may only agree with
   this independent fact; unknown/ADMIN owner is denied. Known TikTok
   Publish semantic controls are additionally treated as irreversible
   even when the caller labels them reversible. The list of localized
   controls is not a certified versioned selector contract; accepted
   native Publish and D-G3 gates stay FALSE.
4. `automation/resource_arbiter.py`: `_lineage` now reads the existing
   append-only Claim audit using owner-verified O_NOFOLLOW, bounded
   same-inode bytes, newline completeness, duplicate-key rejection and
   exact per-owner generation/Claim conflict detection. No journal
   repair/truncate/rotation is attempted on suspicious records.

**Code Complete remains NOT established** pending exact real-device
TikTok version/signature, accepted template/modal/age and publish button
contracts; trusted runtime/clock/native proof acceptance; and a full
cross-module implementation review before the user's deferred final
test/CI/merge batch. Earlier CI receipts do not validate these edits.

## Local source review batch: Publisher proof ordering and API-contract alignment (2026-10-11; UNTESTED)

Scope: Mac-only source editing. Absolutely no build, interpreter invocation,
lint, tests, device action, Commit/Push, PR, CI or Merge was performed.

### Confirmed and edited

- `publisher/gateway_execution.py` now requires independently parseable,
  unambiguous **two-field** Android keyguard facts
  (`mShowing=false` AND `mInputRestricted=false`) plus one exact
  `mWakefulness=Awake` observation. A substring from another dumpsys
  property or just one negative keyguard line cannot imply unlocked.
  Ambiguous OEM formatting is blocked; nothing wakes/unlocks the device.
- `before_irreversible` prechecks both video and caption immutable
  hashes against the original signed Publisher manifest/Gateway binding
  **before** one-use public approval consumption. Existing second check
  after durable effect boundary and before Publisher COMMITTING is kept.
  Inconsistency denies dispatch and does not retry Publish.

### Audited as already implemented (DO NOT duplicate)

- Publisher DRY_RUN writes `publisher-dryrun-result.json` under original
  Capability transition lock, with exact publisher/backend IDs and
  POST_CONFIG/caption/visibility/cleanup proof. Capability Store insists on
  this durable verifier and independent native UI quiescence before
  `VERIFIED`. Missing proof remains nonterminal.
- Native Driver already prevents unaccepted `EXTERNAL_IRREVERSIBLE`
  semantic action routing; new D-G3 gate must still be accepted with
  independent exact app+FrameToken+locator evidence.
- Same canonical `admission.lock` gates both new Job creation and
  `SUBMISSION_POSSIBLE`, while exact immutable replay inspection remains
  possible after release fence.
- Cancel pre-submit terminalization and normal resource-only reconciliation
  both have explicit protected proof paths. Release gates remain FALSE.

### Remaining before claiming PRD Code Complete

Source-level contracts still require static convergence for full release
upgrade/restart/rollback, app-specific native release and screenshot route
acceptance, trusted first-party producer provisioning, all CLI adapters,
crash/fault states and code review. TikTok app certificate, version,
accepted selector/template and calibrated age are genuine device facts:
they are **unknown**, cannot be fabricated during Mac-only coding.
All production/action gates remain CLOSED and no result from old CI may be
attributed to this uncommitted worktree.

## 2026-10-11 continued local integration: exception boundary and release operator provenance (UNTESTED)

This batch is **source editing only**, performed on the existing Mac
worktree. No build, compilation, static execution, test, Y700 access,
Git commit/push, PR/CI or merge occurred.

### Actual source edits

- `automation/gateway_coordinator.py`: fail-closed exception convergence
  after durable `SUBMISSION_POSSIBLE`. An exception during the original
  Backend call, ACK persistence, positive verifier or result archive now
  conservatively enters `RECONCILE_REQUIRED` under the exact original
  Backend identity and explicitly attempts a safe state mark only while
  the active job still exists without an authoritative result marker.
  A partial terminal/archive transition is never reclassified as
  never-created or silently retried. The canonical Claim's independent
  quiescence proof remains the only release authority.
- `automation/admission_fence.py`: install/remove of a release admission
  fence now requires not only the existing operator-session boolean but
  an *independently source-accepted*, root-owned, exact operator-action
  authorization record. The authorization is pinned to release ID,
  INSTALL_FENCE/REMOVE_FENCE, original boot/epoch/revision, authenticated
  local principal, short expiration, nonce and single use. Missing or
  unacceptable authority is CLOSED. Removal validates the release ID
  before using it as a protected filename. Separate
  `_FENCE_MUTATION_ACCEPTED=False` and
  `_RELEASE_OPERATOR_PROOF_SOURCE_ACCEPTED=False` remain.
- `automation/resource_stop_observer.py`: positive stop inspections now
  normalize durable SOT, immutable Job and publisher receipt read
  exceptions to a blocked diagnostic. Missing/corrupt source facts can
  never count as a safe resource release.

### Still missing before Code Complete

- Accepted concrete physical TikTok UI contract: exact installed
  version/signing certificate, independent frozen template/locator,
  blocking overlay signatures, route frame-age calibration, and final
  native single-use input dispatch;
- provenance-accepted first-party principal, clock and runtime/native
  sensors; real per-Backend effects and resource stop evidence;
- full release lifecycle/cancellation/upgrade source review and eventual
  fault-state/Android acceptance (deferred by user).

**Status: Code Complete NOT CLAIMED. D-G3=OPEN, BUSINESS=OFF,
Release Switch=OFF.** Source-only candidate implementation; previous CI
receipts do not cover these edits.

## 2026-10-11 continuation: post-submit exception convergence and one-use release authorization (UNTESTED)

**Development-only edit set**, grounded in the repository's frozen Rev3.7
PRD and current AGENTS.md. Source edits stayed in the Mac worktree:
no compile, lint, tests, native Android invocation, Y700 deployment,
Git commit/push, PR, CI or Merge.

- `automation/gateway_coordinator.py`: pre-submit Runtime Authority
  now checks the freshly observed **exact state_epoch, revision,
  capability_job_id and backend_job_id** against independently read
  authoritative state, in addition to boot, policy hash and BOOTTIME age.
  A previously sampled healthy fact cannot authorize an action after a
  semantic revision or original Job/Backend identity change.
  The same module has a fail-closed exception convergence path
  after the durable `SUBMISSION_POSSIBLE` witness. If the original bound Backend could
  have started, the original identity and protected Claim are retained
  for `RECONCILE_REQUIRED`, never replayed under a new Backend ID.
  Partial terminal/archive writes are not rewritten as FAILED or
  "never created." Pre-submit failures remain distinctly blocked.
- `automation/admission_fence.py`: a release operator's
  `trusted_maintenance_session=True` field alone never authorizes
  install/remove. Exact root-owned action+release+principal+SOT+expiry
  evidence must be independently accepted; the producer-acceptance
  gate remains CLOSED. A one-use nonce is durably consumed under the
  existing admission lock **before** either fence mutation. A crashed
  attempt cannot replay that same authorization, including after a
  partial write or uncertain unlink. Release ID input is validated
  before protected-file path construction.
- `automation/resource_stop_observer.py`: unreadable/corrupt
  Capability Job state, Publisher receipt or authoritative SOT is
  explicitly normalized into a negative stop-proof receipt; it cannot
  be mistaken for a safe resource release.

**Still NOT Code Complete:** The native TikTok app-version-specific
template/signature/modal/JIT calibration and final input route remain
unaccepted; first-party Principal, clock and native release evidence
producers are still source-gated; operator release state machine and
full protocol/error handling need further static integration closure.
Source is intentionally not executed. D-G3=OPEN, BUSINESS=OFF,
Release Switch=OFF.

## 2026-10-11 continuation: source-level resource/ADMIN/release safety closure (UNTESTED)

The user reiterated **continue code development only until frozen PRD Code
Complete**. This edit set intentionally made only Mac-local source changes.
It did not compile, run unit/static-check/test commands, instrument Y700,
run CI, commit, push, create/update a PR, merge, or activate any gate.

**Source contract repairs made in existing runtime code:**

- `automation/resource_arbiter.py`: `bind_active_execution` now REFUSES
  overwriting any existing active UI Job, Session, backend marker or pending
  Reconcile. `clear_active_execution` requires the exact currently bound
  job/session and no pending Reconcile, rather than treating a missing
  binding as successful cleanup. Canonical `acquire_android_ui` finally
  now re-reads the durable Claim; on any active subjob, session, backend
  marker or Reconcile state it RETAINS the Claim and records Reconcile
  rather than blindly removing ownership after a Python scope exit.
  **Claim release is not evidence of TikTok BUSINESS success.**
- `automation/admission_fence.py`: release operator fence removal requires
  an exact `ACTIVE` success for the SAME candidate or an exact completed
  one-time `ROLLED_BACK` transaction for that candidate, matching the
  actual active symlink and its independently inspected release manifest
  Git revision. A stale unrelated ACTIVE marker or symlink drift cannot
  reopen admissions. Before consuming the one-use REMOVE grant, the
  code reobserves canonical UI Claim absence and a zero active/staging
  startup inventory. The independent release and operator source gates
  remain FALSE; no fence was installed or removed.
- `automation/resource_reconcile_v37.py`: emergency ADMIN force-reset
  authority now returns the accepted source nonce and durably consumes
  `claim_id + owner_id + generation + nonce` **before** bumping
  `state_epoch` or invoking original-Backend stop. A crash after
  consumption cannot reuse the same authority to repeat an unsafe stop.
  Root auth/effect gates remain FALSE.
- Frozen existing admission logic already distinguished strict read-only
  replay under the fence from incomplete `.staging -> active` repair
  and pre-backend submission. That was preserved rather than rewritten;
  `SUBMISSION_POSSIBLE` remains a durable no-auto-replay witness.
- Existing `capability_reconcile_runtime.py` already uses positive
  typed durable Publisher, Settings, Observe and Root result evidence.
  It remains explicitly gated and NEVER resubmits an effect.

**Unresolved Code Complete/acceptance facts (do not substitute guesses):**
actual TikTok package/signing/version and frozen visual templates; independent
native modal/overlay observations and calibrated action-age threshold;
accepted first-party Principal/clock/physical runtime & stop-proof producers;
final accepted native Driver mutation adapter and exhaustive recovery/upgrade
contract review. Code-completion and device acceptance are separate: none
of these were claimed as verified by these source-only edits.

**Status:** CODE_COMPLETE=NO; D-G3=OPEN; BUSINESS_COMMIT=CLOSED;
RELEASE_SWITCH=CLOSED; no production deployment.

## Source-only continuation: admission fence/submission race and UI stop generations (UNTESTED)

This continuation responds to the explicit instruction to keep developing
Rev3.7 until Code Complete, while deferring ALL tests, builds, deployment,
Git commit/push, PR, CI and merge. Existing frozen PRD and exact local source
are the authority; no source release gates were opened.

### Newly closed source-level integration gaps

- `automation/gateway_coordinator.py`: an existing Capability Job can no
  longer pass its preflight, release the admission lock, then BEGIN a backend
  submission AFTER a release admission fence is installed. Acquire the
  **same canonical** `submissions/.admission.lock` shared before
  adapter preparation and keep it until the synchronous exact Backend is
  complete or durably uncertain. Verify the root-protected admission fence
  while this shared lock is held. The exclusive fence installer must wait.
  In the `finally` path, settle/retain the exact android_ui Claim BEFORE
  releasing the shared admission lock. A failure in claim cleanup cannot
  leave the admission flock permanently held by the foreground scope.
- `automation/resource_arbiter.py`: every new Claim carries
  `ui_execution_generation=0`; each `bind_active_execution` increments
  it durably before a subordinate can execute. The generation is retained
  across `clear_active_execution`, appears in the canonical audit trail,
  and cannot be provided or reset by a workflow request. Invalid/missing
  generations fail closed.
- `automation/resource_stop_observer.py`: both the live synchronous
  release check and post-crash exact-stop inspection now demand a native
  stop receipt for the **current claim UI execution generation**. A fresh
  wall-time/boot timestamp and matching Claim ID alone are insufficient:
  the previous subordinate's stop evidence may not release a later
  subordinate. Live synchronous release also requires generation >0.
- `automation/admission_fence.py` and `capability_job_store.py` were
  re-read against the earlier code changes: immutable same-submission
  status remains readable while fenced; partial-stage activation and all
  NEW admissions remain blocked under the SAME canonical admission lock.

### Source-only open items

- **Native stop evidence producer** must issue the new
  `ui_execution_generation` from accepted native/UI Core session lineage;
  the existing `_NATIVE_MUTATOR_ABSENCE_ACCEPTED=False` continues to
  fail closed. Neither release nor reconcile gained authority.
- UI template/app-version/modals, actual native action-boundary positive
  acceptance, operator/clock evidence and final install/rollback readiness
  are still incomplete or awaiting genuine device facts.
- This entire working tree is uncompiled and untested; the earlier CI and
  physical read-only receipts do NOT validate this source change.
  `Code Complete = NO`, `D-G3=OPEN`, `BUSINESS= CLOSED`,
  `Release Switch = CLOSED`.

## Follow-on local source batch: generation-bound stop receipt producer (UNTESTED)

- `automation/native_stop_receipt_producer.py`: new independently
  acceptance-gated foreground publisher for exact-Claim native mutator-stop
  receipts. It requires a root-owned native/Bridge sensor receipt with the
  **latest** `ui_execution_generation`, fresh matching boot/epoch and
  positive Linux/native mutator absence; scans existing UI Core jobs for
  protected terminal result evidence; rechecks the current Claim generation
  before atomically publishing the stop receipt. This is NOT a substitute
  for accepting the physical native/Bridge sensor and never releases a
  Claim or decides BUSINESS outcome.
- `automation/publisher_backend_adapter.py`: source-wires this producer
  before the independently guarded `positive_synchronous_ui_quiescence`
  decision, without converting producer refusal to a successful stop.
- `automation/local_fixed_backends.py`: Settings Golden takes the exact
  same native stop receipt path after durable restore verification. This
  unifies normal Publisher/Settings stop proof under one canonical Claim
  generation rather than divergent "backend returned" booleans.

All three producer/source activation constants remain FALSE; the physical
native sensor is not accepted, its receipt is not available, and zero
UI inputs or cleanup were attempted. No build, tests, deployment, commit,
Git push, PR, CI or merge. Code Complete is still unproven.

## Remaining whole-PRD implementation work — NOT DONE

1. **Sprint 1 / 1A integration completion**: establish the Android Driver's
   trusted, fresh SOT epoch/revision and boot boundary; foreground activity
   observation; complete authoritative window inventory and versioned overlay
   exceptions; monotonic exact frame JIT check at the actual native Driver
   input boundary; versioned independent locator templates, route age
   calibration and source-to-frame identity. Production D-G3 still CLOSED.
2. **Sprint 2 Gateway**: exact versioned Catalog, policy precedence,
   authenticated identity, deterministic `submission_id` registry, durable
   capability jobs, permission and expiry rechecks, admission lock, protocol
   compatibility, immutable policy/request hash, CLI diagnostic views.
3. **Sprint 3 Coordinator / backend binding**: foreground synchronous
   coordinator, durable deterministic backend identity before resources and
   submission, exact job status, reconcile and cancel, claim session rollover,
   stale subordinate-job rejection, STOPPED/ZOMBIE handling and owner recovery.
4. **Sprint 4 Outcome / approval / irreversible effect**: single-authority
   effect boundary, binding of approval to exact content/request/effect,
   consume-before-publish ordering, positive verifier contracts, unknown
   outcome `RECONCILE_REQUIRED`, never auto-retry uncertain effects.
5. **Sprint 5 Settings acceptance implementation**: stable reversible
   guarded Settings change/restore, resource arbitration and state hash
   checks. User-requested no-test policy means acceptance itself is deferred.
6. **Sprint 6 TikTok migration / lifecycle**: opt-in frozen DRY_RUN,
   BUSINESS capability wiring without activation, legacy concurrency
   migration, staged health v3 integration, read-only release patch
   diagnostics, immutable release activation/quiescence and rollback
   implementation. Real TikTok publish remains disabled.
7. **Final gated batch only after implementation**: code review; unit and
   fault/crash injection tests; Android real-device and workflow acceptance;
   baseline regression; Git commit/push; PR/CI; security and manual approval
   gate review; merge if all checks and required authorizations pass.
   Do NOT assume PRD completion or user approval from individual unit code.

## Hard guardrails throughout development

- No `am instrument`, Gradle build, `unittest`, smoke/doctor test or test
  harness execution while the development-only instruction is active.
- No `git push`, remote PR update, CI trigger or merge.
- No production APK replacement, no automated UI input, no TikTok
  upload/publish or approval consumption.
- No new always-on daemon, message broker, database or cross-device
  scheduler without separate explicit authorization.
- Runtime state, media, credentials and rooted-device identifiers stay
  outside Git.
- Keep all D-G3 and BUSINESS release gates CLOSED until full acceptance.

## 2026-10-12 continuation: native State Integrity observer provenance (SOURCE ONLY)

Implemented in `Rev37NativeStateObserver.java` on the Rev3.7 feature branch:

- The Android-side fixed SOT reader now checks the fixed-path file's root UID,
  exact `0600` permissions, regular-file type, bounded size, and device/inode/
  size/mtime metadata before and after reading. A symlink or changing file
  identity rejects the observation. This is a conservative read-only
  *candidate*, not an accepted replacement for a native open/fstat/O_NOFOLLOW
  primitive. GNU/Toybox `stat -c` support and root shell semantics still
  require device verification; metadata sampling cannot make reads atomic.
- Foreground Activity observations reject ambiguous multiple resumed
  activities and recheck the exact component after the second native window
  walk and semantic modal observation.
- Existing native read-only observation timeout, dual window checks and
  keyboard overlap refusal remain fail-closed. No action is dispatched.

**Outstanding:** A trusted root-side inode-bound single-fd SOT reader,
complete versioned window/modal contract, accepted TikTok version/signature,
real-device age calibration and Android native JIT acceptance remain open.
D-G3, BUSINESS COMMIT and release switches remain CLOSED. No tests, builds,
Android device execution, PR, CI, merge or deployment were authorized.
The user's newer instruction explicitly permits multiple source commits and
batched feature-branch GitHub pushes, provided feature push does not run CI;
older no-push notes above are superseded on that narrow point.

## 2026-10-12 continuation: Sprint 3 same-backend recovery / reconciliation (SOURCE ONLY)

This development pass inspected the dormant `ForegroundCoordinator`,
`CapabilityStore`, exact outcome reconciler and startup recovery inventory
against frozen Sprint 3/4 requirements. Source changes:

- The only exceptional same-submission WAITING_RESOURCE continuation now
  reads its durable state/identity/backend/execution under the original
  transition flock. It requires matching original policy/request hashes,
  the exact `NEVER_CREATED` witness, no uncertainty, and no symlinked
  cancel/effect/terminal markers. The private continuation entry point
  also independently checks the deterministic Backend ID and binding.
- Pre-submit prerequisite block recording and existing-backend binding
  reject symlinked effect/cancel/result evidence, incorrect backend ID,
  or an inconsistent execution witness. They cannot convert a possible
  submission into `NEVER_CREATED`.
- Exact outcome reconciliation checks state/request consistency and the
  deterministic Backend ID; startup recovery checks the same original
  Backend identity. An unknown recovery state no longer claims zero
  external effect attempts: unknown is `null`, not `0`.

This is source/static work, not a tested or activated Gateway. The
backend creation/submit/ACK crash windows, full effect-boundary
linearization, Android real-device evidence and TikTok business verification
remain unaccepted. D-G3, Gateway production, business effects, TikTok
COMMIT, and release/rollback activation gates remain CLOSED.

### Sprint 4 follow-through: immutable approval / final-effect binding

The still-CLOSED effect crossing candidate now independently reloads the
canonical request, validates its request hash and exact COMMIT/PUBLIC mode,
and compares BOTH content and caption hashes with the recorded approval.
It also requires the deterministic `cap-...--publisher-01` Backend ID,
versioned binding/execution evidence, and rejects a symlinked pre-existing
effect marker during approval recording. The Publisher callback independently
checks exact Backend ID, approval request/policy/artifact/visibility identity.
These are static source protections only: native action-boundary evidence,
physical TikTok app version/signature, real JIT frame age and final effect
verifier are NOT accepted or exercised. All release gates remain CLOSED.

### Publisher precommit filesystem provenance follow-through

`publisher_boundary_guard.py` now requires `O_NOFOLLOW` rather than
silently falling back to an ordinary open, rejects hardlinked protected
JSON/media evidence, compares ctime as well as size/mtime during reads,
and checks that the pathname still points at the same regular inode after
the read/hash. This protects precommit evidence from simple path replacement
and concurrent in-place modification. It is not an accepted substitute for
atomic immutable artifact sealing, native input-time proof or real-device
integration. All production and TikTok effect gates remain CLOSED.

### 2026-10-12 continued Sprint 2/3: crash classification and immutable state

A second static implementation batch hardens the durable admission/recovery
classification shared by Gateway and Coordinator:

- `CapabilityStore.bind_backend` now refuses a FIRST bind unless the durable
  job is still ADMITTED with no existing execution/effect/cancel/terminal
  marker. A repeated bind is limited to the original bound/waiting job,
  exact versioned backend/execution identity and proven NEVER_CREATED state.
  A partially written Backend binding is never silently repaired as a new
  Backend attempt.
- `recovery_inventory` refuses to call a job PRE_SUBMIT_NEVER_BOUND unless
  the ADMITTED state explicitly proves no submission, effect, mutation,
  cancellation or terminal marker. The bound case checks versioned witness,
  typed attempt counters, deterministic Backend ID and nonterminal phase.
  Staged admission inspection rejects symlinked backend/execution/effect,
  cancel and terminal marker paths.
- `capability_reconcile_runtime` requires versioned backend/execution and
  typed submission flags; a DRY_RUN positive receipt is disqualified by
  any cancel or effect marker, including symlinked evidence.
- Shared durable `_read_json` now verifies that the protected pathname still
  refers to the same single-link inode after reading; inode/ctime/size
  changes fail closed instead of returning a displaced state snapshot.

These are static checks and implementation, NOT executed fault-injection
acceptance. Production Gateway, D-G3 and TikTok COMMIT remain CLOSED.
