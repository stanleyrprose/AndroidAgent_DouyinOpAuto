# PRD — Y700 Android Automation Core v0.6 Rev3.6

## Capability Gateway + Deterministic Execution, State Integrity & Runtime Readiness

**文档状态**：FROZEN ARCHITECTURE + IMPLEMENTATION-INPUT SOT — Rev3.6 Targeted Red-Team Consistency Closure / Production Runtime Implementation NOT Authorized  
**版本**：v0.6 Rev3.6 Frozen — Rev3.5 Baseline + Concurrency/Governance/Durability/Authorization Closure  
**日期**：2026-10-05  
**目标设备**：Lenovo Y700 / TB323FU / Android 16 / Debian 13 chroot  
**Canonical Repository**：`stanleyrprose/AndroidAgent_DouyinOpAuto`  
**Canonical Branch**：`main`  
**Canonical Baseline**：`v0.6 Rev3.6 Frozen`（本文件自 Freeze Approval 起 supersedes Rev3.5 Frozen，成为唯一 frozen implementation-input SOT）  
**实施授权**：**Production Runtime Implementation = NO。Phase 0B validation tooling / tests / evidence collectors = AUTHORIZED。任何 production runtime、Gateway/Core/Bridge 行为修改仍需独立 Production Runtime Implementation Authorization。**

**本文档取代/合并：**

1. `PRD-Y700-Android-Automation-Core-v0.6-Deterministic-Execution-State-Integrity.md`
2. `PRD-Y700-Android-Automation-Core-v0.6-Capability-Gateway.md` 的 Capability-first、namespace、TTL/expiration、Adapter、discovery/health、transport boundary、observability、Outcome Contract 与 migration intent；
3. Rev3/Rev3.1/Rev3.2/Rev3.3 已关闭的 concurrency、durability、transport retry、semantic fingerprint、overlay、zombie/liveness、upgrade/rollback 等问题；
4. **Rev3.4 Frozen 的 Documentation/Ops/Preflight Closure 全量保留**：Glossary、reboot recovery reference flow、operational alert semantics、machine-executable preflight checklist、fault-injection harness、fsync performance counters、Catalog overlay-policy validation；
5. Backburner 可迁移架构原则：capability/readiness advertisement、`alive != ready`、state ownership 决定 fallback、安全单一 gateway boundary、measurement-gated break-even；**不移植** iOS/Metal/ANE、LLM split-prefill/remote-KV/split-decode 实现；
6. Rev3.5 深层一致性闭环：pre-submit backend terminalization、deterministic claim reconcile、STOPPED/ZOMBIE 分离、fingerprint profile/watched-field schema、`state.json`/`result.json` 语义分离、claim-session rollover + stale-subjob rejection、overlay window classification、suspend/BOOTTIME、admission-lock load gate。

7. Rev3.6 targeted Red Team closure：cancel/effect-boundary linearization、ADMIN reset quiescence proof、`state.json` crash-safe lifecycle persistence、Phase 0A/0B authorization split、LEGACY resource reconcile addressability、app/UI contract compatibility、cross-environment BOOTTIME validation、CLOCK_SUSPECT reboot semantics、reconcile dwell observability、backend never-created positive-proof predicate。

> **Rev3.6 authority rule**：Rev3.6 Frozen 自本次 Freeze Approval 起 supersedes Rev3.5 Frozen，成为唯一 canonical implementation-input SOT。Rev3.6 完整继承 Rev3.5/Rev3.4 已冻结的 preflight、fault-injection、runbook、reboot recovery、alerting、CI/DoD 与 deep-consistency gates，并增加本轮 Red-Team/Freeze-Review consistency closures。

---

# 0. Executive Summary

Y700 Android Automation Core v0.5 已完成 generic Android automation runtime 的核心基础：AndroidX UI Automator 2.4 driver、workflow-scoped instrumentation、semantic selector、deterministic cardinality、bounded retry、failure evidence、checkpoint、cooperative cancellation、driver reset、Bridge v2 integration，以及真实 Settings / TikTok DRY_RUN 验收。

随着 Y700 很快承担更多 Android 自动化能力，下一阶段出现三个相互关联的问题：

1. **Capability growth**：Cloud ChatGPT、Telegram、Hermes、未来其他 Agent 不应继续直接理解每个 app/controller/backend 的内部实现，需要一个稳定、可发现、可审计的 capability interface。
2. **State integrity**：Agent 观察 Android 状态与真正执行 mutation 之间可能发生状态漂移；多个自动化入口、用户手工触屏、runtime crash 都可能让旧判断变成危险动作。
3. **Runtime readiness / fallback ambiguity**：设备或进程“还活着/可连接”不代表某个 capability 当前可安全执行；同样，某个依赖失败后能否降级、重建或 fallback，取决于当前 state ownership、backend/effect phase，而不能由 controller 临时猜测。

v0.6 Rev3.5 以 **Rev3.4 Frozen** 为 canonical mother baseline：完整保留其 Documentation/Ops/Preflight closure，并合入 Backburner-derived readiness/fallback/secure-boundary/measurement guardrail，再关闭 Freeze Review 发现的深层时序与接口语义缺口：**pre-submit terminalization、deterministic resource reconcile、fingerprint profile/watched-field determinism、blocked-vs-terminal status semantics、claim-session reacquisition、overlay classification、suspend invalidation 与 admission-lock load behavior**。Rev3.5 仍不扩大 runtime 基础设施。

Rev3.6 不改变上述架构方向，只对 Red Team 暴露的 implementation-determinism gaps 做窄修订：**cancel/effect-boundary concurrency、ADMIN reset quiescence、lifecycle state durability、Phase 0 authorization semantics、LEGACY resource recovery addressability、app/UI runtime compatibility 与时间/恢复证据闭环**。

整个修订继续遵守 **Minimal Sufficient Architecture (MSA)**：

> **只增加一个薄 Capability Gateway、一个执行层 state-integrity contract，以及基于现有 Catalog/doctor 的最小 readiness 语义；不增加新 daemon、MQ、数据库、scheduler、plugin framework、dependency graph engine 或第二套 Android runtime。**

总体架构：

```text
Trusted Controller
(ChatGPT / Telegram / Hermes / local CLI)
        │
        ▼
Capability Gateway
(thin foreground synchronous coordinator)
        │
        ├─ Static Capability Catalog
        ├─ Effective Policy
        ├─ Readiness / Compatibility View (advisory)
        ├─ android_ui Resource Arbiter
        ├─ Durable Capability Job / Backend Binding
        └─ Outcome / Approval Contract
        │
        ▼
Existing Android Automation Core v0.5+
        │
        ├─ state_epoch + revision + semantic state_hash
        ├─ compare-before-mutate
        ├─ MUTATION_PREPARED journal boundary
        └─ postcondition / reconcile
        │
        ▼
Existing Bridge v2 filesystem runtime
        │
        ▼
Android host / UI Automator / TikTok / Settings
```

核心原则：

```text
Gateway adds abstraction.
Core adds state correctness.
Bridge preserves execution durability.
No layer may weaken the safety guarantee of the layer below it.
```

v0.6 的完成标准不是“所有 Android 自动化都已 Gateway 化”，而是：

- 有一个小而稳定的 Capability Contract；
- Gateway crash 不会制造未知第二次 backend execution；
- caller 因 transport/network 超时重发同一 `submission_id` 不会创建第二个 capability job；
- safety-critical durable write/fsync/rename 失败均 fail-closed，并按副作用阶段区分普通 failure 与 reconcile；
- storage/permission/time-source/sub-job provenance/admin bypass 均有显式实施契约；
- official Controller 对 timeout/DEVICE_BUSY 必须复用同一 `submission_id` 并按 bounded backoff/status/reconcile 顺序恢复，不能通过换新 ID 绕过不确定任务；
- 每次 UI mutation 前除 state hash 外，还必须通过 global blocking-overlay guard，防止 Activity 不变但 Dialog/Window 覆盖导致误触；
- 实施前必须具备统一术语、reboot recovery flow、operational alert rules 与 machine-executable preflight/fault-injection harness，避免关键规则只存在于文字理解中；
- 所有 production UI mutation 共用唯一 `android_ui` ownership protocol；
- caller 无法降低 capability 的 minimum safety policy；
- stale state 在 mutation 前 fail closed；
- unsafe effect 前先 durable crossing boundary；
- unsafe effect 后 ambiguity 不自动 retry；
- TikTok 当前 COMMIT/reconcile 保证被保留而不是重新发明；
- Settings 与 TikTok 证明该架构可用于 generic 与 real business workflow；
- 未来新 capability 可以沿同一合同扩展，而无需改写 Bridge/Core；
- `alive/reachable`、`READY`、`safe to execute` 三者语义明确分离；
- dependency failure 的 fallback 只能按 state/effect ownership 规则发生，不能绕开 deterministic backend / no-blind-replay；
- 任何未来 Mac/Y700/cloud execution placement 必须先有真实 workload break-even measurement；v0.6 不实现自适应调度。

---

# 1. Authority and Inherited Baseline

本 PRD 是 **增量架构**，不是重写项目。以下已接受事实继续 authoritative。

## 1.1 Git / code SOT

- GitHub `main` 是 code、scripts、non-secret config、public-safe docs 的唯一 canonical Git SOT。
- Runtime state、media、secret、device backup、recovery binary 不进入 public Git。
- Emergency live-device fix 稳定后必须 reconcile 回 Git。
- Y700 live filesystem 不成为第二 code SOT。

## 1.2 Bridge v2 remains frozen

Bridge v2 Sprint 6A 保持 frozen：

```text
/opt/y700/jobs/
├── .staging/
├── active/
├── archive/
│   ├── succeeded/
│   ├── failed/
│   ├── cancelled/
│   └── reconcile_required/
└── control/
```

继续保持：

- `.staging -> active` same-filesystem atomic rename；
- filesystem-first durable execution state；
- generic `root_exec` replay policy = `NEVER`；
- request identity / SHA binding；
- orphan child 不 blind replay；
- lease expiry 只代表 liveness evidence，不授权 replay；
- uncertain live child / side effect -> `RECONCILE_REQUIRED`；
- result-before-archive lookup 不产生 false `JOB_NOT_FOUND`；
- 不引入 SQLite / Redis / MQ；
- optional Unix socket Sprint 6B 仍保持 measurement-gated，不因 Gateway 激活。

## 1.3 Android Automation Core v0.5 remains baseline

已接受能力继续保留：

- AndroidX UI Automator 2.4；
- workflow-scoped instrumentation；
- semantic / relation selectors；
- deterministic 0/1/many cardinality；
- click / longClick / inputText / clearText / swipe / scroll；
- waitFor / waitStable / assert；
- pressBack / pressHome；
- failure evidence；
- checkpoint；
- screen/keyguard preflight；
- driver reset；
- safe checkpoint / unsafe checkpoint distinction；
- cooperative cancellation；
- generic Settings acceptance；
- TikTok generic-core DRY_RUN acceptance。

v0.6 **不得为了 Gateway API 美观重写这些已验收路径**。

## 1.4 Existing TikTok safety remains authoritative during migration

现有 TikTok production path 已经具有：

- canonical UI lease：`/opt/y700/runtime/android-ui.lock`；
- DRY_RUN final publish hard-stop；
- durable COMMITTING boundary before Publish；
- explicit/standing authorization semantics；
- exactly-one COMMIT attempt；
- ambiguous outcome reconciliation；
- Profile verification；
- no blind Publish replay。

v0.6 Gateway 必须复用或加强这些保证，不得降低。

---

# 2. Problem Statement

## 2.1 Capability interface fragmentation

当前上层 controller 需要理解：

```text
automation/ui_job.py
apps/tiktok/controller.py
bridge/root-exec.sh
publisher/*
device-specific paths
different result contracts
different recovery semantics
```

随着 Y700 增加更多能力，这会导致：

- controller 与 backend implementation 强耦合；
- safety policy 分散；
- capability discovery 困难；
- 不同 Agent 对同一功能使用不同入口；
- 新业务能力容易绕过已有 recovery / approval / verification。

需要一个稳定的 capability surface，但不能为了“平台化”引入过度架构。

## 2.2 Stale observation

典型 race：

```text
Agent observe
      ↓
得到“Publish 按钮 / 某 checkbox / 某页面状态”
      ↓
用户触屏 / 其他 workflow 改变 UI
      ↓
Agent 按旧状态执行 click
```

单纯 job dedupe 无法解决。

## 2.3 Automation interleaving

未来可能同时存在：

```text
Cloud ChatGPT
Telegram
Hermes
scheduled workflow
local maintenance
```

如果两个 mutating workflow 同时控制 screen，即使各自逻辑正确，也可能互相破坏。

## 2.4 Gateway crash can weaken backend safety

如果 Gateway：

```text
submit backend
-> crash
-> backend_job_id 尚未 durable
```

则恢复时无法判断 backend 是否已执行，重复 submit 可能制造第二次 side effect。

## 2.5 Process lock alone is insufficient

如果 Gateway 持有 `flock()`，backend 异步执行，而 Gateway process crash：

```text
flock 自动释放
backend 仍在点击 UI
第二个 workflow 获得 lock
```

因此需要“live mutual exclusion + durable semantic ownership”。

## 2.6 Unsafe effect cannot be inferred after the fact

对于 Publish：

```text
dispatch click
-> crash
```

无法可靠知道 click 是否已送达。

因此 safety boundary 必须 **在可能产生 external effect 的动作前 durable**。

## 2.7 Policy must not be caller-controlled

Capability 的：

- required resource；
- replay policy；
- verification；
- approval；
- TTL bounds；

不能由 caller 任意降低，否则 Gateway 反而成为 safety bypass。

## 2.8 Truth ownership must remain unambiguous

新增 `/opt/y700/capability-jobs` 后不能声称又出现一个“全局 runtime SOT”。

必须采用：

> **One fact -> one authoritative durable record.**

---

# 3. Product Goal

## 3.1 Primary Goal

把 Y700 从：

```text
many controllers
-> backend-specific commands
-> Android
```

演进为：

```text
many trusted controllers
-> one small Capability Contract
-> existing proven Core / Bridge backends
-> Android
```

同时保证：

```text
observe / validate intent
-> persist deterministic backend intent
-> acquire required resource
-> bind/validate current device state
-> execute exact backend once
-> verify
-> commit final outcome
```

Capability 的产品模型保持原始 PRD 的核心表达，但明确 safety ownership：

```text
Capability
=
Intent
+ Minimum Policy
+ Adapter
+ Verifier
```

其中 caller 提供 Intent/Payload 与有限可收紧选项；minimum safety policy 由 static Catalog 所有。

在任何无法证明安全的 crash / stale / ambiguity 下 fail closed。

## 3.2 Success Definition

v0.6 PASS 必须同时满足：

1. Gateway 是薄 wrapper，不重写 Core / Bridge；
2. Gateway 没有 mandatory daemon；
3. Gateway 没有 detached background job execution；
4. capability request / policy / backend binding immutable 且 durable；
5. production UI mutations 只有一个 canonical `android_ui` ownership protocol；
6. stale observation 在 mutation 前被拒绝；
7. backend submit crash 不会自动创建第二 backend job；
8. unsafe effect 前已有 durable boundary；
9. unsafe effect 后 verifier failure -> `RECONCILE_REQUIRED`；
10. caller 无法降低 capability minimum safety；
11. TikTok 现有 approval / COMMIT / reconciliation semantics 保留；
12. Settings generic acceptance 和 TikTok business acceptance 均通过；
13. 新 capability 可通过 catalog + plain adapter function 扩展，无需新 infrastructure。

---

# 4. MSA Scope

## 4.1 v0.6 MUST include

```text
Static Capability Catalog
Minimal static execution profile (placement / foreground / readiness requirements)
Capability Contract
Foreground synchronous coordinator
Durable capability job
Transport retry admission identity (`submission_id`)
Immutable request hash
Effective safety policy
Deterministic backend binding
Exclusive android_ui resource arbitration
State token / compare-before-mutate
Durable mutation prepare record
Unsafe effect boundary
Outcome Contract
Exact-request approval binding
Explicit reconcile
Static catalog + dynamic health/readiness separation
Capability readiness advertisement + reason codes
Fallback eligibility bound to existing state/effect/replay facts
Single external control boundary; internal backend surfaces remain non-public
Durability / storage / permission operational contract
Bounded explicit maintenance / GC path
Settings acceptance
TikTok migration/acceptance
```

## 4.2 Explicitly deferred

以下全部不属于 v0.6：

```text
Gateway daemon
detached execution
not_before scheduler
priority queue
general workflow/DAG engine
Redis / PostgreSQL / SQLite runtime DB
MQ
event bus
plugin framework
dynamic plugin loading
capacity-N resource semaphore
network_io capacity model
storage_io capacity model
multi-device fleet scheduler
cross-runtime Mac/Y700/cloud placement scheduler
automatic alternate-runtime failover
generic dependency graph / dynamic capability negotiation engine
health heartbeat daemon
active cross-request business-idempotency engine
semantic-version negotiation
HTTP public API
multi-tenant authorization
automatic unsafe replay
background automatic GC daemon
automatic stale-claim lease stealing
new Android driver framework
iOS/browser/desktop abstraction
```

## 4.3 Resource scope cut

v0.6 **真正实施的 exclusive resource 只有：**

```text
android_ui = capacity 1
```

原因：

- 当前 Gateway 首要风险来自 screen/UI ownership；
- TikTok 已有真实 `android-ui.lock`；
- Settings/TikTok 两个 acceptance 都需要此资源；
- `package_manager`、`device_global` 可在未来 measured need 出现后新增；
- 提前实现多资源 acquisition / capacity-N semaphore 违反 MSA。

未来若增加多 resource，必须先定义 canonical total ordering；v0.6 不实现。

---

# 5. Design Principles

## 5.1 Preserve lower-layer guarantees

Gateway 的抽象不能削弱 Bridge v2 / v0.5 已有保证。

```text
Gateway convenience
<
execution correctness
```

## 5.2 Thin Gateway

Gateway 只做：

```text
capability validation
policy resolution
resource ownership
backend binding
backend orchestration
approval/outcome binding
status/reconcile
```

它不：

```text
implement UI Automator
implement root executor
become workflow engine
own app business internals
```

## 5.3 Trigger / Transport Is Not Job

当前调用路径仍可为：

```text
Cloud ChatGPT / Telegram / Hermes
-> trusted control plane
-> capctl / Python API
```

任何未来 transport/wake mechanism 最多传递：

```text
capability_job_id / wake hint
```

完整 request、policy、backend binding 与 outcome 必须来自 durable filesystem。

因此：

```text
transport failure may increase latency
transport failure must not corrupt correctness
```

v0.6 不实现新的 wake transport。

## 5.4 Execution Is Not Outcome

```text
ACTION_EXECUTED != BUSINESS_OUTCOME_VERIFIED
```

Backend 返回成功只能证明 execution fact；BUSINESS capability 必须依其 verifier contract 形成 durable outcome。

## 5.5 Compare Before Mutate

所有 protocol v2 UI mutation：

```text
current state
must match
expected state token / AUTO observation
```

否则 action attempt = 0。

## 5.6 Durable Intent Before Side Effect

两个不同层级：

### Android mutation

在 action 前：

```text
MUTATION_PREPARED
fsync
```

### Business unsafe effect

在 first non-safe external effect 前：

```text
EFFECT_BOUNDARY_CROSSED
fsync
```

两者语义不同，不合并为一个模糊的 `SIDE_EFFECT_APPLIED`。

## 5.7 Fail Closed

不确定：

```text
≠ success
≠ failure
≠ safe to retry
```

而是：

```text
RECONCILE_REQUIRED
```

## 5.8 One Fact, One Owner

每个 durable fact 只能有一个 authority。

## 5.9 No duplicated lock hierarchy

上一版 State Integrity PRD 中独立 `mutation.lock` **取消**。

原因：

```text
Gateway android_ui lock
+
Core mutation lock
=
two arbitration systems
```

v0.6 使用唯一 canonical `android_ui` arbiter 作为 UI mutation lane。

## 5.10 Business logic stays above primitives

Core primitive 不新增：

```text
publishTikTok()
postInstagram()
sendWhatsApp()
```

业务 capability 通过 adapter 组合 generic primitives / existing controllers。


## 5.11 Transport Retry Identity Is Not Business Idempotency

网络超时导致 caller 不知道第一次 `invoke` 是否已被 Gateway 接收，是 **admission identity** 问题，而不是业务语义幂等问题。

v0.6 Rev3.1 增加 mandatory：

```text
submission_id
```

规则：

```text
same submission_id + same canonical request_sha256
= same capability job

same submission_id + different canonical request_sha256
= SUBMISSION_ID_CONFLICT
```

它只解决：

```text
the same submission being retransmitted because the response was lost/unknown
```

它不解决：

```text
two independently created business intents that happen to have equal payloads
```

因此：

```text
submission_id retry dedupe
!=
business idempotency
```

合法的第二次业务操作必须使用新的 `submission_id`、新的 capability job，并遵守新的 approval/effect-boundary 语义。

## 5.12 Alive / Reachable Is Not Ready

Rev3.5 明确区分：

```text
process/device alive or reachable
!=
capability READY
!=
safe to execute this mutation now
```

`READY` 只能表示“最近一次 on-demand readiness 检查时，mandatory dependencies 满足”；真正 mutation 仍由 resource ownership、state guard、overlay guard、approval/effect boundary 与 backend durable facts 决定。

因此：

- 单个 process ping / SSH success / PID existence 不得推出 capability READY；
- stale `node-health.json` 不得授权 execution；
- readiness failure 可以提前阻止工作，但 readiness success 永远不能绕过 Core 的 execution-time safety checks。

## 5.13 Fallback Follows State Ownership and Effect Phase

dependency failure 后是否可以继续，不按“服务是否还能重启”判断，而按 **当前状态是否可安全重建** 判断。

最小三类：

```text
OPTIONAL_AUXILIARY
= 非 correctness 依赖；缺失只允许 semantic-no-op degradation

RECONSTRUCTIBLE_PRE_EFFECT
= effect 前可通过重新 observe / reinitialize 重建；
  必须保持同一 submission/capability/top-backend identity

EXCLUSIVE_OR_UNCERTAIN
= unique runtime state / backend may still run /
  mutation may have occurred / effect boundary crossed
= no transparent fallback; status/reconcile only
```

任何 fallback 都不得：

```text
allocate second top-level backend after uncertainty
change submission_id for same intent
weaken resource/state/effect policy
repeat an external commit
```

## 5.14 Optional Degradation Must Preserve Semantics

只有当缺失组件被 static contract 明确视为非 safety-critical、且继续执行不会改变 capability 的业务语义与 verifier 保证时，才允许：

```text
READY -> DEGRADED
```

例如非关键 diagnostics/telemetry 缺失可以降级；approval、verification、resource ownership、state integrity、effect-boundary durability 绝不属于 optional degradation。

## 5.15 One External Gateway Boundary

任何现在或未来的 remote transport 都必须终止在一个 authenticated control/Gateway boundary：

```text
Remote Controller
      ↓
trusted transport / control plane
      ↓
Capability Gateway
      ↓
internal Bridge / UI Core / root executor
```

内部 backend/primitive 不因新增 transport 而各自暴露 network listener，也不各自发明 remote auth。

## 5.16 Measure Break-even Before Adaptive Routing

Backburner 的可迁移经验是：**offload/routing 是否有价值取决于 end-to-end break-even，而不是某个设备理论算力更强。**

v0.6 不实现跨 runtime routing；但未来任何 Mac/Y700/cloud placement 必须先测：

```text
setup + transfer + queue + compute + sync + recovery-risk margin
```

并证明优于当前路径后，才允许引入 threshold。没有 measurement 时，保持 canonical runtime，不为“可能更快”增加 scheduler/failover abstraction。

---

# 6. Target Architecture

```text
┌─────────────────────────────────────────────┐
│ Trusted Controllers                         │
│ ChatGPT / Telegram / Hermes / local CLI     │
└──────────────────────┬──────────────────────┘
                       │ Capability Request
                       ▼
┌─────────────────────────────────────────────┐
│ Capability Gateway                         │
│ Foreground synchronous coordinator         │
│                                             │
│  Catalog -> Effective Policy               │
│      ↓                                      │
│  Readiness / Compatibility View            │
│  (advisory early gate, not safety authority)│
│      ↓                                      │
│  Durable Capability Job                    │
│      ↓                                      │
│  android_ui Resource Arbiter               │
│      ↓                                      │
│  Deterministic Backend Binding             │
│      ↓                                      │
│  Adapter                                    │
│      ↓                                      │
│  Outcome / Approval / Reconcile             │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│ Android Automation Core                    │
│                                             │
│ state_epoch + revision + semantic hash      │
│ state token / AUTO guard                    │
│ MUTATION_PREPARED                           │
│ action / postcondition                      │
│ MUTATION_COMMITTED                          │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│ Bridge v2 — unchanged                      │
│ filesystem-first durable jobs              │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
                Android host/device
```

---

# 7. Gateway Execution Model

## 7.1 v0.6 decision

唯一 execution model：

> **Foreground Synchronous Coordinator**

`capctl invoke` 或 Python API 的调用进程负责本次 invocation 的 orchestration，但 **不拥有 backend correctness**。推荐统一顺序：

```text
validate request
-> load exact capability contract
-> resolve effective policy
-> initial expires_at / approval precheck
-> activate immutable capability job
-> derive deterministic backend_job_id
-> persist backend.json + fsync
-> acquire required resource claim (if any)
-> recheck expires_at
-> submit exact backend_job_id
-> wait/observe exact backend
-> verify / reconcile outcome
-> terminalize only when final outcome is known
```

关键不变量：

```text
backend identity is durable before resource claim depends on it
backend identity is durable before backend submission
```

对于没有 exclusive resource 的 read-only capability，可跳过 resource step，但 backend identity ordering 不变。

## 7.2 No detached execution

v0.6 不支持：

```text
capctl invoke --detach
background queue
scheduled later execution
```

不存在“CLI 退出后由另一个 Gateway daemon 继续执行”的隐式模型。

这里的 **no detached execution** 只约束 Gateway orchestration，不要求所有 existing backend 与 Coordinator 必须是同一个 OS process。Bridge/UI Publisher 等既有 backend 可以按其已冻结模型拥有独立 child/process-group 生命周期；Coordinator crash 后，backend 是否仍在运行必须由 **exact backend durable facts + exact process identity** 判断，不能从 Coordinator PID 推断。

因此：

```text
Gateway coordinator lifetime
!= backend execution lifetime
```

若 backend 与 Coordinator 恰为同一 process，则 exact process death 只是 backend-stop evidence 的一部分；仍按 Section 16.6 的 deterministic reconcile proof 关闭 resource ownership。

## 7.3 Coordinator crash and recovery ownership

Coordinator crash 后：

- capability job durable 保留；
- `backend.json` durable 保留；
- backend durable job（若已提交）保留；
- durable resource claim（若安全性尚未证明可释放）保留；
- 不由 daemon 自动 resume；
- 不自动重新提交 backend；
- 不自动重放 mutating workflow。

命令语义严格分离：

```text
capctl status
= read-only inspection
= MUST NOT mutate job/resource/backend state

capctl reconcile
= explicit recovery operation
= may inspect backend/device outcome
= may safely release stale resource ownership when liveness is positively resolved
= may transition RECONCILE_REQUIRED -> final outcome
= MUST NOT automatically repeat an external side effect

capctl invoke
= create a new capability invocation
= MUST NOT silently repair or mutate an older uncertain job
```

如果一个新 invocation 遇到旧 durable resource claim：

```text
return DEVICE_BUSY / RESOURCE_RECONCILE_REQUIRED
```

而不是顺手修改旧 job。

这让：

```text
status = observe
reconcile = recovery
invoke = new intent
```

三个入口保持清晰、可预测。

Foreground `invoke` 可以在两类状态返回给 caller：

```text
final terminal outcome
or
durable RECONCILE_REQUIRED / recovery-required blocked state
```

进入 `RECONCILE_REQUIRED` 后，本次 foreground coordinator 可以退出；后续只有显式 `reconcile` 才继续推进该旧 job。

# 8. Capability Classification

Capability 分三类：

```text
BUSINESS
INTERNAL
ADMIN
```

## 8.1 BUSINESS

面向正常 controller 的稳定能力。

v0.6 production 目标：

```text
tiktok.publish
```

## 8.2 INTERNAL

构建业务 capability 的 generic primitive interface。

例如：

```text
android.device.observe
android.ui.workflow
```

默认不鼓励业务 Agent 直接绕过 BUSINESS capability 使用。

## 8.3 ADMIN

明确 escape hatch：

```text
android.root.exec
```

规则：

- 仅用于 development / maintenance；
- 不宣称具有 BUSINESS verifier / approval guarantees；
- 不作为普通 Agent 的推荐 capability；
- 任何绕过 canonical resource ownership 的 admin action 必须显式标记 unsafe；
- v0.6 不试图把 root shell 变成“安全业务能力”。

---

# 9. Capability Namespace & Contract Stability

原始 Capability Gateway PRD 的 namespace 设计保留为长期命名空间：

```text
android.device.*
android.ui.*
android.app.*
android.package.*
android.file.*
android.settings.*
tiktok.*
```

未来可扩展但 **不由 v0.6 实施**：

```text
instagram.*
whatsapp.*
chrome.*
telegram.*
camera.*
media.*
```

命名原则：

```text
<domain>.<resource>.<verb>
```

示例：

```text
android.device.observe
android.ui.workflow
android.app.launch
android.package.install
android.file.import
android.settings.set
tiktok.publish
```

一旦 capability 标记为 `stable`：

> 不得在没有 explicit migration/version change 的情况下改变其语义。

### v0.6 shipping subset

MSA 不要求一次实现整个 namespace。v0.6 只需要足够证明 architecture：

```text
android.device.observe   # read-only discovery/health path
android.ui.workflow      # INTERNAL generic UI execution
android.root.exec        # ADMIN escape hatch
tiktok.publish           # BUSINESS capability
```

`android.settings.set` 可作为 acceptance-only wrapper；是否进入 stable public catalog 由 closure review 决定。

# 10. Static Capability Catalog

## 10.1 Git SOT

建议初始只使用一个文件：

```text
config/capabilities.json
```

不建立 plugin registry / dynamic loader。

## 10.2 Definition example

```json
{
  "name": "tiktok.publish",
  "version": "1.0",
  "classification": "BUSINESS",
  "adapter": "tiktok_publish",
  "resource": "android_ui",
  "overlay_policy": {
    "top_level_guard": "REQUIRED",
    "in_app_modal": "POSSIBLE",
    "blocking_selectors": [
      {"resource_id": "example:blocking_modal_root"}
    ]
  },
  "app_ui_contract": {
    "package": "com.zhiliaoapp.musically",
    "accepted_version_codes": [123456789],
    "signing_cert_sha256": "sha256:...",
    "ui_contract_version": "tiktok-ui-v1"
  },
  "execution_profile": {
    "placement": "Y700_REQUIRED",
    "requires_foreground": true,
    "alternate_runtime_fallback": "NONE",
    "readiness_requirements": [
      "bridge_v2",
      "ui_protocol_v2",
      "instrumentation_ready",
      "runtime_permission_integrity"
    ]
  },
  "minimum_policy": {
    "replay": "NEVER",
    "verification": "REQUIRED",
    "approval": "REQUIRED",
    "expires_in_max_sec": 7200
  }
}
```

## 10.3 Overlay Policy Validation

任何会使用 `android_ui` mutation 的 capability 必须显式声明：

```text
overlay_policy.top_level_guard = REQUIRED
overlay_policy.in_app_modal = NONE_KNOWN | POSSIBLE
```

规则：

1. `top_level_guard` 对 mutating capability 不能关闭；
2. `in_app_modal=POSSIBLE` 时，`blocking_selectors` 必须至少有一个 **versioned selector**，Catalog load 时为空则 `CAPABILITY_CATALOG_INVALID`；
3. `in_app_modal=NONE_KNOWN` 不是永久保证；真实 App 行为改变后必须更新 capability/workflow contract；
4. `blocking_selectors` 是 platform top-level Window/Dialog detector 的补充，不替代 global overlay guard；
5. observation-only capability 可省略 `overlay_policy`；
6. runtime benign-window classification（IME/Toast 等）不能关闭 Catalog 中已声明的 app-specific blocker。

这样 modal safety 不依赖 capability 开发者“记得在代码里补 if”。

## 10.4 Execution Profile Validation

`execution_profile` 是 **static execution constraint metadata，不是 scheduler**：

- `placement=Y700_REQUIRED`：shipping capability 的 canonical runtime 在 Y700；
- `requires_foreground=true`：执行依赖 foreground interactive state；
- `alternate_runtime_fallback=NONE`：Y700 failure 不得被 Controller 解释成可自动改投 Mac/cloud；
- `readiness_requirements[]`：用于 discovery/doctor/early preflight 的 mandatory dependency names，不替代 execution-time Core guard。

v0.6 mutating BUSINESS capability 默认 `alternate_runtime_fallback=NONE`。本版本不实现 Mac/cloud alternate backend。

## 10.4A App / UI Contract Compatibility

对依赖 app-specific selector、modal detector、commit surface 或 verifier 的 capability，Catalog 必须声明 versioned `app_ui_contract`：

```text
package
accepted_version_codes[]
signing_cert_sha256        # when stable/available
ui_contract_version
```

规则：

1. `blocking_selectors` / expected surface 只对经过 acceptance 的 app/UI contract 有效；
2. mutating BUSINESS capability 在 early preflight 必须读取真实 installed package/version/signing identity；
3. 当前 app build 不属于已测试 contract 时：
   `APP_UI_CONTRACT_MISMATCH`, readiness=`UNAVAILABLE`, backend/UI side effect=0；
4. 禁止因为 package name 相同就假定 selector contract 仍兼容；
5. 禁止用 wildcard version/package bypass；
6. selector “未命中”本身不能反推出 blocker 存在；安全判断必须结合当前 versioned app contract + global window facts + expected surface；
7. app auto-update 后必须重新通过对应 Settings/TikTok acceptance，才可把新 version code 加入 accepted set。

因此安全模型是：

```text
known-compatible app/UI contract
+
global overlay classifier
+
versioned app-specific blocker/expected-surface contract
```

而不是：

```text
known blocker selector did not match
-> assume page is safe
```

## 10.5 Version semantics

v0.6：

```text
exact capability version match only
```

不做 semver range negotiation。

Runtime protocol/contract compatibility 另由 Section 33 advertisement/preflight 检查；它不能把 capability version mismatch 自动转换成兼容执行。

## 10.6 Static vs Dynamic

Catalog 只描述：

```text
what exists
what contract applies
minimum safety
static execution constraints
overlay contract
```

Catalog **不写动态状态**：

```text
READY / DEGRADED / BUSY / BLOCKED_RECONCILE / UNAVAILABLE / UNKNOWN
```

Dynamic health/readiness 不进入 static Catalog。

v0.6 使用：

```text
/opt/y700/runtime/node-health.json
```

作为**可选、按需刷新的 dynamic planning/preflight snapshot**。它不是 contract SOT，也不是 execution-success guarantee。

Capability discovery 的 canonical source 仍是 Git-managed `config/capabilities.json`；`capctl list/describe` 可把 Catalog 与当前 node health 合并展示。v0.6 不要求再维护第二份持久化 `runtime/capabilities.json`。

如果未来确有兼容需求输出 runtime discovery snapshot，该文件只能是可重建 derivative，不得成为 authority。

## 10.7 Execution profile is not replay permission

```text
execution_profile
= where / under what runtime prerequisites this capability is intended to run

replay/effect policy
= whether an already-started or uncertain operation may be repeated
```

因此：

```text
alternate_runtime_fallback != SAFE replay
READY != permission to mutate
placement != backend identity allocation authority
```

未来若增加 alternate runtime，必须单独 version contract；v0.6 不预留 generic adapter graph。

---

# 11. Capability Request Contract

Caller request 示例：

```json
{
  "submission_id": "01K7EXAMPLEULID...",
  "capability": "tiktok.publish",
  "version": "1.0",
  "correlation_id": "workflow-abc123",
  "payload": {
    "artifact_id": "...",
    "caption": "...",
    "visibility": "PUBLIC"
  },
  "expires_at": "2026-10-05T12:00:00+06:30",
  "requested_by": {
    "type": "agent",
    "name": "cloud-chatgpt"
  }
}
```

规则：

- `submission_id` 由 caller 在**第一次发送前**生成，并在同一次 transport retry 中保持不变；
- `capability_job_id` 由 Gateway 根据 `submission_id` 确定性派生，caller 不直接自选 job id；
- `correlation_id` 是 optional tracing metadata，不参与 authorization / admission identity；
- `payload` 是 capability-specific immutable intent；
- `expires_at` 可为空；
- v0.6 **没有 `not_before`**；未来 scheduling 属于独立需求。

## 11.1 Caller may NOT define authoritative safety

Request 不接受 authoritative：

```text
resources=[]
approval=NONE
verification=NONE
replay=SAFE
```

这些由 Catalog minimum policy 决定。

## 11.2 requested_by semantics

`requested_by`：

```text
metadata only
```

不是：

```text
authenticated identity
authorization evidence
approval evidence
```

v0.6 Gateway 是：

> local authenticated-node interface, not multi-tenant authorization boundary.

未来 HTTP / multi-user exposure 需要独立 auth PRD。

## 11.3 TTL / Expiration

保留原始 Gateway PRD 中最有价值的 stale-job protection：

```text
expires_at
```

但按 MSA 删除：

```text
not_before
deferred scheduler
```

规则：

1. `expires_at` 为空：不因时间自动失效；
2. `expires_at` 已过且 backend **尚未提交**：terminal `EXPIRED`，backend/Android side effect = 0；
3. 等待 `android_ui` 结束后、backend submit 前必须再次检查 `expires_at`；
4. backend 一旦提交，TTL 不再产生 `EXPIRED` transition；
5. backend submit 后的 execution / verification / ambiguity 必须根据 durable backend facts 与 Outcome Contract 分类；
6. unsafe effect 已可能发生但 outcome unknown：`RECONCILE_REQUIRED`；
7. caller 只能在 capability-defined bounds 内设置 TTL，不能超过 maximum；
8. default TTL / max TTL 是 capability contract 参数，原始 PRD 中的具体分钟/小时仅作 tuning 参考，不作为 v0.6 hard-coded product rule。

### Time source

`expires_at` 是绝对日历截止时间，解析/审计使用设备 `CLOCK_REALTIME`。

Gateway admission 时同时 durable 记录：

```json
{
  "ttl_clock_version": 1,
  "accepted_wall_time": "...",
  "accepted_boot_id": "...",
  "accepted_boottime_ms": 123456,
  "deadline_boottime_ms": 234567
}
```

同一 `boot_id` 内，backend-submit 前 TTL gate 以 `CLOCK_BOOTTIME` deadline 为准，避免 wall-clock jump 改变已接收请求的剩余寿命。

reboot 后 monotonic deadline 失效；Gateway 重新按 durable `expires_at` + 当前 `CLOCK_REALTIME` 判断，并由 `doctor` 暴露 reboot/time-source context。

若 reboot 后 `CLOCK_REALTIME` 被判定为 `CLOCK_SUSPECT`，且旧 job 尚未 backend submit：

```text
MUST NOT submit backend
MUST NOT classify EXPIRED from an untrusted wall clock
keep the existing pre-submit lifecycle state (e.g. BACKEND_BOUND / WAITING_RESOURCE)
phase_reason_code = CLOCK_SUSPECT_PRE_SUBMIT
terminal = false
next_action = REPAIR_CLOCK
```

这里**不得**仅因为 clock evidence 不可信就把 job 变成 `RECONCILE_REQUIRED`，否则会与“reconcile 不负责启动旧 backend intent”的规则形成恢复死路。

clock 恢复可信后，caller/controller 必须用**同一 `submission_id` + exact same request**重新进入 `invoke` admission。该调用不是新业务 intent；仅在以下条件全部成立时允许恢复 pre-submit continuation：

```text
same deterministic capability_job_id
backend positive-proven never-created
no mutation/effect uncertainty
current lifecycle remains an explicitly retriable pre-submit state
clock health = HEALTHY
TTL/approval/readiness re-check PASS
```

然后：

```text
expires_at now passed -> EXPIRED
still valid           -> continue the same job toward resource/backend submit
```

任何 `RECONCILE_REQUIRED`、backend existence unknown、mutation/effect uncertainty 都**不能**通过同-submission invoke 恢复 execution；仍必须走 status/reconcile。

### Cross-environment clock-source contract

Y700 同时存在 Android Host 与 Debian chroot。任何跨环境生产/消费的 boottime value 必须采用同一语义：

```text
CLOCK_BOOTTIME
milliseconds
same kernel boot epoch
same boot_id
```

Phase 0 必须实测：

```text
Android-host boottime delta
Debian-chroot boottime delta
suspend-before/after delta
```

两侧增量必须在测量容差内一致；若无法证明一致，不允许跨环境直接比较 token/deadline boottime 值，相关 capability fail closed。

边界：

- TTL 是 stale-intent protection，不是 security credential；
- v0.6 不防御 ADMIN 故意篡改系统时间；
- 明显时钟异常时 `doctor` 报 `CLOCK_SUSPECT`；
- state-token age 永不使用 wall-clock duration。

TTL 的唯一 correctness 作用：

```text
prevent stale intent from starting a backend execution
```

不是：

```text
cancel already-submitted work
or
rewrite an uncertain outcome as EXPIRED
```

## 11.4 Submission Identity / Transport Retry Admission

`submission_id` 是 v0.6 Rev3.3 的 mandatory request field。

推荐格式：

```text
UUIDv4 / ULID / other high-entropy opaque identifier
```

Gateway 不依赖其时间排序语义，只要求：

```text
bounded length
valid character set
caller-generated before first transmission
stable across retries of the same submission
```

Canonical admission identity：

```text
submission_sha256 = SHA256(UTF-8 submission_id)
capability_job_id = "cap-s-" + full_hex(submission_sha256)
```

`request_sha256` 基于 canonical immutable request 计算，并包含：

```text
submission_id
capability
version
payload
expires_at
requested_by
```

纯 tracing field：

```text
correlation_id
```

不进入 `request_sha256`，因此 transport retry 可以更新 tracing context，但不能改变业务 intent。

### Admission registry

使用 filesystem-only durable mapping：

```text
/opt/y700/runtime/submissions/
├── admission.lock
└── <submission_sha256>.json
```

`admission.lock`：

- 只保护 admission binding 的 compare/create；
- 是短时 metadata lock，不是 Android execution resource；
- 不在 capability execution 期间持有；
- 不形成第二套 `android_ui` ownership hierarchy；
- 必须 bounded wait，禁止无限 blocking flock。

初始基线：

```text
admission_lock_timeout_ms = 5000
allowed deployment values = 5000 | 10000 | 15000
```

`5000ms` 是初始 deployment default，不是 protocol wire constant。Phase 0 / Implementation Authorization gate 必须在真实 Y700 上覆盖 TikTok cold-start、UFS/fsync pressure 与并发 same-submission admission，测量 admission critical-section hold time；若 `p99_hold_ms >= 0.5 * timeout`，在 Implementation Authorization 前将 deployment value 提升到 10000 或 15000ms 并记录证据。

约束：

- effective timeout 是 **root-owned/Git-managed deployment setting**，不是 caller request field；
- 同一 deployed revision 内保持固定，不按单个 job 动态改变；
- `capctl doctor` 必须报告 effective value；
- 实现继续使用 non-blocking flock + `CLOCK_BOOTTIME`/monotonic deadline/backoff；
- 该 timeout 只保护 admission availability，不授予任何 execution/replay permission。

超时：

```text
ADMISSION_LOCK_TIMEOUT
```

不得创建 capability job/backend；error envelope 必须 `retryable=true`、`next_action=RETRY_SAME_SUBMISSION`；同一 submission retry 必须复用原 `submission_id`，不得因 lock timeout 生成新业务 intent。

Binding：

```json
{
  "submission_version": 1,
  "submission_sha256": "...",
  "request_sha256": "...",
  "capability_job_id": "cap-s-...",
  "capability": "tiktok.publish",
  "created_at": "..."
}
```

Admission ordering：

```text
1. canonicalize request
2. compute submission_sha256 / request_sha256
3. acquire short-lived admission.lock
4. lookup durable submission binding
5a. existing + same request_sha256
    -> return/recover exact same capability_job_id
5b. existing + different request_sha256
    -> SUBMISSION_ID_CONFLICT
5c. absent
    -> write binding temp
    -> fsync(temp)
    -> atomic rename to final binding
    -> fsync(submissions dir)
    -> create/activate exact deterministic capability job
6. release admission.lock
7. continue normal policy/resource/backend execution
```

如果 crash 发生在 binding durable 之后、capability job activation 之前：

```text
retry with same submission_id + same request_sha256
-> reuse same deterministic capability_job_id
-> complete/recover the pre-side-effect activation
-> never allocate a second capability job
```

如果 active/archive job 已存在：

```text
terminal/result exists
-> return existing terminal status

active non-terminal job
-> normally return existing job/status
-> EXCEPTION: if state is an explicitly retriable pre-submit prerequisite block,
   exact request/submission matches,
   backend is positive-proven never-created,
   and no mutation/effect uncertainty exists,
   same-submission invoke may re-enter the existing coordinator path and continue that SAME job
```

该 exception 只服务于 pre-submit availability recovery（例如 clock repaired after `CLOCK_SUSPECT_PRE_SUBMIT`）；它不得用于 `RECONCILE_REQUIRED`、unknown backend、post-mutation 或 post-effect recovery。

v0.6 不要求后台 GC。Submission binding 的 retention 至少不得短于对应 capability job 的可查询 retention。

### Caller retry / reconcile contract

Caller 必须区分：

```text
transport retry of the same submission
-> reuse submission_id

explicitly new business attempt
-> new submission_id
```

对所有官方 Controller（Cloud ChatGPT connector / Telegram ingress / Hermes / future first-party controller），`submission_id` 必须在第一次发送前 durable/locally retained，直到该业务意图达到：

```text
VERIFIED
OUTCOME_NOT_ACHIEVED
FAILED
CANCELLED
EXPIRED
```

或 operator 明确终止该 intent。

以下情况**禁止生成新的 `submission_id`**：

```text
transport timeout
connection reset
DEVICE_BUSY
RESOURCE_RECONCILE_REQUIRED
RECONCILE_REQUIRED
unknown invoke response
```

同一 intent 的恢复顺序固定为：

```text
1. retry/status using same submission_id
2. bounded exponential backoff for transient busy/transport uncertainty
3. inspect exact deterministic capability_job_id
4a. if next_action=REPAIR_CLOCK -> repair/verify clock health, then retry SAME submission
4b. if blocked/uncertain -> doctor + reconcile
5. if reconcile remains unresolved -> alert/operator escalation
6. only after a final outcome or explicit abandonment may a new business attempt receive a new submission_id
```

v0.6 reference backoff：

```text
1s -> 2s -> 4s -> 8s -> 16s
max attempts = 5
max single delay = 16s
```

实现可加入小幅 jitter，但不得改变“有界、同 ID、先 status/reconcile 后新 intent”的语义。

Gateway 无法从 payload 一般性判断两个**不同** `submission_id` 是否是同一业务意图；因此 business-idempotency engine 仍然 deferred。官方 Controller 的上述 contract 是端到端 correctness 边界的一部分，而不是可选 UX 建议。

# 12. Effective Policy

v0.6 不提供 generic caller `policy_overrides`。

因此：

```text
effective_policy
=
Catalog minimum_policy
+
deterministically resolved contract values
(currently mainly expires_at / TTL bounds)
```

而不是一个未定义 schema 的“caller policy merge engine”。

规则：

- required resource 来自 Catalog，不可由 caller 删除；
- REQUIRED verification 不可由 caller关闭；
- REQUIRED approval 不可由 caller关闭；
- NEVER replay 不可由 caller改为 SAFE；
- `expires_at` 可以由 request 设置，但必须满足 capability-defined maximum TTL；
- caller 不存在通用 `replay/approval/verification/resources` override 字段；
- future 若确有 caller tightening 需求，必须通过独立 schema/version 引入，不在 v0.6 暗含。

Activation 前必须 durable：

```text
request.json
identity.json.request_sha256
effective_policy.json
identity.json.effective_policy_sha256
```

Activation 后：

```text
request.json immutable
effective_policy.json immutable
```

任一被改变：

```text
JOB_CONTRACT_VIOLATION
```

若尚未跨 unsafe boundary：

```text
fail closed
```

若已跨 unsafe boundary：

```text
RECONCILE_REQUIRED
```

不得通过重新计算 policy 来“修复”旧 job。

# 13. Capability Job Store

## 13.1 Layout

```text
/opt/y700/capability-jobs/
├── .staging/
├── active/
└── archive/
    ├── verified/
    ├── failed/
    ├── cancelled/
    ├── expired/
    └── outcome_not_achieved/
```

**没有 `archive/reconcile_required/`。**

原因：

```text
RECONCILE_REQUIRED
= blocked but unresolved
= non-terminal
```

因此 job 保持在：

```text
active/<capability_job_id>
```

直到 explicit reconcile 得到 final outcome。

创建过程：

```text
write .staging/<cap_job_id>
fsync files
fsync dir
atomic rename -> active/<cap_job_id>
```

## 13.2 Minimal job contents

```text
request.json
effective_policy.json
identity.json
state.json
journal.jsonl
backend.json              # durable before resource claim/backend submit
approval.json             # only when required
effect-boundary.json      # only when crossed
result.json               # final terminal states only
evidence/                 # only when needed
cancel.json               # only when requested
transition.lock           # ephemeral per-capability flock; LOCK_EX writers / LOCK_SH consistent readers; never durable authority
```

不建立第二个通用 event store。

### Live lifecycle authority vs terminal marker

```text
state.json
= current capability lifecycle / blocked-state authority

result.json
= final terminal business-outcome marker only
```

因此：

- 在 durable `result.json` 尚不存在时，`state.json.lifecycle_state` 必须表示当前**非终态** lifecycle（如 `BACKEND_BOUND / WAITING_RESOURCE / RUNNING_SAFE / RUNNING_UNSAFE / VERIFYING / CANCELLING / RECONCILE_REQUIRED`）；terminal linearization 后 normalized lifecycle/outcome 由 `result.json` authority 派生；
- `RECONCILE_REQUIRED` **只写入 `state.json` + journal/evidence**，不写 `result.json`；
- `result.json` 只在五大 terminal outcome durable 后出现；
- caller/controller 不得以“`result.json` 尚不存在”推断 job 仍应普通轮询；必须读取 `state.json.lifecycle_state` 或 `capctl status` 的 normalized state。

Minimal `state.json` shape：

```json
{
  "state_version": 1,
  "state_revision": 7,
  "lifecycle_state": "WAITING_RESOURCE",
  "phase_reason_code": null,
  "updated_at": "..."
}
```

`state.json` 是由下层 durable facts 推导并持久化的 **authoritative orchestration lifecycle snapshot**；它不得覆盖或伪造 backend/resource/effect 的 authoritative durable records。

`result.json` 不用于表示 unresolved reconcile state。

### Crash-safe lifecycle state persistence

`state.json` 是 **authoritative orchestration lifecycle snapshot**，但不覆盖 backend/resource/effect 等下层 authoritative facts。它不是可随意重建的 cache。

所有 lifecycle mutation 必须：

```text
acquire per-capability transition.lock
re-read current durable state + relevant authoritative facts
write state.json.tmp
fsync(state.json.tmp)
atomic rename -> state.json
fsync(capability-job parent dir)
only then expose the new lifecycle state
```

规则：

- 禁止 in-place truncate/rewrite `state.json`；
- `state_revision` 每次 durable lifecycle transition 单调 +1；
- `transition.lock` 只是同一 capability job 内的短生命周期 consistency primitive，不是 resource ownership、不是 lease、不是 durable SOT；
- lifecycle/cancel/effect/result writers 使用 `LOCK_EX`；`status` 等需要 state/result 一致快照的 read-only path 使用 `LOCK_SH`；
- process crash 自动释放 `transition.lock`；恢复依据 durable files，不依据锁是否存在；
- 若 **durable valid `result.json` 不存在**，`state.json` parse/hash/schema corruption -> `STATE_STORE_CORRUPT`, `terminal=false`, `next_action=RECONCILE`；
- 若 durable valid `result.json` 已存在，final outcome authority 优先；`state.json` corruption 只能作为 diagnostic degradation，不能把已终结 job 退回 non-terminal；
- `status` 只能报告 corruption，不得偷偷重写 state；
- explicit `reconcile` 可根据 request/backend/resource/effect/result/journal 等 authoritative facts 生成新的 durable lifecycle snapshot；
- `state.json` durable publish 失败后，进程内 RAM 中“刚刚进入的新 lifecycle state”不得作为后续 correctness evidence。

这同时为 `cancel` 与 `EFFECT_BOUNDARY_CROSSED` 提供统一的 per-job 线性化区间。

### Cross-lock rule — no blocking nested acquisition

Rev3.6 同时存在两个完全不同的 flock：

```text
android-ui.lock   = global resource-claim mutation serialization
transition.lock   = one capability job's lifecycle-transition serialization
```

为避免 ABBA deadlock，v0.6 **禁止在持有其中一个锁时阻塞等待另一个锁**。

规范流程：

```text
resource cleanup/reacquire:
  acquire android-ui.lock
  re-read/mutate/fsync claim
  release android-ui.lock
  then, if lifecycle update is needed:
    acquire transition.lock
    re-read authoritative facts
    durable update state.json
    release transition.lock

cancel/effect-boundary:
  acquire transition.lock only
  validate current durable claim by exact resource_guard/read
  never acquire android-ui.lock inside transition critical section
```

若未来某实现确实需要同时保护两个域，必须重新版本化锁协议；Rev3.6 不允许临时选择任意 acquisition order。

> **No nested blocking acquisition between `android-ui.lock` and per-job `transition.lock`.**

## 13.3 Identity

`identity.json` 至少包含：

```json
{
  "capability_job_id": "cap-s-...",
  "submission_sha256": "...",
  "request_sha256": "...",
  "effective_policy_sha256": "...",
  "created_at": "..."
}
```

`request_sha256` / `effective_policy_sha256` 是 immutable contract identity。

# 14. Authority Matrix — One Fact, One Owner

| Fact | Authoritative durable record |
|---|---|
| transport submission -> capability job binding | `/opt/y700/runtime/submissions/<submission_sha256>.json` |
| capability request / immutable payload | capability `request.json` |
| request identity | `identity.json.request_sha256` |
| effective safety policy | `effective_policy.json` |
| capability orchestration state | capability `state.json` |
| approval for exact request | capability `approval.json` |
| backend binding | capability `backend.json` |
| backend execution status | backend durable job |
| Bridge root execution state | `/opt/y700/jobs/...` |
| UI workflow execution state | existing UI job durable files |
| Android automation revision/epoch | `device-state.json` |
| current android_ui semantic ownership | durable resource claim |
| verification evidence | capability `evidence/` |
| final capability business outcome | capability `result.json` |

重要规则：

> `state.json` 不能覆盖与 backend durable fact 矛盾的事实。

`/opt/y700/capability-jobs` 不是 `/opt/y700/jobs` 的替代物：

```text
Capability job = orchestration intent/outcome
Bridge job     = privileged execution fact
UI job         = UI workflow execution fact
```

---

# 15. Deterministic Backend Binding

这是 v0.6 release blocker。

## 15.1 Ordering

必须：

```text
1. derive deterministic backend_job_id
2. persist backend.json
3. fsync backend.json + parent dir
4. acquire declared resource claim (if required)
5. recheck expires_at / required pre-submit conditions
6. submit backend using exact backend_job_id
7. observe exact backend
```

不得：

```text
acquire a claim that requires an unknown backend_job_id
```

也不得：

```text
submit backend
-> later remember backend ID
```

“persist backend binding”只表示 durable execution intent，**不表示 backend 已启动**，因此可以安全地发生在 resource acquisition 之前。

## 15.2 backend.json

```json
{
  "backend_binding_version": 1,
  "capability_job_id": "cap-123",
  "backend_type": "ui_workflow",
  "backend_job_id": "cap-123--ui-01",
  "request_sha256": "...",
  "created_at": "..."
}
```

## 15.3 Top-level backend vs subordinate execution jobs

`backend.json` 绑定的是：

> **一个 capability invocation 的 top-level execution owner**

不是要求整个业务只能产生一个内部 sub-job。

例如：

```text
tiktok.publish capability
  ↓
top-level backend_type = publisher
top-level backend_job_id = deterministic publisher job
  ↓
publisher internally may run:
  prepare UI job
  precommit UI job
  commit-click UI job
  verification UI job
```

这些 subordinate UI jobs：

- 属于 top-level backend 的内部 execution facts；
- 必须可追踪到 `capability_job_id` / top-level `backend_job_id`；
- 所有 mutating sub-job 必须传播**创建/执行该 sub-job 时的 current exact `resource_guard`**；
- “exact”指 sub-job 对当前 ownership session 的 `claim_id + owner_id` 精确绑定，**不是**要求 capability 从首次 invoke 到所有 reconcile 永远只能使用第一个 claim ID；
- 不得被 Gateway 当成新的 top-level retry backend。

对于已有 workflow，如果已经存在稳定、immutable 的 publisher/media job identity，deterministic binding 可以复用该既有 ID；不强制为了命名漂亮而生成 `cap-...--publisher-01`。

“never allocate a second backend after uncertainty”指：

```text
never allocate a second top-level backend execution to repeat the same capability intent
```

不禁止一个已存在的 backend 内部正常产生多个明确语义的 sub-job。

### Subordinate provenance contract

所有由 capability top-level backend 创建的 subordinate execution job 必须携带 durable provenance：

```json
{
  "parent_capability_job_id": "cap-s-...",
  "top_backend_job_id": "cap-s-...--publisher",
  "subjob_id": "...",
  "subjob_role": "prepare|precommit|commit|verify|other-versioned-role",
  "resource_guard": {
    "resource": "android_ui",
    "claim_id": "...",
    "owner_id": "cap:..."
  }
}
```

规则：

1. mutating subordinate job 缺失 parent/top-backend/exact resource_guard -> `SUBORDINATE_BINDING_INVALID`，action attempts = 0；
2. observation-only subordinate job 仍记录 parent/top-backend provenance；
3. top-level backend 启动 subordinate job 前 durable append `SUBJOB_BOUND`；
4. subordinate completion 只是 execution evidence，不直接 terminalize capability business outcome；
5. orphan subordinate job 进入 reconcile/diagnostic，不得被误认成新的 top-level backend；
6. 若后续 `capctl reconcile` 重新 acquire `android_ui`，必须创建**新的 reconcile/verify subordinate job**并绑定新的 exact `claim_id`；旧 claim 下生成的 mutating sub-job 不得换绑/续跑；
7. top-level `backend_job_id` 与 `capability_job_id` 保持不变；新 claim 只代表新的 resource ownership session，不代表第二次 external-effect attempt；
8. capability journal durable 记录 `RESOURCE_REACQUIRED {prior_claim_id,new_claim_id,purpose}`，仅作 provenance；当前 ownership authority 仍只有 `android-ui.claim.json`。

## 15.4 Existing backend ID

如果 submit 返回 already exists：

Gateway 必须：

```text
lookup exact backend ID
-> compare immutable identity
```

结果：

- identity match -> attach/recover same backend；
- identity mismatch -> `JOB_CONTRACT_VIOLATION`；
- 不自动分配 `--ui-02`。

## 15.5 Crash recovery and pre-submit terminalization

任何 recovery 都只能查询：

```text
backend.json.backend_job_id
```

绝不“重新生成一个新的 backend”。

`backend.json` 的语义固定为：

> **immutable deterministic backend binding / derived execution intent**

它 **不表示 backend 已提交、已启动或仍需继续执行**。因此 `backend.json` 一旦 durable 后仍允许 job 在 backend submit 前进入合法 terminal outcome。`backend.json` 本身保持 immutable，**不得**通过在其中写 `ABORTED_BEFORE_SUBMIT` 等 mutable marker 来表达 lifecycle；pre-submit 终止由 `state.json`、journal、`cancel.json`、TTL facts 与最终 `result.json` 表达。

### Backend never-created positive-proof predicate

`backend not found` **不自动等于** `backend never-created`。只有同时满足以下条件才允许 positive-prove：

```text
1. deterministic backend_job_id known from durable backend.json
2. backend SOT / Bridge/UI job store permission + integrity checks HEALTHY
3. exact ID lookup covers every authoritative namespace required by that backend
   (e.g. staging/active/result/terminal archive as applicable)
4. no identity mismatch or partial/corrupt record exists
5. retention/GC contract guarantees该 exact backend record 若曾成功创建，此刻仍应可查询
6. no subordinate/job evidence proves execution already started
```

任何 lookup 路径为 `UNREADABLE / IO_ERROR / PERMISSION_ERROR / CORRUPT / retention-uncertain`：

```text
never-created proof = NOT ESTABLISHED
-> BACKEND_STATE_UNKNOWN / RECONCILE_REQUIRED
```

因此 reconciliation 不能把单纯 `ENOENT` 当作“从未提交”的充分证据。

如果 `backend.json` 已 durable，且 exact backend lookup **positive-proves backend 从未创建/提交**，explicit `reconcile` 按当前已 durable cause 终结：

```text
TTL/deadline already expired before submit -> EXPIRED
valid cancel requested before submit        -> CANCELLED
deterministic pre-submit validation/start failure -> FAILED
```

如果没有足够证据证明 backend never-created，或 backend existence/liveness 仍未知：

```text
RECONCILE_REQUIRED
```

不得把 unknown backend 当作 FAILED/EXPIRED/CANCELLED，也不得为了完成旧 intent 在 reconcile/status 中 submit backend。

因此 `BACKEND_BOUND` 只是“identity 已绑定”，不是 irreversible crossing point；Section 24.1 的 `EXPIRED/CANCELLED/FAILED` pre-submit transition 对 `backend.json` 已存在的 job 同样成立。

如用户在旧 job 已 final 后仍希望执行该业务 intent，创建新的 capability invocation。

# 16. Canonical android_ui Resource Arbiter

## 16.1 One canonical path

v0.6 复用现有生产路径：

```text
/opt/y700/runtime/android-ui.lock
```

不创建：

```text
/opt/y700/runtime/locks/android_ui.lock
```

避免双锁。

Durable claim：

```text
/opt/y700/runtime/android-ui.claim.json
```

## 16.2 Two-layer ownership

```text
flock(android-ui.lock)
=
atomic live claim mutation / process-level mutual exclusion

android-ui.claim.json
=
durable semantic ownership
```

`flock` 消失不代表 durable ownership 自动消失。

## 16.3 Claim content

```json
{
  "claim_version": 1,
  "claim_id": "ui-claim-...",
  "claim_generation": 1,
  "prior_claim_id": null,
  "resource": "android_ui",
  "owner_kind": "CAPABILITY",
  "owner_id": "cap:cap-123",
  "capability_job_id": "cap-123",
  "backend_type": "publisher",
  "backend_job_id": "cap-123--publisher",
  "request_sha256": "...",
  "owner": {
    "boot_id": "...",
    "pid": 1234,
    "proc_start_ticks": 56789
  },
  "acquired_at": "..."
}
```

`claim_id` 是一次 **resource ownership session identity**，不是 capability-lifetime identity。首次 acquire `claim_generation=1, prior_claim_id=null`；同一 capability 在 explicit reconcile 中合法 reacquire 时使用新的 `claim_id`、递增 generation，并把上一个 claim ID 仅作为 provenance 写入 `prior_claim_id`/journal。

`boot_id + pid + proc_start_ticks` 是 process identity evidence，用于降低 Linux PID reuse 误判。

**v0.6 不把 heartbeat timeout 设计成 resource lease。**

`capctl doctor` / explicit reconcile 可以读取：

```text
/proc identity
backend heartbeat age
backend durable state
claim age
```

作为 liveness evidence，但：

```text
heartbeat stale
PID missing
coordinator exit
claim age exceeded
```

任何单一信号都**不得自动授权 claim release**。

claim 本身不需要周期性 heartbeat 写入，也没有 `lease_expires_at`。


字段兼容规则：

```text
owner_kind = CAPABILITY
-> capability_job_id REQUIRED
-> request_sha256 = capability request identity

owner_kind = LEGACY
-> capability_job_id MAY be null
-> owner_id / backend_job_id MUST still identify the existing production workflow
-> request_sha256 uses the legacy/backend immutable request identity when available
```

因此 shared arbiter 可以同时覆盖 migration 期间的 legacy top-level controller 与 Gateway，而不伪造 capability job。

**claim 不保存 `effect_boundary_crossed`。**

唯一 authority：

```text
android-ui.claim.json
= WHO currently owns the UI resource

capability/effect-boundary.json
= whether unsafe business boundary was crossed
```

同一个 fact 不重复存两份。

## 16.4 Acquisition

前提：

```text
backend.json already exists and is fsynced
```

进程拿到 `flock` 后 **仍不能直接假定资源可用**。

必须读取 durable claim。

若无 claim：

```text
derive ownership-session lineage from capability/legacy durable journal
create new unique claim_id
initial acquire: prior_claim_id=null, claim_generation=1
explicit same-capability reconcile reacquire: prior_claim_id=<last released claim>, claim_generation=N+1
write claim to temp
fsync(temp)
atomic rename -> android-ui.claim.json
fsync(runtime parent dir)
durable append RESOURCE_ACQUIRED / RESOURCE_REACQUIRED
only then proceed
```

`claim_generation/prior_claim_id` 是 audit/provenance，不替代 `claim_id` 的 exact ownership authority；若 lineage journal integrity 自身损坏，按 runtime/state integrity failure fail closed，不通过猜测生成 lineage。

backend submit 必须发生在 durable claim 完成之后。

若 claim 属于本次合法 recovery：

```text
inspect exact backend/resource facts
continue only through explicit reconcile rules
```

若 claim 属于其他 job：

```text
inspect exact owner/backend durable state
```

只有在能证明旧 backend 已安全终止、不会继续操作 UI 时，explicit reconcile 才可清理旧 claim。

如果 backend liveness 仍未知：

```text
RESOURCE_RECONCILE_REQUIRED
```

不得因旧 coordinator PID 消失而直接抢占。

Claim cleanup 也必须 durable 且在 canonical flock 保护下：

```text
prove backend/UI mutator stopped
-> hold/acquire canonical flock
-> unlink android-ui.claim.json
-> fsync(runtime parent dir)
-> release flock
```

不得先释放 ownership、后判断 backend 是否仍可能运行。

## 16.5 Core ownership assertion — enforce, do not merely document

所有 protocol v2 `LOCAL_UI_MUTATION` / `EXTERNAL_COMMIT` action 必须携带：

```json
{
  "resource_guard": {
    "resource": "android_ui",
    "claim_id": "ui-claim-...",
    "owner_id": "cap:cap-123"
  }
}
```

Core 在 **每次 mutation、且在 `MUTATION_PREPARED` 之前** 校验：

```text
current durable claim exists
claim.resource == android_ui
claim.claim_id == request.resource_guard.claim_id
claim.owner_id == request.resource_guard.owner_id
```

否则：

```text
RESOURCE_OWNERSHIP_REQUIRED
or
RESOURCE_OWNERSHIP_MISMATCH
action_attempts = 0
```

Observation-only action：

```text
observe / find / screenshot / waitStable ...
```

不要求 UI ownership。

这不是第二把锁：

```text
top-level controller/Gateway
= acquire ownership

Core
= assert ownership
```

从而防止 controller 直接调用 `automation/ui_job.py` 绕过 arbiter。

## 16.6 Coordinator crash and resource release

Coordinator crash 导致 kernel flock release **不代表 resource free**。

如果 backend：

```text
running
or liveness unknown
```

durable claim 保留，其他 mutating workflow 被阻止。

`capctl reconcile` 是 normal recovery mutator；它**不需要人工 ADMIN 批准**才能做确定性安全清理。若同时满足以下 positive-proof 条件：

```text
1. exact claim_id still matches the durable claim being reconciled
2. exact owner process identity is DEAD / PID_REUSED / ZOMBIE
   (or the owner never started, as positively proven)
3. exact backend durable facts say STOPPED/TERMINAL or backend is positively proven never-created
4. no subordinate process/job with the same top_backend_job_id can still mutate android_ui
5. reconciler holds canonical flock while re-reading the claim and performing cleanup
```

`STOPPED`（Linux `T/t`）**不属于** positive stop proof：它仍可能被恢复执行；只有 `ZOMBIE`（`Z`）、DEAD、PID_REUSED 等不可继续执行的 exact process evidence 才可进入上述 proof。若必须处理 STOPPED/HUNG owner，先执行显式 exact-process termination/ADMIN recovery，再重新建立证据。

则 `capctl reconcile` **MUST be authorized** to：

```text
unlink android-ui.claim.json
fsync(runtime parent dir)
record RESOURCE_RELEASED_BY_RECONCILE
```

无需 `admin force-reset`，也不得无限保持 `RESOURCE_RECONCILE_REQUIRED`。

若上述任一项为 `UNKNOWN / UNREADABLE / HUNG`，或无法排除仍有 UI mutator，则保留 claim；只有这种“无法 positive-prove stop”的场景才进入 operator/ADMIN force-reset consideration。

资源释放判断与业务 effect boundary 正交：即使 `EFFECT_BOUNDARY_CROSSED` 已存在，只要所有 UI mutator 已 positive-proven stopped，仍可释放 `android_ui`；此时 capability business outcome 继续保持 `RECONCILE_REQUIRED`。

这是两个不同问题：

```text
resource ownership ambiguity
!=
business outcome ambiguity
```

例如 TikTok Publish 已发送但最终是否出现在 Profile 尚不确定时：

- 正常 foreground path 若马上进行 UI-based Profile verification，可继续持有**同一 claim**直到该 verifier 完成/阻塞；
- 若 coordinator crash、verification 被延期、或 backend 已终止且不再需要当前 UI session，则 UI resource 可以安全释放；
- capability 仍可保持 `RECONCILE_REQUIRED`；
- 后续 `capctl reconcile` 需要 UI 时重新正常 acquire **新 claim_id / next claim_generation**；
- 只允许创建绑定该新 exact claim 的新 reconcile/verification subordinate job；旧 claim 下的 sub-job 全部保持 stale，不得 rebind；
- 不允许再次发送 Publish side effect。

## 16.7 Legacy migration rule

Gateway mutating UI capability 启用前：

> 所有 production mutating UI paths 必须参加同一个 `android_ui` ownership protocol。

允许 legacy entrypoint 保留，但它必须：

1. 通过 shared arbiter acquire claim；
2. 将 exact `claim_id/owner_id` 传入 UI Core；
3. Core mutation boundary 校验 ownership。

不允许：

```text
legacy lock A
+
gateway lock B
```

也不允许：

```text
direct mutating ui_job
without resource_guard
```

### No nested re-acquisition

现有 TikTok controller 已经存在内部 `ui_lease()`。

v0.6 migration 必须避免：

```text
Gateway acquires android_ui
-> Publisher/Controller opens same canonical lock again
-> nested/reentrant flock ambiguity or deadlock
```

统一规则：

```text
top-level production entrypoint acquires exactly once
downstream components receive claim_id/owner_id
downstream Core asserts ownership
downstream Adapter/Controller MUST NOT reacquire
```

Legacy direct entrypoint：

```text
legacy top-level controller
-> shared arbiter acquire once with owner_kind=LEGACY
-> bind its existing backend/job identity in the claim
-> pass resource_guard downward
```

Gateway entrypoint：

```text
Gateway
-> shared arbiter acquire once
-> pass resource_guard through Publisher/Adapter to every mutating UI sub-job
```

因此现有 `ui_lease()` 需要在 migration 中被重构为 shared-arbiter entrypoint / claim-aware wrapper，而不是和 Gateway lock 并存。

## 16.8 Admin bypass

Debug/admin bypass 如果保留：

- 必须显式；
- 不属于 BUSINESS safety guarantee；
- 不得成为 production path。

任何 ADMIN 操作如果可能改变 Android/UI/global device state，或无法静态证明 observation-only，则必须在 dispatch **之前** durable bump `state_epoch`。

如果 epoch bump 不能 durable 完成：

```text
STATE_INTEGRITY_UNAVAILABLE
ADMIN operation MUST NOT execute
```

caller 不得关闭该规则。Generic `android.root.exec` 默认 `state_effect=UNKNOWN`，因此默认 bump epoch before dispatch。

### Emergency UI runtime reset

允许显式 ADMIN escape hatch：

```text
capctl admin force-reset-ui-runtime --claim-id <exact-id> --reason <text>
```

必须：

```text
verify exact claim
durable bump state_epoch
durable ADMIN_FORCE_RESET_REQUESTED audit
best-effort stop exact backend/process group
re-check exact process/backend/subordinate-job evidence
establish UI-mutation quiescence
only then:
  hold canonical flock
  re-read exact claim
  unlink claim
  fsync parent dir
  durable ADMIN_FORCE_RESET_COMPLETED audit
if a capability job exists: leave its business outcome RECONCILE_REQUIRED
if owner_kind=LEGACY: record resource-recovery audit only; do not invent a capability outcome
never auto-replay prior effect
```

**ADMIN 也不能越过 one-mutator safety invariant。**

如果 stop 是 best-effort 且 quiescence **无法 positive-prove**：

```text
DEVICE_UI_RUNTIME_UNSAFE
claim MUST remain
new mutating BUSINESS work MUST remain blocked
recommended_action = REBOOT_OR_REPAIR_RUNTIME
```

允许 operator 通过完整 Android/runtime reboot 建立“旧 mutator 不可能继续执行”的新证据，再执行 normal reconcile/ADMIN cleanup。

因此 `force-reset-ui-runtime` 的语义不是“无条件删锁”，而是：

> **尝试强制终止旧执行并重建未来 mutation 的安全起点；只有 quiescence 已证明后才可释放 claim。**

它从不证明旧业务 outcome。

# 17. Device State Integrity Layer

## 17.1 Runtime state

```text
/opt/y700/runtime/ui-state/
└── device-state.json
```

权限：

```text
directory 0700
file      0600
```

不再创建单独 `mutation.lock`。

## 17.2 state_epoch

代表当前 state-integrity epoch。

在无法安全继承 revision continuity 时变化，例如：

- first initialization；
- explicit state reset；
- corrupted ledger recovery；
- admin bypass 后无法证明 continuity。

不要因为每次 Android reboot 就机械变化，除非 implementation 无法证明 ledger continuity；具体规则必须 deterministic 并测试。

## 17.3 revision

单调递增：

```text
每个成功 durable commit 的 Android UI mutation +1
observe-only 不增加
```

revision 发现的是：

```text
automation-created state drift
```

不是 human touch。

## 17.4 semantic state_hash

```text
SHA-256(canonical semantic snapshot)
```

用于发现：

```text
user touch
system dialog
foreground/activity changes
element/property changes
```

不 hash screenshot bytes，不 hash full raw UI XML。

## 17.5 state_token

```json
{
  "token_version": 1,
  "state_epoch": "...",
  "revision": 42,
  "fingerprint_version": "semantic-v1",
  "fingerprint_profile_id": "settings.switch.element-base.v1",
  "scope": "ELEMENT",
  "state_hash": "sha256:...",
  "observed_at": "...",
  "observed_boot_id": "...",
  "observed_boottime_ms": 123456,
  "max_age_ms": 30000
}
```

Age：

```text
current_boot_id == observed_boot_id
age_ms = CLOCK_BOOTTIME_now - observed_boottime_ms
age_ms <= max_age_ms
```

`observed_at` 只用于审计。boot mismatch：

```text
STATE_TOKEN_BOOT_MISMATCH
action_attempts = 0
```

`max_age_ms=30000` 是 Core v0.6 initial maximum/default；静态 capability/workflow contract 只能收紧：

```text
0 < capability_max_age_ms <= 30000
```

caller 不能放宽。未来需要 >30s 必须 versioned policy change + 实测评审。

### Suspend / Deep Sleep semantics

`CLOCK_BOOTTIME` **故意包含 Android/Linux suspend 时间**。这是 safety choice，不是计时误差：Y700 熄屏/休眠期间 foreground、window、keyguard、process 或 app state 可能发生变化，因此 suspend 10 分钟后旧 30s token 应立即失效。

```text
resume after token age > max_age_ms
-> STATE_TOKEN_EXPIRED
-> action_attempts = 0
-> no mutation replay
```

若 workflow 使用 `AUTO` guard，Coordinator/Core 可以在 mutation 前重新执行 fresh observation；fresh observation 必须重新经过 screen/keyguard/foreground/overlay preflight 并签发新的 token，然后**重新评估当前 action preconditions**。不能仅因为“旧 token 是 suspend 导致过期”而直接复用旧 mutation intent。

因此 v0.6 明确不使用 suspend-pausing `CLOCK_MONOTONIC` 来延长 state-token validity。

`fingerprint_profile_id` 必须与当前 versioned fingerprint contract exact match；profile mismatch：

```text
STATE_TOKEN_PROFILE_MISMATCH
action_attempts = 0
```

token 不是 credential。

---

# 18. Semantic Fingerprint

## 18.1 FOREGROUND

至少：

```text
screen/keyguard state
foreground package
foreground activity
```

## 18.2 ELEMENT

FOREGROUND +

```text
selector contract
cardinality
stable semantic element attributes
enabled
checked
selected
clickable
text/content-desc when relevant
```

## 18.3 PROPERTY

ELEMENT +

workflow 明确声明的 business-relevant property。

例如：

```text
dark_mode_white_check.checked
visibility = PUBLIC
Publish control semantic identity
```

## 18.4 Canonicalization — Allowlist First

`semantic-v1` 采用 **field allowlist**，不是“先 hash 整棵 UI tree，再维护越来越长的 ignore list”。

原则：

```text
only explicitly declared semantic fields enter the hash
everything else is excluded by default
```

基础规范：

- UTF-8；
- sorted JSON keys；
- deterministic null/missing rule；
- booleans normalized；
- `FOREGROUND` 只包含明确声明的 screen/keyguard/package/activity 字段；
- `ELEMENT` 只包含 selector identity、cardinality 与 contract 允许的稳定语义属性；
- `text/content-desc` 只有在 selector/property contract 声明 relevant 时才进入；
- `PROPERTY` 只加入 workflow/capability 明确声明的 watched property；
- timestamps、revision、token id、event counters 不进入 hash；
- screenshot bytes 不进入；
- absolute bounds / animation frame / transient coordinates 默认不进入；
- system clock / battery percentage / transient telemetry 不进入，除非 capability 明确声明为 watched business property；
- 未列入 allowlist 的 UI/tree attribute 默认不进入；
- deterministic test vectors 必须存在。

目标不是“维护动态字段黑名单”，而是从源头只 hash 对当前 mutation 安全判断有意义的 semantic facts。

## 18.5 Fingerprint Scope Contract

每个 mutation guard 必须能够回答：

```text
which semantic facts make this action safe to execute?
```

禁止为了“更保险”把完整 UI XML、所有 node attributes 或 screenshot hash 纳入 authoritative fingerprint。

新增 capability 若需要新字段，必须显式扩展该 capability/workflow 的 fingerprint scope，并增加稳定性与 drift-detection test。

### 18.5.1 Versioned fingerprint profile

每个 guarded mutation 必须解析到一个 versioned static profile：

```json
{
  "fingerprint_profile_id": "settings.switch.element-base.v1",
  "scope": "ELEMENT",
  "watch_element_optional": [],
  "watch_properties": []
}
```

若业务确实需要 text/content-desc 参与安全判断：

```json
{
  "fingerprint_profile_id": "tiktok.publish-control.v1",
  "scope": "ELEMENT",
  "watch_element_optional": ["text", "content_desc"],
  "watch_properties": ["visibility"]
}
```

规则：

- profile 来自 versioned workflow/adapter contract；caller 不能临时增加/删除 watched field 来改变 safety；
- `fingerprint_profile_id` 必须进入 state token，并在 compare-before-mutate 时 exact-match；
- profile 不是 dynamic `node-health` 内容，也不是 capability caller policy override；
- `watch_element_optional` v0.6 只允许 `text|content_desc`；
- `watch_properties` 只能引用 capability/workflow 已注册的 scalar property allowlist。

## 18.6 Global Blocking Overlay Guard

仅靠 `foreground.package + foreground.activity` 不足以证明 UI 可安全点击，因为 Android 可以在 Activity 不变时出现：

```text
runtime permission dialog
system confirmation dialog
app modal dialog
full/partial-screen blocking overlay
another focusable top-level window
```

因此所有 protocol-v2 UI mutation 在 final compare-before-mutate 阶段必须计算：

```text
screen.blocking_overlay_present
screen.blocking_overlay_owner_package
screen.blocking_overlay_class
```

其中：

```text
blocking_overlay_present
```

是 mandatory global semantic fact。

判定原则：

1. Core 基于当前 top-level Accessibility/UiAutomation window/root facts 做 **classified candidate evaluation**，禁止使用“只要出现第二个 visible window 就 blocking”的简化算法；
2. 一个 candidate 只有在能证明其对当前 action 构成输入/焦点/可交互区域阻断时才置 `blocking_overlay_present=true`。最小证据可来自：unexpected focused/active application/system window、已知 modal/system-dialog signature、或可交互 root 明确覆盖/取代 expected target surface；
3. `TYPE_INPUT_METHOD`/IME **仅因存在本身不算 blocker**；正常 text-input 流程允许 IME 存在，但 target/foreground/focus 仍必须满足 action contract；
4. transient Toast/notification/non-focusable system window **仅因存在本身不算 blocker**；
5. `TYPE_ACCESSIBILITY_OVERLAY` 不做 blanket ignore：只有 versioned allowlist 中已知、non-focus-stealing/non-intercepting 的 overlay 可忽略；未知或 focus/input-intercepting accessibility overlay 仍 fail closed；
6. capability/workflow 可声明明确允许的 expected dialog/window signature；allowlist 必须 versioned、静态、最小化，不能由 caller 临时放宽；
7. 若检测到未被当前 action contract 显式允许的 blocking overlay：

```text
UNEXPECTED_BLOCKING_OVERLAY
action_attempts = 0
```

8. 该检查在 mutation dispatch 前 JIT 执行；不能只依赖较早 token snapshot；
9. app 内自定义 modal 如果无法作为独立 top-level window识别，workflow 必须通过 versioned `blocking_selector`/watched property 纳入 guard；
10. overlay detector 是 safety precondition，不依赖 screenshot pixel hash。

当没有被分类为 blocking 的 candidate 时：

```text
screen.blocking_overlay_present = false
screen.blocking_overlay_owner_package = null
screen.blocking_overlay_class = null
```

只有最终被选为 authoritative blocker 的 candidate 才填 owner/class；IME/Toast 等被规则排除的 window 不得污染 semantic hash。

这不是“把所有 window 属性都 hash 进去”。Rev3.5 仍坚持 allowlist-first，只增加少量全局 safety facts。

## 18.7 semantic-v1 Exact Canonical Schema

Authoritative allowlist：

```text
screen.interactive
screen.keyguard_locked
screen.blocking_overlay_present
screen.blocking_overlay_owner_package
screen.blocking_overlay_class
foreground.package
foreground.activity
selector.resource_id
selector.class_name
selector.package
selector.text
selector.content_desc
selector.clickable
selector.enabled
selector.checked
selector.selected
cardinality
element.enabled
element.checked
element.selected
element.clickable
element.text
element.content_desc
property.<capability-declared-scalar-name>
```

规则：

- `selector.*` 只序列化 action **实际 predicates**；因此 selector 使用 `text/content_desc` 约束时它们必须进入，否则强制 omit；
- `element.enabled/checked/selected/clickable` 是 `ELEMENT` base semantic fields，按 profile/base contract 采样；
- `element.text` / `element.content_desc` **只有**在 resolved `fingerprint_profile.watch_element_optional` 显式列出时进入；即使 runtime node 实际存在非空 text/content-desc，若 profile 未 watch，序列化器也必须从 object 中强制 omit；
- watched optional field：accessor 返回 `null` -> JSON `null`；返回 empty string -> `""`；返回非空 string -> Unicode NFC string。三者都与“unwatched -> omit key”严格区分；
- watched field 无法可靠读取 -> `STATE_FINGERPRINT_UNAVAILABLE`, action attempts = 0；不得悄悄 omit 后继续；
- `property.*` 由 versioned profile 声明且仅允许 scalar/null；
- bounds/node order/screenshot/timestamp/battery/clock/animation/raw XML 禁止进入 authoritative hash。

这使 Appendix A Vector 2 的 omission 成为规范：该 profile 未 watch `element.text/content_desc`，因此无论真实 Switch node 是否存在文字，这两个 key 都必须被删除，不是写 `null`。

Canonicalization：

```text
strings -> Unicode NFC
booleans -> JSON true/false
integers -> base-10
null -> JSON null
floats -> forbidden
missing -> omit key
UTF-8
sorted object keys
no insignificant whitespace
arrays forbidden
```

Hash：

```text
SHA-256(canonical_utf8_bytes)
"sha256:" + lowercase hex
```

Fixed vector 1（token `fingerprint_profile_id=semantic-v1.foreground-base.v1`；profile ID 不进入以下 canonical JSON bytes，但 compare 时必须 exact-match）：

```json
{"fingerprint_version":"semantic-v1","foreground":{"activity":"com.android.settings.Settings","package":"com.android.settings"},"scope":"FOREGROUND","screen":{"blocking_overlay_class":null,"blocking_overlay_owner_package":null,"blocking_overlay_present":false,"interactive":true,"keyguard_locked":false}}
```

```text
sha256:074e74b0f725954b789fea7d905715c7e096c4ab159029a1c6c8ef8a6b610b66
```

Fixed vector 2（token `fingerprint_profile_id=settings.switch.element-base.v1`；该 profile 不 watch `element.text/content_desc`）：

```json
{"cardinality":1,"element":{"checked":true,"clickable":true,"enabled":true,"selected":false},"fingerprint_version":"semantic-v1","foreground":{"activity":"com.android.settings.Settings","package":"com.android.settings"},"scope":"ELEMENT","screen":{"blocking_overlay_class":null,"blocking_overlay_owner_package":null,"blocking_overlay_present":false,"interactive":true,"keyguard_locked":false},"selector":{"resource_id":"android:id/switch_widget"}}
```

```text
sha256:6bab7e2cd22bb7e2804f75638edfda2546f73802003c57fde3ecbdd322f32fd4
```

所有 fingerprint producer/consumer 必须通过固定向量 regression。

---

# 19. Compare-Before-Mutate

## 19.1 External observe -> later act

使用：

```text
state_guard = TOKEN
```

mutation 必须同时满足：

```text
epoch match
revision match
fingerprint_version match
fingerprint_profile_id exact match
semantic hash match
token not expired
```

否则：

```text
STALE_STATE_EPOCH
STALE_STATE_REVISION
STALE_STATE_HASH
STATE_TOKEN_PROFILE_MISMATCH
STATE_TOKEN_EXPIRED
```

action attempt count = 0。

## 19.2 Internal workflow

预定义 workflow 使用：

```json
{"state_guard":{"mode":"AUTO"}}
```

AUTO 不代表跳过 guard。

它要求 runtime 在 mutation boundary：

```text
observe semantic state
-> create internal token
-> validate
-> prepare mutation
-> dispatch
```

并把 token / hash 写入 action journal。

## 19.3 Missing guard

Protocol v2 mutation 缺 guard：

```text
UNGUARDED_MUTATION_NOT_ALLOWED
```

不 fallback 到 v1。

---

# 20. UI Mutation Journal Contract

上一版 State-Integrity 设计中的全局 `pending-mutation.json` 已收敛掉。

原因：

- UI job 已经有 durable journal；
- 单独 pending file 会形成第二事务系统；
- MSA 应复用已有 job durability。

## 20.1 Before mutation

前置顺序：

```text
resource ownership assertion PASS
state guard PASS
```

然后现有 UI job `journal.jsonl` append：

```json
{
  "phase": "MUTATION_PREPARED",
  "action_id": "...",
  "action_index": 3,
  "mutation_class": "LOCAL_UI_MUTATION",
  "state_epoch": "...",
  "revision_before": 42,
  "fingerprint_version": "semantic-v1",
  "fingerprint_profile_id": "settings.switch.element-base.v1",
  "state_hash_before": "...",
  "resource_claim_id": "ui-claim-...",
  "request_sha256": "...",
  "timestamp": "..."
}
```

必须：

```text
append
flush
fsync
```

然后才 dispatch Android mutation。

## 20.2 Successful mutation — ordering is safety-critical

postcondition PASS 后，顺序固定为：

```text
1. atomic write device-state.json with revision=N+1
2. fsync device-state.json + parent dir
3. append MUTATION_COMMITTED
4. flush + fsync journal
```

不得反过来。

理由：

如果：

```text
revision=N+1 durable
-> crash before MUTATION_COMMITTED
```

旧 token 已失效；job 可进入 reconcile，安全。

如果反过来：

```text
MUTATION_COMMITTED durable
-> crash before revision advances
```

旧 token 可能错误保持有效，因此禁止。

例：

```json
{
  "phase": "MUTATION_COMMITTED",
  "action_id": "...",
  "revision_before": 42,
  "revision_after": 43,
  "postcondition": "PASS",
  "timestamp": "..."
}
```

## 20.3 Crash semantics

出现：

```text
MUTATION_PREPARED
without
MUTATION_COMMITTED
```

不代表 action 未发生。

恢复必须：

```text
inspect action semantics
+ current revision/epoch
+ actual Android semantic state
+ postcondition evidence
```

不能证明：

```text
RECONCILE_REQUIRED
```

不得 blind replay。

# 21. Capability Replay Policy

保留原始 Gateway PRD 的三值 contract，但明确它是 **capability-level policy**：

```text
SAFE
IDEMPOTENT
NEVER
```

### SAFE

仅用于可证明无 external side effect 的 capability，例如 read-only observation。

### IDEMPOTENT

必须由 capability definition 明确证明业务幂等语义。

Core/Gateway：

```text
must not infer idempotency from payload equality
```

v0.6 不提供 cross-request idempotency index；因此 `IDEMPOTENT` 只描述 capability recovery policy，不自动提供 arbitrary duplicate-request dedupe。

### NEVER

外部 side effect、不可逆动作或无法证明业务幂等的 capability。

`tiktok.publish`：

```text
replay = NEVER
```

`NEVER` 与 `EFFECT_BOUNDARY_CROSSED` 配合：

- boundary 前是否可恢复/重新 submit，必须由 exact backend evidence 决定；
- boundary 后禁止自动 external-effect replay。

## 21.1 Dependency Failure / Fallback Eligibility

Rev3.5 不新增 generic failover engine，而是把 fallback 判断绑定到已有 durable facts。

决策顺序：

```text
1. effect boundary crossed OR backend/mutation may have occurred?
   -> EXCLUSIVE_OR_UNCERTAIN
   -> no alternate execution; RECONCILE_REQUIRED/status path

2. mandatory safety dependency unavailable/incompatible?
   -> fail closed before new side effect
   -> CAPABILITY_NOT_READY / RUNTIME_CONTRACT_MISMATCH

3. dependency is explicitly non-safety optional and semantics unchanged?
   -> OPTIONAL_AUXILIARY
   -> continue DEGRADED; journal exact reason

4. state can be deterministically reconstructed before effect?
   -> RECONSTRUCTIBLE_PRE_EFFECT
   -> re-observe/reinitialize under same job/backend identity, bounded

5. otherwise
   -> no fallback
```

`RECONSTRUCTIBLE_PRE_EFFECT` 的典型合法动作是重新 observe 当前 UI、重新生成 state token、重新做 capability preflight；它不是重新创建第二个 top-level backend。

v0.6 不要求在 Catalog 建 generic dependency DAG。shipping adapter/Core 只需对实际 dependency 明确 mandatory/optional，并通过 acceptance tests 证明其 fallback class。

# 22. Side-Effect Taxonomy

必须把两个维度分开。

## 22.1 Mutation class

```text
OBSERVE_ONLY
LOCAL_UI_MUTATION
EXTERNAL_COMMIT
```

决定：

- 是否需要 `resource_guard`；
- 是否需要 state guard；
- 是否增加 revision；
- 是否需要 capability effect boundary。

**v0.5 的 `SAFE_ACTIONS` 概念必须在 v0.6 实现时拆分。**

特别是：

| Action | Mutation class | Replay/recovery property |
|---|---|---|
| `observe` / `find` / `findAll` / `waitStable` | `OBSERVE_ONLY` | safe observation retry |
| `screenshot` / `assert` / `waitFor` | `OBSERVE_ONLY` | safe observation retry |
| `pressHome` | `LOCAL_UI_MUTATION` | usually repeatable/reversible, but still mutates state |
| `pressBack` | `LOCAL_UI_MUTATION` | context-dependent/reversible, but still mutates state |
| `click` / `inputText` / `swipe` / `scroll` | `LOCAL_UI_MUTATION` unless explicitly part of external commit | action-specific recovery |
| final Publish click | `EXTERNAL_COMMIT` | never auto replay |

因此：

```text
repeatable
!=
OBSERVE_ONLY
```

`pressHome` / `pressBack` 成功后必须遵守 mutation journal/revision rules。

## 22.2 Replay/recovery policy

独立描述：

```text
SAFE_OBSERVE_RETRY
SAFE_IDEMPOTENT
RECONCILE_BEFORE_RETRY
NEVER_AUTO_REPLAY
```

Replay property 不能覆盖 mutation classification。

例如：

```text
pressHome
```

即使通常可安全重复，也必须：

```text
own android_ui
guard current state
MUTATION_PREPARED
mutate
advance revision
MUTATION_COMMITTED
```

这样旧 state token 不会因为“可重复”而继续有效。

# 23. Unsafe Effect Boundary

## 23.1 Terminology

禁止 generic 状态：

```text
SIDE_EFFECT_APPLIED
```

因为 runtime 往往无法证明 side effect 已发生。

采用：

```text
EFFECT_BOUNDARY_CROSSED
```

它表示：

> 从这个 durable point 开始，系统不再拥有自动重复外部 side effect 的权限。

## 23.2 Ordering

对于 `EXTERNAL_COMMIT`：

```text
acquire capability transition.lock
re-read state.json / cancel.json / effect-boundary.json
all preconditions PASS
exact request / policy identity PASS
approval valid
state guard PASS
android_ui ownership valid
app_ui_contract_match PASS when capability declares app_ui_contract
backend identity known
NO durable cancel intent that won the transition race
        ↓
write capability/effect-boundary.json
fsync file + parent dir
durable state transition -> RUNNING_UNSAFE
release transition.lock
        ↓
write/advance backend-specific unsafe marker if it already exists
(e.g. TikTok Publisher COMMITTING)
fsync
        ↓
only then dispatch first non-safe external effect
```

统一安全原则：

> **upper-layer safety boundary first, lower-layer legacy unsafe marker second, actual external side effect third.**

### Cancel / unsafe-boundary linearization

`capctl cancel` 与 `EFFECT_BOUNDARY_CROSSED` 必须在同一 per-capability `transition.lock` 下竞争。

规则：

```text
cancel acquires transition.lock first
-> re-read effect-boundary absent
-> durable cancel.json
-> durable state -> CANCELLING (or pre-submit cancellation path)
-> release lock
-> effect-boundary writer later sees cancel intent and MUST NOT cross

effect-boundary writer acquires transition.lock first
-> final checks PASS
-> durable effect-boundary.json
-> durable RUNNING_UNSAFE state
-> release lock
-> later cancel cannot convert business outcome to CANCELLED
```

如果 cancel 在 boundary 后到达：

```text
CANCEL_AFTER_EFFECT_BOUNDARY
terminal=false
business effect is not undone
normal flow continues VERIFYING / RECONCILE_REQUIRED as evidence dictates
```

cancel 可以请求停止**后续非必要工作**，但不得把已经消费 approval / crossed unsafe boundary 的 job 伪装成 `CANCELLED`。

crash 恢复只读取 durable winner：

```text
cancel.json durable && effect-boundary absent -> cancel won
effect-boundary durable                     -> effect won
neither durable                             -> re-evaluate under transition.lock
```

不存在“依据谁先返回 HTTP/CLI response”判断 winner。

这样最坏的 crash 只会造成“保守进入 reconcile”，不会造成 Gateway 错误认为仍在 safe zone。

## 23.3 effect-boundary.json — single authority for unsafe boundary

```json
{
  "effect_boundary_version": 1,
  "capability_job_id": "cap-123",
  "capability": "tiktok.publish",
  "request_sha256": "...",
  "backend_job_id": "cap-123--ui-01",
  "approval_sha256": "...",
  "approval_nonce": "...",
  "crossed_at": "...",
  "boundary": "before_final_publish",
  "revision": 57,
  "fingerprint_version": "semantic-v1",
  "fingerprint_profile_id": "tiktok.publish-control.v1",
  "state_hash": "..."
}
```

对于 `approval=REQUIRED`：

```text
effect-boundary.json exists
=
the exact single-use approval has been consumed for this capability job
```

不再单独建立第二个 mutable “approval used” store。

## 23.4 TikTok integration ordering

现有 Publisher 已有：

```text
READY_TO_COMMIT
-> COMMITTING
-> exactly one Publish click
```

v0.6 通过现有 `before_irreversible` hook 收敛为：

```text
precommit semantic checks PASS
↓
Gateway/capability boundary writer:
    effect-boundary.json fsync
↓
Publisher:
    COMMITTING fsync
↓
Controller:
    exactly one Publish click
```

不得反过来。

## 23.5 After boundary

从 `effect-boundary.json` durable 起：

> **该 durable boundary 同时是本次 external attempt 的 cancellation cutoff：后到的 cancel 不再拥有把本次业务尝试转为 CANCELLED 的权限。**

```text
no automatic external-effect retry
```

Crash / verifier infrastructure error / unknown outcome：

```text
RECONCILE_REQUIRED
```

即使 verifier 后续给出：

```text
OUTCOME_NOT_ACHIEVED
```

也**不自动恢复 retry permission**。

对于：

```text
replay=NEVER
approval.single_use=true
```

再次执行 external effect 必须：

```text
new capability job
+
new exact-request approval / newly authorized attempt
```

旧 approval 不可重用。

# 24. Capability Lifecycle

由于 v0.6 没有 daemon / scheduler，不定义无人负责的长期 `QUEUED`。

## 24.1 Mutating BUSINESS capability

```text
CREATED
  ├── expires before backend submit -> EXPIRED
  ↓
BACKEND_BOUND
  ├── expires before submit -> EXPIRED
  ├── valid cancel before submit -> CANCELLED
  ├── deterministic pre-submit failure -> FAILED
  ↓
WAITING_RESOURCE
  ├── expires while waiting -> EXPIRED
  ├── valid cancel before submit -> CANCELLED
  ├── deterministic pre-submit failure -> FAILED
  ↓
RESOURCE_ACQUIRED
  ├── expires before backend submit -> EXPIRED
  ├── valid cancel before submit -> CANCELLED
  ├── deterministic pre-submit failure -> FAILED
  ↓
RUNNING_SAFE
  ├── pre-effect confirmed failure -> FAILED
  ├── cancel wins transition race -> CANCELLING
  │       ├── safe-stop proof -> CANCELLED
  │       └── stop/outcome unknown -> RECONCILE_REQUIRED
  │
  └── effect-boundary wins transition race -> EFFECT_BOUNDARY_CROSSED
          ↓
      RUNNING_UNSAFE
          ↓
      VERIFYING
        ├── VERIFIED
        ├── OUTCOME_NOT_ACHIEVED
        └── RECONCILE_REQUIRED   # blocked, non-terminal
```

Pre-submit invariant：

> **`backend.json` existence does not forbid `EXPIRED / CANCELLED / FAILED`; only successful/uncertain backend submission closes the pre-submit terminalization window.**

TTL invariant：

> **`EXPIRED` 只允许发生在 backend submission 之前。**

一旦 exact backend 已提交：

```text
TTL no longer changes job to EXPIRED
```

之后真实 execution/outcome 必须由 backend facts、verification 与 reconcile 决定。

## 24.2 Read-only capability

```text
CREATED
-> BACKEND_BOUND
-> RUNNING_SAFE
-> VERIFIED | FAILED
```

若在 backend submit 前 TTL 到期：

```text
EXPIRED
```

## 24.3 Local reversible capability

例如 Settings acceptance：

```text
CREATED
-> BACKEND_BOUND
-> WAITING_RESOURCE
-> RESOURCE_ACQUIRED
-> RUNNING_SAFE
-> VERIFIED
```

内部 mutation 仍经过：

```text
resource assertion
state guard
MUTATION_PREPARED
revision commit
MUTATION_COMMITTED
```

但没有 business-level unsafe `EFFECT_BOUNDARY_CROSSED`。

## 24.4 Cancellation

```text
cancel request != terminal cancellation
```

规则：

- backend 未提交：在 transition serialization 下 durable cancel intent 后，可进入 `CANCELLED`；
- backend 已提交但 unsafe boundary 未 crossed：cancel 先进入 `CANCELLING`，不得直接跳 `CANCELLED`；
- `CANCELLED` 只允许在 backend / UI mutator 已安全停止且没有 unresolved unsafe effect ambiguity 后产生；
- resource claim 继续保留，直到 backend UI mutation liveness 被证明停止；
- backend survival unknown -> capability `RECONCILE_REQUIRED`，resource claim 按 Section 16 保留；
- backend 已证明终止但 business outcome 仍不确定：可以释放 UI resource，但 capability 继续 `RECONCILE_REQUIRED`；
- 不因 coordinator timeout/process exit 自动释放 resource；
- `cancel.json` 与 `effect-boundary.json` 的 winner 必须由 Section 23.2 `transition.lock` 线性化；
- effect boundary 已 durable 后的 cancel 返回 `CANCEL_AFTER_EFFECT_BOUNDARY`，不能把未知/已发生业务结果伪装成 `CANCELLED`。

## 24.5 Completion marker

`result.json` 是 **terminal business-outcome linearization point**。在 `result.json` durable 之前，任何 surface 都不得报告 `terminal=true`。

只有：

```text
VERIFIED
OUTCOME_NOT_ACHIEVED
FAILED
CANCELLED
EXPIRED
```

才允许 durable publish final `result.json`。

### Terminalization ordering — normative

terminalization 必须在 per-capability `transition.lock` 下执行：

```text
1. re-read state/backend/resource/effect/verifier facts
2. prove one supported final outcome with no unresolved contradiction
3. create result.json.tmp with immutable final outcome/evidence refs
4. fsync(result.json.tmp)
5. atomic rename -> result.json
6. fsync(capability-job dir)
   ^ terminal linearization point
7. release transition.lock
8. move active/<job> -> archive/<outcome>/<job>
9. fsync active/ and destination archive parent dirs
```

规则：

- `state.json` **不得先写成 terminal outcome 再等待 result.json**；active 阶段它保留最后一个非终态 orchestration snapshot；
- `result.json` durable 后，normalized status 的 `terminal=true`、`lifecycle_state=<final outcome>` 必须由 result authority 派生，即使 archive move 尚未完成；
- crash 在 step 5/6 之前：不得报告 terminal；按 durable facts 继续/reconcile；
- crash 在 step 6 之后、archive move 之前：job 可以仍位于 `active/`，但 `status` 必须识别 durable result 并返回 terminal；
- archive move 是 housekeeping/index placement，不是 business outcome 的第二 linearization point；
- result durable 后不得再改变 final outcome，只允许修复 archive placement/diagnostic metadata。

### Result integrity failure

`result.json` 是 final outcome SOT，因此它自身若 parse/schema/read/hash-integrity 失败，不得依赖 archive directory 名或旧 `state.json` 猜测 outcome：

```text
RESULT_STORE_CORRUPT
terminal = false
next_action = RECONCILE
no external-effect replay
```

explicit reconcile 只有在**独立 durable evidence** 能唯一证明原 final outcome 与 request identity 时，才允许安全 republish identical terminal result；否则保持 recovery blocked / operator escalation。archive path 只是 derived placement，不是 substitute outcome authority。

`RECONCILE_REQUIRED`：

```text
non-terminal
stays in active/
state.json.lifecycle_state = RECONCILE_REQUIRED
state.json + journal/evidence record the blocked state
no final result.json yet
```

Controller contract：

```text
status.lifecycle_state == RECONCILE_REQUIRED
-> stop ordinary completion polling/backoff
-> next_action = RECONCILE
-> do not wait for result.json to appear by itself
```

因为 v0.6 无 background reconcile/daemon，`result.json` 不会在无人执行 recovery 的情况下“最终自己出现”。

explicit `capctl reconcile` 可以：

```text
RECONCILE_REQUIRED -> VERIFIED
RECONCILE_REQUIRED -> OUTCOME_NOT_ACHIEVED
RECONCILE_REQUIRED -> FAILED
```

其中 `FAILED` 只允许在证据证明 unsafe external effect 没有发生、且失败事实明确时使用。

如果仍无法确定：

```text
remain RECONCILE_REQUIRED
```

不得为了清理 active job 而伪造 terminal outcome。

# 25. Outcome Contract

## 25.1 Final terminal business outcomes

```text
VERIFIED
OUTCOME_NOT_ACHIEVED
FAILED
CANCELLED
EXPIRED
```

## 25.2 Recovery-blocked state

```text
RECONCILE_REQUIRED
```

不是 final business outcome，而是：

> execution 已停止自动推进；side-effect replay 被禁止；当前证据不足以安全决定最终 outcome。

因此：

- 不写 final `result.json`；
- 不进入 terminal archive；
- 保持 active blocked；
- 只能通过 explicit `capctl reconcile` 继续分类。

## 25.3 FAILED

只用于：

```text
已确认 validation/execution failed
+
不存在 unresolved external effect ambiguity
```

在 unsafe boundary 之后，只有 positive evidence 证明 external effect 未发生时，才可能 reconcile 到 `FAILED`。

## 25.4 VERIFIED

具有 capability-specific positive evidence。

## 25.5 OUTCOME_NOT_ACHIEVED

仅允许：

```text
positive evidence proves intended business outcome did NOT occur
```

它不是：

```text
verifier temporarily did not see success
```

并且：

```text
OUTCOME_NOT_ACHIEVED
!= automatic retry authorization
```

对于 `replay=NEVER` / single-use approval：

```text
new external attempt requires a new job + new approval
```

## 25.6 CANCELLED

仅在系统能证明 external unsafe effect 尚未开始，或 capability 本身无该类 effect 时成立。

effect boundary 已 crossed 后，不得仅因用户请求取消而终结为 `CANCELLED`。

## 25.7 EXPIRED

仅用于：

```text
expires_at passed
before backend submission
```

必须保证：

```text
Android/backend side effect = 0
```

backend 一旦提交，TTL 不再产生 `EXPIRED` transition。

## 25.8 RECONCILE_REQUIRED causes

包括：

- unsafe boundary 后 verifier infrastructure failure；
- backend survival unknown；
- action may have happened but durable mutation commit/evidence missing；
- contradictory durable facts；
- eventual consistency 尚无法判断；
- stale resource claim 无法安全回收。

注意：

```text
resource claim may later be safely released
while
capability outcome remains RECONCILE_REQUIRED
```

两者不是同一状态机。

# 26. Capability-Specific Verifier Contract

每个 BUSINESS capability 必须定义：

```text
verification window
observation-only retry/backoff
positive success evidence
positive negative evidence (if any)
ambiguity rule
```

## 26.1 TikTok

必须继承已有 Profile reconciliation。

禁止实现：

```text
immediate post absent
=> FAILED
```

正确：

```text
profile evidence / durable publisher state
=> VERIFIED
or positive not-achieved
or RECONCILE_REQUIRED
```

---

# 27. Approval Contract

## 27.1 Exact binding

`approval.json` 至少：

```json
{
  "approval_version": 1,
  "job_id": "cap-123",
  "capability": "tiktok.publish",
  "capability_version": "1.0",
  "request_sha256": "...",
  "approved_by": {
    "principal_type": "...",
    "principal_id": "..."
  },
  "approved_at": "...",
  "expires_at": "...",
  "nonce": "...",
  "single_use": true
}
```

`approval.json` activation 后 immutable。

## 27.2 Trusted origin

`approved_by` 不能直接来自 request 的 `requested_by`。

它必须由 trusted control-plane context 提供，例如：

- current authenticated ChatGPT authorization context；
- allowlisted Telegram ingress；
- trusted local controller。

v0.6 不设计 general identity provider。

## 27.3 Approval validation timing

对 `approval=REQUIRED` 的 external commit：

1. invocation/preflight 时检查 request hash / capability / version；
2. resource 等待期间 approval 可能过期，因此；
3. **在 `EFFECT_BOUNDARY_CROSSED` 之前必须再次验证 approval validity/expiry**；
4. final validation PASS 后才允许 durable boundary；
5. `effect-boundary.json` 必须记录 `approval_sha256` / `approval_nonce`；
6. boundary durable 即视为 single-use approval 已消费。

## 27.4 Existing one-URL authorization

现有规则继续：

> 在授权的 `douyin-tiktok-publish` workflow 中，用户提交一个 Douyin URL 可构成该内容 exactly-one PUBLIC COMMIT attempt 的显式授权。

Gateway migration 时：

1. upstream workflow 完成最终 artifact/caption/visibility request；
2. 将现有 authorization evidence **绑定到该 immutable `request_sha256`**；
3. 创建 single-use `approval.json`；
4. request 之后任何 material mutation 使 approval invalid；
5. 不允许 silent rebind 到新的 request hash；
6. Publish boundary 前必须最终验证 approval hash / expiry；
7. boundary crossed 后该授权即被消费；
8. `OUTCOME_NOT_ACHIEVED`、timeout 或 verification ambiguity 都不重新授予一次 Publish；
9. 第二次 Publish 必须是新 job + 新 authorization。

# 28. Capability CLI / API Surface

v0.6 最小 CLI：

```bash
capctl list
capctl describe <capability>
capctl invoke <capability> --request FILE
capctl status <cap_job_id>
capctl cancel <cap_job_id> --reason ...
capctl reconcile <cap_job_id>
capctl reconcile-resource --claim-id <claim_id>
capctl doctor
capctl gc --dry-run [--older-than <duration>]
capctl gc --apply --older-than <duration>
capctl admin force-reset-ui-runtime --claim-id <id> --reason <text>
```

## 28.1 list / describe / doctor

`list`：

```text
static Catalog
+
advisory dynamic node health
```

但不修改 Catalog。

`doctor` 可以执行 diagnostics/preflight 并更新 advisory health snapshot，但不修改 capability job outcome。

## 28.2 status

严格 read-only：

```text
read active/archive durable facts
render state/backend/resource/evidence summary
```

不得：

```text
release claim
resubmit backend
terminalize reconcile job
write recovery classification
```

## 28.3 invoke

Foreground synchronous。

不提供：

```text
--detach
--schedule
```

`invoke` 对新的 `submission_id` 创建新 intent；对已存在的同 `submission_id` + exact request，执行 deterministic admission lookup。

默认只返回既有 job/status，不做 silent unsafe recovery。唯一允许继续 execution 的特殊情况是 **explicitly retriable pre-submit continuation**（例如 `CLOCK_SUSPECT_PRE_SUBMIT` 修复后重试），且必须 positive-prove backend never-created、无 mutation/effect uncertainty，并重新通过 TTL/approval/readiness gates。

## 28.4 cancel

`capctl cancel` 是 cooperative cancellation request，但必须参与 Section 23.2 的 unsafe-boundary linearization。

```text
cancel request
!=
proof of terminal cancellation
```

流程：

```text
acquire capability transition.lock
re-read result.json / effect-boundary.json / state.json
if durable result.json exists:
    return existing terminal outcome; do not write cancel.json
elif boundary absent:
    durable publish cancel.json
    durable state -> CANCELLING or pre-submit cancel path
else:
    return CANCEL_AFTER_EFFECT_BOUNDARY
release transition.lock
```

`result.json` 的 terminal authority 高于晚到的 cancel request；terminal linearization 后任何 cancel/reconcile 请求都不得改写 final outcome。

如 existing backend 支持 v0.5 cooperative cancellation，则在 durable cancel intent 后请求其安全停止；若 backend 不支持 cooperative cancel，则等待自然停止/已有 recovery evidence，**不得为了普通 cancel 直接 SIGKILL**。

terminal semantics 遵守 Section 24。

## 28.5 reconcile

唯一允许显式推进 unresolved recovery state 的入口。

入口第一步必须在需要 mutation 时取得 `transition.lock` 并 re-read `result.json`。若 durable terminal result 已存在：

```text
return existing terminal outcome
no lifecycle/resource/business recovery mutation for that capability outcome
```

resource-only cleanup 若仍有独立 stale claim，则必须按 Section 16 的 exact resource proof 作为单独 maintenance fact 处理，不得改变已 final business outcome。

允许：

- inspect exact backend；
- perform observation-only / reversible verification work；
- reacquire `android_ui` when verifier itself needs UI；
- release stale resource claim when backend liveness is positively resolved；
- transition `RECONCILE_REQUIRED` to a supported final outcome。

禁止：

```text
automatic second external commit
reuse consumed approval
allocate second backend to "try again"
```

## 28.5A reconcile-resource — LEGACY / resource-only recovery

Migration 期间 `owner_kind=LEGACY` 的 durable claim 可以没有 `capability_job_id`，因此必须提供 resource-addressable normal recovery：

```text
capctl reconcile-resource --claim-id <exact-claim-id>
```

它只允许：

```text
inspect exact claim/backend/process/subordinate evidence
apply Section 16.6 positive-stop proof
durably release the exact stale android_ui claim when proof succeeds
record audited resource-recovery evidence
```

它禁止：

```text
invent capability_job_id
terminalize any BUSINESS capability outcome
repeat backend/external effect
weaken positive-stop proof
```

对于 `owner_kind=CAPABILITY`，优先使用 `capctl reconcile <cap_job_id>`；resource-only form 只在明确的 resource recovery / migration 场景使用。

## 28.6 Maintenance / ADMIN commands

`capctl gc` 只处理 terminal archive、proven orphan temp/.staging、过 retention 的 submission binding；不删除 active/RECONCILE_REQUIRED/current claim/unresolved effect evidence。默认 dry-run，删除必须显式 `--apply`，并 fsync parent dir。它不是后台任务。

`capctl admin force-reset-ui-runtime` 是 audited unsafe emergency path；自动 bump epoch；不 terminalize/replay 旧业务。

## 28.7 Python API

CLI 可以调用同一个 plain Python runtime function。

不建立 RPC daemon。

# 29. Minimal Implementation Shape

本 PRD 只定义逻辑组件，不强制复杂 class hierarchy。

推荐最多：

```text
capability/
├── catalog.py       # load + validate static definitions
├── runtime.py       # job/policy/resource/backend/outcome orchestration
└── capctl.py        # CLI
config/
└── capabilities.json
```

可根据实现实际拆分，但以下在 v0.6 明确禁止：

```text
adapter plugin framework
abstract factory tree
event bus
dependency injection container
generic workflow engine
database repository layer
microservice split
```

Adapters 优先采用：

```python
ADAPTERS = {
    "tiktok_publish": tiktok_publish_adapter,
    "android_ui_workflow": ui_workflow_adapter,
}
```

plain function mapping 即可。

---

## 29.1 Adapter Contract

原始 Gateway PRD 的 Adapter Layer 保留，但职责被收窄，避免 Adapter 各自实现 policy/locking/lifecycle。

Gateway runtime 统一负责：

```text
request activation
effective policy
TTL
deterministic backend binding
resource ownership
lifecycle
final terminalization
reconcile orchestration
```

Adapter 只负责：

```text
capability-specific payload validation
translate payload -> existing backend request
invoke/attach exact preallocated backend ID
propagate exact resource_guard into mutating UI backend
normalize backend execution facts
provide capability-specific verifier hook
```

Adapter **不得**：

```text
reacquire android_ui independently
allocate a second backend ID after uncertainty
weaken effective policy
rewrite Bridge/UI executor
invent its own job lifecycle
write a competing effect-boundary fact
```

对于已有 backend-specific unsafe marker（如 TikTok `COMMITTING`），Adapter/Publisher 必须按 Section 23 的顺序与 capability effect boundary 对齐，而不是产生独立的重试语义。

这保留原始 PRD “wrap, do not rewrite”的扩展价值，同时消除每个 Adapter 重复实现 runtime logic 的风险。

# 30. Core Primitive Boundary

## 30.1 Core owns generic primitives

Observation：

```text
health
observe
screenshot
find
findAll
assert
waitFor
waitStable
```

UI mutation：

```text
click
longClick
inputText
clearText
swipe
scroll
pressBack
pressHome
```

Generic platform：

```text
app launch/stop/state
file push/pull
package/process operations where already supported
```

State integrity：

```text
state token
semantic fingerprint
revision
resource ownership assertion
mutation prepare/commit
reconcile support
```

v0.6 implementation 必须拆掉 v0.5 中把 `pressBack` / `pressHome` 与 observe action 放在同一个 `SAFE_ACTIONS` 概念里的歧义：

```text
observation safety
!=
mutation classification
!=
replay safety
```

`pressBack` / `pressHome` 在 mutation classification 中属于 `LOCAL_UI_MUTATION`，因此必须拥有 `android_ui`、通过 guard，并推进 revision。

## 30.2 Core does NOT own business verbs

禁止：

```text
publishTikTok()
postInstagram()
sendTelegramMessage()
```

这些属于 BUSINESS capability / adapter。

---

# 31. Status Lookup and Archive Race

Capability lookup 使用 Bridge v2 同类 bounded direct-lookup pattern，但必须认识到：

```text
RECONCILE_REQUIRED stays in active/
```

Lookup：

```text
1. active/<id>
2. direct lookup known terminal archive classes
3. short grace
4. repeat once
5. return not-found only after bounded repeat
```

Terminal archive classes：

```text
verified
outcome_not_achieved
failed
cancelled
expired
```

不得：

```text
archive scan
```

也不得把 active `RECONCILE_REQUIRED` 当成 false `JOB_NOT_FOUND`。

`capctl status` 只读取上述记录，不执行 recovery mutation。为避免观察到 lifecycle/result writer 的中间态，对单一 capability job 的 consistency-sensitive snapshot 必须：

```text
open transition.lock
acquire LOCK_SH (bounded/read-only)
read result.json first, then state.json + required immutable/durable facts
render normalized status
release LOCK_SH
```

writer 侧使用 `LOCK_EX`，因此 status 不会在 `result.json` rename 与 parent-dir fsync 之间抢先报告 terminal。取得 read lock **不属于 recovery mutation**。若 bounded shared-lock acquisition 超时，status 返回 machine-readable transient diagnostics，不得无锁降级为可能不一致的 terminal judgment。

Normalized status 必须至少返回：

```json
{
  "lifecycle_state": "RECONCILE_REQUIRED",
  "terminal": false,
  "result_present": false,
  "next_action": "RECONCILE"
}
```

对于 durable `result.json`（无论 job 尚在 `active/` 还是已进入 terminal archive）：

```text
terminal = true
lifecycle_state = result.outcome
result_present = true
next_action = NONE
```

因此 `active/<id>/result.json` 是 crash-after-terminal-linearization / before-archive-move 的合法短暂状态，不得误报为 non-terminal。

官方 Controller 的 completion state machine 以 `lifecycle_state + terminal` 为准，而不是以文件存在性轮询 `result.json`。

# 32. Business Idempotency Decision

v0.6 Rev3.1 **不提供 active cross-request business-idempotency engine**。

必须区分：

```text
submission_id
= transport retry identity

business idempotency key
= semantic rule deciding whether two independently created intents are the same business operation
```

Rev3.1 已通过 `submission_id` 解决：

```text
response lost / timeout
-> same submission retransmitted
-> same capability job
```

但不会根据以下内容自动 dedupe 两个新 intent：

```text
same payload
same video hash
same caption
same account
same campaign
```

真正的业务幂等仍需要：

```text
domain-specific key semantics
atomic business-key claim
request binding
retention
conflict policy
terminal outcome index
```

因此继续 deferred。

v0.6 Rev3.1 依靠：

- `submission_id` transport retry admission binding；
- deterministic capability job ID；
- deterministic backend ID；
- exact request identity；
- no auto second backend；
- effect boundary；
- existing TikTok duplicate guards。

v0.6 不宣称：

```text
arbitrary same business idempotency key guarantees exactly once
```

---

# 33. Unified Node Health, Capability Advertisement & Readiness

原始 Gateway PRD 的 `node-health.json` 设计保留，但 Rev3.5 将其从简单 health snapshot 强化为 **on-demand readiness advertisement**，仍遵守 MSA：

```text
/opt/y700/runtime/node-health.json
```

它是：

```text
dynamic planning / diagnostics / early-preflight snapshot
```

不是：

```text
static capability contract
execution outcome authority
mutation permission
resource lease authority
```

## 33.1 Health schema

建议 schema 升级为：

```json
{
  "schema_version": 2,
  "status": "HEALTHY",
  "updated_at": "...",
  "observed_boot_id": "...",
  "updated_boottime_ms": 123456,
  "contracts": {
    "gateway": 1,
    "bridge": 2,
    "ui_core": 2
  },
  "runtime": {
    "bridge": "HEALTHY",
    "ui_driver": "HEALTHY",
    "instrumentation": "READY",
    "keyguard": "CLEAR",
    "thermal": "NORMAL",
    "storage": "HEALTHY",
    "permission_integrity": "HEALTHY"
  },
  "resources": {
    "android_ui": {
      "status": "FREE",
      "claim_job_id": null
    }
  },
  "capabilities": {
    "android.device.observe": {
      "status": "READY",
      "reason_codes": []
    },
    "android.ui.workflow": {
      "status": "READY",
      "reason_codes": []
    },
    "tiktok.publish": {
      "status": "READY",
      "reason_codes": []
    }
  }
}
```

规则：

- 不用 daemon 持续刷新；
- `capctl doctor` / `capctl list` / invoke early-preflight 可按需刷新；
- stale `updated_at` / boot mismatch 必须可见，并将没有 fresh evidence 的 capability 视为 `UNKNOWN`，不是沿用旧 `READY`；
- protocol/contract version 必须显式可见；不做 semver negotiation；
- dynamic health 绝不修改 static Catalog minimum policy / execution profile；
- `READY` 只是 snapshot-time readiness；每个 job 的 resource/state/effect checks 仍是 execution authority。

## 33.2 Readiness state machine

capability dynamic status 只使用：

```text
UNKNOWN
READY
DEGRADED
BUSY
BLOCKED_RECONCILE
UNAVAILABLE
```

语义：

- `UNKNOWN`：没有 fresh on-demand evidence，或 snapshot 跨 boot/stale；
- `READY`：static `readiness_requirements` 在本次检查时全部满足，且无已知 blocker；
- `DEGRADED`：仅 optional/non-safety dependency 失效，但 capability 语义、minimum safety 与 verifier guarantee 不变；
- `BUSY`：runtime ready，但 required exclusive resource 当前被另一个已知安全 owner 占用；
- `BLOCKED_RECONCILE`：存在 ownership/backend/effect ambiguity，不能靠等待自动恢复；
- `UNAVAILABLE`：mandatory runtime dependency 缺失、protocol incompatible、permission integrity failure，或 capability 当前无法被安全启动。

最小 deterministic derivation：

```text
if snapshot missing/stale/boot-mismatch:
    UNKNOWN
elif unresolved ownership/backend/effect ambiguity:
    BLOCKED_RECONCILE
elif required resource safely owned by another live job:
    BUSY
elif mandatory dependency absent or contract/protocol incompatible:
    UNAVAILABLE
elif only explicitly optional dependency is degraded:
    DEGRADED
else:
    READY
```

`alive/reachable` 只是一条 evidence，**不能单独进入 `READY`**。

## 33.3 Capability Advertisement

`capctl list/describe` 逻辑上合并：

```text
Git-managed static Catalog
  - capability/version/classification
  - minimum_policy
  - execution_profile
+
current on-demand node-health snapshot
  - readiness status
  - reason_codes
  - protocol/runtime evidence
  - resource status
```

输出可以显示：

```text
tiktok.publish@1.0
placement=Y700_REQUIRED
foreground_required=true
alternate_runtime_fallback=NONE
status=READY|DEGRADED|BUSY|BLOCKED_RECONCILE|UNAVAILABLE|UNKNOWN
reason_codes=[...]
```

这是 **advertisement/view**，不是第二 registry SOT。

## 33.4 Early Preflight vs Execution Authority

Gateway 可以用 fresh readiness view 做 fail-fast：

```text
UNAVAILABLE
-> reject before starting a new backend when safely knowable

BUSY
-> existing bounded wait / DEVICE_BUSY semantics

BLOCKED_RECONCILE
-> RESOURCE_RECONCILE_REQUIRED / reconcile path
```

但任何 race 都必须由已有执行层保证兜底：

```text
readiness snapshot says READY
-> runtime changes
-> Core/backend execution-time guard sees mismatch
-> zero unsafe action / existing reconcile semantics
```

因此：

> **Readiness can deny early; readiness can never authorize mutation by itself.**

## 33.5 Protocol compatibility advertisement

借鉴 Backburner 在连接 worker 前先检查 protocol/version 的思路，Rev3.5 要求 doctor/list 至少能暴露：

```text
gateway contract version
Bridge contract version
UI Core protocol version
adapter/backend compatibility where applicable
```

如果 static capability requirement 与当前 runtime 明确不兼容：

```text
RUNTIME_CONTRACT_MISMATCH
capability status = UNAVAILABLE
backend/UI side effect = 0
```

这不是 semver negotiation，只是 exact compatibility check。

对 app-specific mutating capability，compatibility advertisement 还必须包含：

```text
installed package
installed versionCode/versionName
signing identity where available
resolved ui_contract_version
app_ui_contract_match = true|false|unknown
```

若 app/UI contract 不匹配：

```text
APP_UI_CONTRACT_MISMATCH
capability status = UNAVAILABLE
backend/UI side effect = 0
```

`UNKNOWN` 不能被 Controller 当作 `READY`。

Early readiness 不是 app/UI compatibility 的最终授权。对声明 `app_ui_contract` 的 mutating capability，Adapter/workflow 在**每个 app-specific mutating step dispatch 前**至少重新确认 installed package/version/signing identity 仍匹配；对 `EXTERNAL_COMMIT`，Section 23 final boundary preconditions 必须再次确认 `app_ui_contract_match=MATCH`。

若 app 在 early preflight 后发生 auto-update/reinstall/signature change：

```text
APP_UI_CONTRACT_MISMATCH
mutation/effect attempts = 0 for the not-yet-dispatched step
capability cannot rely on stale READY snapshot
```

该 JIT check 属于 capability/Adapter contract，不把 app-specific version knowledge 放入 generic Core。

# 34. Trigger / Transport Boundary

v0.6 不增加 mandatory transport。

当前执行入口仍可为：

```text
Cloud ChatGPT / Telegram / Hermes
-> existing authenticated control plane
-> capctl / Python API
```

未来若新增 HTTPS / Unix socket / FCM-like wake / scheduler：

```text
Transport -> wake(capability_job_id)
```

transport 只提供 wake/latency optimization。

完整 request、effective policy、resource claim、backend binding 和 result 必须来自 durable filesystem。

因此：

```text
transport failure may increase latency
transport failure must not corrupt correctness
```

这也是为什么 transport 不属于 v0.6 implementation scope。

# 35. Minimal Observability

保留原始 Gateway PRD 的 observability intent，但不增加独立 metrics subsystem。

每个 capability job 的 existing `journal.jsonl` / `result.json` 在自然可得时记录：

```text
readiness_snapshot_age_ms
readiness_preflight_ms
resource_wait_ms
gateway_to_backend_submit_ms
backend_execution_ms
verification_ms
total_job_ms
```

`capctl doctor` 可通过 bounded filesystem lookup 派生：

```text
active_job_count
verified_count
failed_count
expired_count
reconcile_required_count
```

v0.6 **不要求**：

```text
external metrics backend
prometheus exporter
continuous metrics daemon
/opt/y700/runtime/capability-metrics.json
```

如果未来诊断需要证明 standalone metrics snapshot 有价值，再 measurement-gated 增加。

## 35.1 Blocked-state visibility

`capctl doctor` / on-demand `node-health.json` 至少暴露：

```text
android_ui = FREE | OWNED | BLOCKED_RECONCILE
claim_id
owner_kind / owner_id
claim_age_ms

owner_process_state =
  MATCHING
  DEAD
  PID_REUSED
  STOPPED
  ZOMBIE
  HUNG_OR_UNKNOWN
  UNREADABLE

backend_liveness = RUNNING | STOPPED | UNKNOWN
app_ui_contract_match = MATCH | MISMATCH | UNKNOWN
active_reconcile_required_count
oldest_reconcile_age_ms
per-job reconcile_since / reconcile_age_ms
storage_health = HEALTHY | LOW_SPACE | IO_ERROR | PERMISSION_ERROR
clock_health = HEALTHY | CLOCK_SUSPECT
```

`owner_process_state` 必须联合：

```text
claim.boot_id
claim.pid
claim.proc_start_ticks
/proc/<pid>/stat
/proc/<pid> existence/readability
backend durable state
```

解释：

- `DEAD`：exact process identity 已不存在；
- `PID_REUSED`：PID 存在但 proc start ticks 不匹配；
- `STOPPED`：exact process identity 仍存在但处于可恢复的 stopped state；**不能**作为 release proof，因为进程可能被 `SIGCONT` 恢复；
- `ZOMBIE`：process 已退出执行、仅保留 zombie entry；可与 exact backend terminal/proven-not-created + no-live-mutator evidence 共同构成 positive stop proof；
- `HUNG_OR_UNKNOWN`：进程身份匹配但无进展/无法证明安全终止；
- `UNREADABLE`：权限或 proc evidence 无法可靠读取。

这些分类本身是 operations evidence；**`doctor/status` 不得据此改变 ownership/outcome**。但 explicit `capctl reconcile` 可以按 Section 16.6 把多条 independent evidence 组合成 positive stop proof，并在 canonical flock 下确定性释放 claim。

推荐规则至少包括：

```text
(DEAD|PID_REUSED|ZOMBIE) + backend STOPPED/TERMINAL/proven-not-created + no live mutator
-> recommended_action = RECONCILE

HUNG_OR_UNKNOWN | UNREADABLE | backend UNKNOWN
-> recommended_action = RECONCILE first; if positive proof remains impossible, operator may choose ADMIN_FORCE_RESET
```

`doctor` 应在能给出 exact safe next step 时输出 machine-readable recommendation，例如：

```text
recommended_action = STATUS | RECONCILE | ADMIN_FORCE_RESET | NONE
```

其中 `ADMIN_FORCE_RESET` 仍需显式 operator/admin 执行，绝不由 doctor 自动触发。

## 35.2 Operational Alert Rules — Normative

v0.6 不内置 alert daemon；Controller/外部监控消费 `doctor` / `status` 时必须遵循以下标准告警语义：

| Condition | Severity | Required response |
|---|---|---|
| `active_reconcile_required_count > 0` | HIGH | surface immediately; inspect exact jobs; no new-ID retry for same intent |
| `oldest_reconcile_age_ms` beyond measured WARN/HIGH threshold | WARN/HIGH | escalate visibility/operator ownership; **never** auto-terminalize, auto-GC, auto-release or auto-replay |
| `android_ui=BLOCKED_RECONCILE` | HIGH | status/doctor/reconcile; operator escalation if unresolved |
| current claim + `owner_process_state=DEAD/PID_REUSED/ZOMBIE` | HIGH | recommend normal reconcile; release only after Section 16.6 positive-stop proof |
| current claim + `owner_process_state=STOPPED` | HIGH | treat as potentially resumable; reconcile/explicit stop proof; **never release on STOPPED alone** |
| current claim + `HUNG_OR_UNKNOWN/UNREADABLE` beyond measured warning age | HIGH | operator/reconcile review; no lease stealing |
| `storage_health=LOW_SPACE` | WARN | run `gc --dry-run`; plan explicit cleanup |
| `storage_health=IO_ERROR/PERMISSION_ERROR` | CRITICAL | block new mutating work; repair storage/permissions explicitly |
| `clock_health=CLOCK_SUSPECT` | WARN/HIGH | prevent time-sensitive new mutating intent if TTL interpretation is unreliable |
| `OBSERVABILITY_DEGRADED` | WARN | repair diagnostics path; does not itself authorize state mutation |
| `CAPABILITY_NOT_READY` / `RUNTIME_CONTRACT_MISMATCH` recurring | WARN/HIGH | repair mandatory dependency/version; do not bypass with alternate runtime |
| `UNEXPECTED_BLOCKING_OVERLAY` recurring | WARN | capability/UI contract review, not blind retry |

Thresholds such as `claim_age_warn_ms` / `LOW_SPACE` bytes / readiness snapshot age are Sprint-0 measured operational config，**不是 ownership/replay authority**。

Reference Controller 必须把 HIGH/CRITICAL condition 明确 surfaced 给 operator；本 PRD 不要求常驻监控服务。

## 35.3 Journal growth rule

`journal.jsonl` 是 per-job journal；不做 in-place rotation。blob 写 evidence reference/hash；event payload bounded；terminal history 由 archive retention/GC 控制；safety-critical journal write failure 走 Durability Failure Contract。

## 35.4 Storage retention / GC

无 background GC daemon。

```text
capctl gc --dry-run
capctl gc --apply --older-than <duration>
```

active / RECONCILE_REQUIRED / current claim / unresolved effect evidence 永不作为普通 GC candidate。

```text
submission binding retention >= capability-job query retention
```

```text
backend execution-fact retention referenced by an active/RECONCILE_REQUIRED capability
>= that parent capability's active/reconcile lifetime + required query/recovery window
```

GC/retention 配置若无法保证上述关系，则 `backend never-created` proof 不得成立，相关 job 必须保守进入/保持 recovery blocked，而不能从 ENOENT 推断“从未执行”。

Sprint 0 测量 free-space、typical job/evidence size，确定 LOW_SPACE threshold。无法保证 required safety records durable 落盘时，新 mutating capability fail closed。

# 36. Security and Trust Boundaries

## 36.1 Filesystem

新 runtime artifacts：

```text
directories 0700
files       0600
root owned
```

沿用 symlink/path traversal protections。

Runtime preflight / `doctor` 必须 lstat 校验 root ownership、required regular path 非 symlink、无 group/other write permission、known parent path。

异常：

```text
RUNTIME_PERMISSION_INTEGRITY_ERROR
```

mutating capability fail closed。不得静默 chmod/chown 修复后继续；显式 ADMIN repair 必须 audit + re-preflight。

## 36.2 State token

不是 credential。

## 36.3 requested_by

不是 authenticated identity。

## 36.4 Capability Gateway

v0.6 只面向已有 trusted local-node/control-plane。

不直接开放公网 API。

## 36.5 Secrets

approval context、credentials、Telegram ids 等不进入 public Git。

## 36.6 Single External Control Boundary

Rev3.5 固化以下网络暴露规则：

```text
external/remote transport
-> authenticated trusted control boundary
-> Capability Gateway
-> internal local interfaces
```

Gateway 的引入 **不得** 让以下内部能力直接变成 remote API：

```text
Bridge root executor
UI Core primitive executor
app-specific controller internals
raw filesystem job directories
```

当前 v0.6 没有 public HTTP API，因此不新增 Noise/PSK/额外 tunnel 实现；但未来无论采用 SSH、Cloudflare Tunnel、HTTPS、Unix-socket proxy 或其他 transport，都必须把 auth/encryption/remote exposure 收敛在 Gateway/control-plane edge，而不是让每个 backend 单独暴露端口。

这是 trust-boundary constraint，不是新 transport scope。

---

# 37. Error Contract

至少：

```text
CAPABILITY_NOT_FOUND
CAPABILITY_VERSION_MISMATCH
CAPABILITY_REQUEST_INVALID
CAPABILITY_NOT_READY
RUNTIME_CONTRACT_MISMATCH
SUBMISSION_ID_REQUIRED
SUBMISSION_ID_CONFLICT
CAPABILITY_EXPIRED
POLICY_WEAKENING_NOT_ALLOWED
JOB_CONTRACT_VIOLATION
APPROVAL_REQUIRED
APPROVAL_INVALID
CANCEL_AFTER_EFFECT_BOUNDARY
DEVICE_BUSY
RESOURCE_RECONCILE_REQUIRED
BACKEND_BINDING_CONFLICT
BACKEND_STATE_UNKNOWN
STALE_STATE_EPOCH
STALE_STATE_REVISION
STALE_STATE_HASH
STATE_TOKEN_EXPIRED
UNGUARDED_MUTATION_NOT_ALLOWED
MUTATION_OUTCOME_UNKNOWN
VERIFIER_UNAVAILABLE
RECONCILE_REQUIRED
DURABILITY_IO_ERROR
STORAGE_FULL
STATE_INTEGRITY_UNAVAILABLE
STATE_STORE_CORRUPT
RESULT_STORE_CORRUPT
DEVICE_UI_RUNTIME_UNSAFE
APP_UI_CONTRACT_MISMATCH
RUNTIME_PERMISSION_INTEGRITY_ERROR
ADMISSION_LOCK_TIMEOUT
SUBORDINATE_BINDING_INVALID
CLOCK_SUSPECT
STATE_TOKEN_BOOT_MISMATCH
STATE_TOKEN_PROFILE_MISMATCH
STATE_FINGERPRINT_UNAVAILABLE
UNEXPECTED_BLOCKING_OVERLAY
CONTROLLER_RETRY_CONTRACT_VIOLATION
OBSERVABILITY_DEGRADED
```

错误必须 machine-readable。

## 37.1 CLI / Python Error Envelope

`capctl`: stdout exactly one JSON envelope；stderr optional diagnostics；command failure uses non-zero exit code。Envelope 至少含：

```text
code
message
retryable
phase
lifecycle_state
terminal
next_action
```

并在可用时带 `capability_job_id/submission_id/claim_id/request_sha256`；不得泄露 secret/payload。Python API 使用同一 code/context。

`retryable` 只表示“当前 command/transport 可以按既定 contract 自动重复”，不是 business side-effect replay permission。关键映射：

```text
ADMISSION_LOCK_TIMEOUT -> retryable=true,  next_action=RETRY_SAME_SUBMISSION
DEVICE_BUSY            -> retryable=true within bounded controller budget
RECONCILE_REQUIRED     -> retryable=false, terminal=false, next_action=RECONCILE
terminal outcome       -> retryable=false, terminal=true,  next_action=NONE
```

Additional ownership of error emission：

```text
CONTROLLER_RETRY_CONTRACT_VIOLATION
= first-party Controller / audit contract violation
= NOT a Gateway-guaranteed detector for arbitrary two-ID business equivalence

CANCEL_AFTER_EFFECT_BOUNDARY
= cancel arrived after the durable unsafe boundary winner
= retryable=false
= terminal=false

STATE_STORE_CORRUPT
= lifecycle snapshot cannot be trusted
= retryable=false
= terminal=false
= next_action=RECONCILE

RESULT_STORE_CORRUPT
= final outcome record cannot be trusted
= retryable=false
= terminal=false until independently reconciled/re-published
= next_action=RECONCILE
= never authorizes external-effect replay

DEVICE_UI_RUNTIME_UNSAFE
= ADMIN stop/quiescence proof failed
= retryable=false
= new mutating BUSINESS work blocked
```

```text
CLOCK_SUSPECT (pre-submit)
= retryable=false while clock is unhealthy
= terminal=false
= next_action=REPAIR_CLOCK
= after repair, same-submission invoke may re-enter only the safe pre-submit continuation rule
```

## 37.2 Durability Failure Contract

所有 safety-critical durable write 必须检查 write/fsync(file)/rename-or-unlink/fsync(parent-dir)。

- backend/mutation 尚未开始且 durable prerequisite 失败 -> `DURABILITY_IO_ERROR`/`STORAGE_FULL`, side_effect=0；
- claim create/cleanup durability 不确定 -> `RESOURCE_RECONCILE_REQUIRED`；
- UI mutation 已可能发生但 revision 无法 durable -> `STATE_INTEGRITY_UNAVAILABLE` + `RECONCILE_REQUIRED`，阻断未来 protocol-v2 mutation；
- storage 恢复后必须 durable new state_epoch + known revision baseline 才恢复 mutation lane；
- `effect-boundary.json` 未 durable -> external irreversible effect MUST NOT dispatch；
- external effect/outcome 已发生但 terminal result 无法 durable -> `RECONCILE_REQUIRED`，只允许安全重发 terminal record，不允许重做 external effect；
- `state.json` durable publish/parse/schema failure -> `STATE_STORE_CORRUPT` or `DURABILITY_IO_ERROR`; do not continue from RAM-only lifecycle state；
- **任何 safety-critical durable publish 返回错误/parent-dir fsync ambiguity 后，进程内 memory object 不得作为后续 causal-step authority；必须 re-read durable storage 或进入 blocked/reconcile state。**

## 37.3 Temp / Staging Failure

temp/.staging 永不 executable。orphan 由 doctor 报告，gc 仅在证明 non-active/unbound 后清理。

---

## 37.4 Fault-Injection Test Contract

实现必须提供可重复的 fault-injection seam，至少覆盖：

```text
after temp write / before file fsync
after file fsync / before rename
after rename / before parent-dir fsync
after parent-dir fsync / before next causal step
before/after revision durable write
before/after MUTATION_COMMITTED append
before/after effect-boundary durable publish
after external-effect dispatch / before terminal-result publish
```

要求：

1. unit/integration simulation 层必须覆盖全部 named boundary；
2. 真机至少覆盖代表性的 kill/crash/restart case；
3. fault-injection 只能存在于 test/debug build path，production path 不提供远程任意 crash API；
4. 每个注入点必须验证 Recovery Matrix 中对应 invariant，而不只是验证进程退出；
5. CI 中 semantic vectors、durability ordering、no-blind-replay 相关 fault tests 为 blocking checks。

---

# 38. Recovery Matrix

| Failure point | Required behavior |
|---|---|
| durability fails before backend | no backend/mutation; fail closed |
| claim durability ambiguous | RESOURCE_RECONCILE_REQUIRED |
| revision persist fails after mutation | STATE_INTEGRITY_UNAVAILABLE + RECONCILE_REQUIRED |
| effect-boundary fsync fails | external effect attempts = 0 |
| final result persist fails post-effect | RECONCILE_REQUIRED; no effect retry |

| state.json write/rename/fsync corrupt or ambiguous | STATE_STORE_CORRUPT / DURABILITY_IO_ERROR; RAM lifecycle state not authoritative; explicit reconcile rebuild only from durable facts |

| valid result.json exists but state.json is corrupt | terminal result remains authoritative; surface state diagnostic degradation; do not reopen business outcome |
| result.json corrupt/unreadable | RESULT_STORE_CORRUPT; do not infer outcome from archive path/state; no replay; reconcile may republish only from independent exact evidence |
| status races lifecycle/result writer | status takes bounded transition `LOCK_SH`; writer uses `LOCK_EX`; never report terminal from an un-fsynced intermediate publish |
| cancel and effect-boundary race | transition.lock serializes; durable cancel wins -> no boundary; durable boundary wins -> CANCEL_AFTER_EFFECT_BOUNDARY/no CANCELLED |
| ADMIN force-reset cannot prove UI quiescence | DEVICE_UI_RUNTIME_UNSAFE; keep claim; block new mutating BUSINESS work; reboot/repair required |
| permission/symlink integrity fails | RUNTIME_PERMISSION_INTEGRITY_ERROR |
| token boot mismatch | STATE_TOKEN_BOOT_MISMATCH |
| token fingerprint profile mismatch | STATE_TOKEN_PROFILE_MISMATCH; zero action attempts |
| suspend/deep sleep makes token older than max_age | STATE_TOKEN_EXPIRED; fresh AUTO observe/preflight required before any mutation |
| admission lock timeout | ADMISSION_LOCK_TIMEOUT; no job/backend |
| mutating subjob lacks provenance | SUBORDINATE_BINDING_INVALID |
| unexpected blocking top-level dialog/window before mutation | `UNEXPECTED_BLOCKING_OVERLAY`; zero action attempts |
| IME/toast/non-focusable transient secondary window present without blocker evidence | do not set blocking_overlay solely from presence; normal action/state guards still apply |
| owner PID absent or reused | doctor classifies evidence; normal release still requires reconcile/backend-stop proof |
| concurrent same `submission_id` + same request | admission lock serializes; both resolve to same deterministic capability job |
| same `submission_id` + different request | `SUBMISSION_ID_CONFLICT`; no new job/backend |
| crash after submission binding durable / before capability activation | same-submission retry reconstructs/activates same deterministic job; no second job |
| transport response lost after capability activation | same-submission retry returns exact existing job/status |
| crash before capability activation | no active job |
| crash after activation, before `backend.json` | explicit reconcile; no backend assumption |
| crash after `backend.json`, before resource | backend identity known; `backend.json` remains immutable binding only; explicit reconcile may terminalize EXPIRED/CANCELLED/FAILED only when exact pre-submit cause + never-created backend are positively proven |
| crash after resource claim, before backend submit | explicit reconcile may prove no backend and release claim; no blind submit |
| crash before durable claim fsync/rename completes | backend must not have been submitted; no competing execution permitted by protocol |
| crash after backend submit before Gateway acknowledgement | discover same exact backend; never allocate second backend |
| Gateway crash while backend UI workflow alive | durable claim blocks competitor |
| old coordinator gone but backend liveness unknown | keep claim; `RESOURCE_RECONCILE_REQUIRED`; status/doctor do not release |
| owner DEAD/PID_REUSED/ZOMBIE + exact backend STOPPED/TERMINAL/proven-not-created + no live subordinate mutator | explicit `capctl reconcile` must release exact claim under canonical flock; ADMIN force-reset not required |
| owner process STOPPED but not dead | keep claim; stopped process may resume; reconcile must first obtain positive termination proof or operator may perform exact-process stop/ADMIN reset |
| backend proven stopped but business outcome unknown | UI claim may be released; capability remains `RECONCILE_REQUIRED`; later UI reconcile uses a new exact claim and new reconcile subjob, never rebinds old subjob |
| crash after `MUTATION_PREPARED`, before Android action | current state/revision decides; no blind replay |
| crash after action, before revision commit | old token must not be accepted; reconcile actual state |
| revision durable, crash before `MUTATION_COMMITTED` | job reconcile; old token already invalid |
| crash before capability effect boundary | no external retry unless exact backend evidence proves no effect and new policy/approval permits |
| capability effect boundary durable, Publisher `COMMITTING` absent | conservative `RECONCILE_REQUIRED`; no auto external retry |
| Publisher `COMMITTING` durable, before Publish result | `RECONCILE_REQUIRED`; no auto external retry |
| verifier unavailable after unsafe effect | `RECONCILE_REQUIRED` |
| `OUTCOME_NOT_ACHIEVED` after consumed approval | no auto retry; new attempt requires new job/approval |
| `expires_at` passes while waiting for resource | `EXPIRED`, only if backend not submitted |
| `expires_at` passes after backend submit | ignore for terminal classification; continue execution/verify/reconcile |
| result durable, archive move pending | status must still resolve job |
| corrupted device-state ledger | fail closed; explicit reset/new epoch only |
| direct mutating Core call without valid claim | zero action attempt; ownership error |
| stale `node-health` says READY but current runtime differs | ignore snapshot as authority; execution-time guard/preflight decides |
| mandatory runtime/protocol dependency absent before backend | `CAPABILITY_NOT_READY` / `RUNTIME_CONTRACT_MISMATCH`; zero backend/UI side effect |

| installed app/UI contract mismatches tested Catalog contract | `APP_UI_CONTRACT_MISMATCH`; readiness UNAVAILABLE; zero backend/UI side effect |
| reboot + CLOCK_SUSPECT for old pre-submit job | no backend submit; no EXPIRED classification; preserve pre-submit lifecycle + `CLOCK_SUSPECT_PRE_SUBMIT`, next_action=REPAIR_CLOCK; after repair only same-submission safe pre-submit continuation |
| backend lookup ENOENT but SOT integrity/retention not proven | never-created proof fails; BACKEND_STATE_UNKNOWN / RECONCILE_REQUIRED |
| LEGACY stale claim with no capability_job_id | `reconcile-resource --claim-id` may release only after Section 16.6 positive-stop proof |
| optional non-safety diagnostic/optimization missing | may continue `DEGRADED` only if semantic/verifier contract unchanged; journal reason |
| unique/uncertain state lost after backend/mutation/effect may have occurred | no alternate runtime/backend; `RECONCILE_REQUIRED` / exact status path |

# 39. Migration Plan

## 39.1 Phase 0A — Passive Freeze / Inventory

Before any repository code/tooling change：

- inventory all production UI mutating entrypoints；
- record existing `android-ui.lock` users；
- record existing COMMIT/reconcile boundaries；
- capture current Settings / TikTok baseline；
- capture current performance only as baseline, not new hard SLA。

## 39.1B Phase 0B — Validation Tooling Authorization

Rev3.6 显式区分：

```text
Production Runtime Implementation Authorization = NO
Phase 0B validation-tooling authorization       = YES after Rev3.6 Freeze Approval
```

Phase 0B 只允许新增/修改：

```text
scripts/v06/*
tests/fault_injection/*
diagnostic/evidence collectors
CI checks limited to validating frozen contracts
documentation / measurement output
```

Phase 0B 禁止：

```text
改变 production Gateway/Core/Bridge runtime behavior
启用 BUSINESS capability
修改 production mutation path
修改 effect/replay semantics
部署新的 production daemon/service
```

Phase 0B 完成并通过 Section 46 empirical gates 后，才召开独立 **Production Runtime Implementation Authorization** review；通过后才进入 Phase 1 / Sprint 1。

## 39.2 Phase 1 — Shared UI ownership + State Integrity

Implement first, without Gateway BUSINESS activation：

- shared `android_ui` arbiter library；
- reuse `/opt/y700/runtime/android-ui.lock`；
- durable claim with unique `claim_id`；
- Core protocol v2 `resource_guard` ownership assertion；
- migrate legacy TikTok mutating path to shared arbiter and propagate exact claim into UI jobs；
- eliminate nested `ui_lease()` reacquisition when a top-level claim already exists；
- add `device-state.json`；
- add state token / AUTO guard；
- split observation safety from mutation/replay classification；
- classify `pressHome` / `pressBack` as `LOCAL_UI_MUTATION`；
- add `MUTATION_PREPARED/COMMITTED` journal semantics；
- freeze revision-before-commit ordering；
- prove stale/manual drift/direct-bypass rejection。

Exit:

```text
all production mutating UI paths use one arbiter
Settings state-integrity acceptance PASS
existing TikTok behavior unchanged
```

## 39.3 Phase 2 — Static Catalog + Capability Job

Implement：

- capability namespace / stable naming rule；
- `config/capabilities.json`；
- minimal `execution_profile` (Y700 placement / foreground / readiness requirements / no implicit alternate runtime)；
- mandatory `submission_id` + deterministic admission binding；
- exact version matching；
- classification；
- minimum/effective policy；
- `expires_at` / pre-start expiration；
- atomic capability job store；
- request/policy hash；
- status lookup。

Initially enable read-only/internal path first。

## 39.4 Phase 3 — Deterministic Backend Binding + Foreground Coordinator

Implement：

- deterministic backend id；
- durable backend binding before submit；
- foreground synchronous coordinator；
- coordinator crash recovery；
- cancellation semantics；
- no detached execution。

Crash injection must PASS before next phase。

## 39.5 Phase 4 — Effect Boundary + Outcome + Approval

Use generic reversible Settings path to prove:

- pre-effect failure；
- verifier success；
- verifier infrastructure failure classification；
- reconcile；
- policy weakening rejection；
- request mutation rejection。

Then implement generic unsafe boundary support.

## 39.6 Phase 5 — TikTok BUSINESS Migration

Add：

```text
tiktok.publish
```

要求：

- existing Publisher `COMMITTING` remains a lower-layer marker, but must occur only **after** capability `EFFECT_BOUNDARY_CROSSED` is durable；
- existing explicit/one-URL authorization bound to request hash；
- Profile verification retained；
- exactly-one Publish attempt retained；
- legacy business path may remain as wrapper but cannot bypass arbiter；
- no second production implementation.

## 39.7 Phase 6 — Discovery / Health / Closure

最后才加入：

- `capctl list/describe/doctor` complete UX；
- on-demand `node-health.json` schema v2；
- READY/DEGRADED/BUSY/BLOCKED_RECONCILE/UNAVAILABLE/UNKNOWN derivation；
- protocol/contract compatibility advertisement；
- `alive != ready` diagnostics；
- explicit `capctl gc`；
- permission/storage/clock health；
- static/dynamic discovery merge；
- single external Gateway/control-plane boundary verification；
- docs；
- final acceptance；
- CHECKPOINT update；
- Git closure。

## 39.8 v0.5 -> v0.6 Upgrade / Rollback

Upgrade gate：

```text
record accepted v0.5 baseline
stop new legacy mutating jobs
prove no legacy UI mutator running
reconcile legacy COMMITTING/uncertain jobs
deploy approved Rev3.6 code/config
validate runtime dirs owner/mode
initialize NEW state_epoch + revision baseline
migrate legacy TikTok ui_lease to shared arbiter
keep Gateway BUSINESS disabled
run Settings + concurrency + TikTok DRY_RUN gates
then enable TikTok BUSINESS
```

复用现有 android-ui.lock path；旧 lock content 不是 Rev3.6 durable claim。旧 legacy jobs 不转换 capability jobs。

Rollback only if no active Rev3.6 mutator, no unresolved Rev3.6 effect boundary, no Rev3.6 backend running。Rollback 后未来 v2 token 使用前 durable new/bump state_epoch。Catalog/runtime 必须来自兼容 Git baseline。

---

# 40. Implementation Sprints

## 40.1 Sprint 0 — Validation Tooling & Baseline (Phase 0B)

**Authorization boundary：本 Sprint 仅授权 validation tooling/tests/evidence collection，不授权任何 production runtime behavior change。**

Deliverables：

- canonical resource inventory；
- authoritative fact matrix；
- current UI lease inventory；
- frozen MSA scope；
- acceptance baseline；
- free-space/job/evidence baseline + LOW_SPACE threshold；
- filesystem ownership/mode baseline；
- durability/fsync baseline：
  - fsync count per representative workflow；
  - fsync latency P50/P95/max；
  - parent-dir fsync latency；
  - total durability overhead；
- fault-injection harness capable of injecting failure/crash at named durability boundaries；
- full legacy UI-mutation call-site inventory，特别是 `pressHome` / `pressBack`；
- full TikTok subordinate UI-job inventory/provenance path；
- v0.5 -> v0.6 upgrade/rollback runbook；
- machine-executable implementation preflight checks。

Exit：

```text
no unresolved dual-lock path in the BASELINE inventory
no unresolved SOT ambiguity in the documented current system
fault-injection HARNESS SELF-TEST PASS (not production named-boundary PASS yet)
semantic-v1 reference fixed-vector tool PASS
legacy pressHome/pressBack inventory complete (migration itself is Sprint 1)
TikTok mutating subordinate-job inventory complete (provenance enforcement itself is later Sprint work)
pre-implementation scripts produce machine-readable PASS/FAIL
no Phase 0B change alters production runtime behavior
```

Sprint 0/Phase 0B **不得**要求尚未实现的 Rev3.6 production behavior 已经 PASS；它的职责是建立 baseline、工具、fixtures 与 empirical feasibility evidence。

## 40.2 Sprint 1 — android_ui Arbiter + State Integrity

Deliverables：

- shared arbiter；
- durable claim + `claim_id`；
- Core `resource_guard` ownership assertion；
- state epoch/revision/hash；
- semantic-v1 exact canonical schema + fixed vectors；
- token/AUTO guard with boot-aware monotonic age；
- ADMIN mutating/unknown epoch invalidation；
- mutation journal prepare/commit；
- revision commit ordering；
- `pressHome` / `pressBack` mutation reclassification；
- stale-state / ownership errors。

Exit：

- concurrent UI mutation blocked；
- direct mutating Core call without claim blocked；
- manual UI drift blocked；
- `pressHome` / `pressBack` invalidate old state tokens；
- crash prepared-without-commit reconciled；
- current TikTok DRY_RUN regression remains PASS。

## 40.3 Sprint 2 — Capability Contract / Job / Policy

Deliverables：

- catalog；
- minimal static `execution_profile`（Y700 placement / foreground / readiness requirements / no implicit alternate runtime）；
- exact capability version + runtime contract compatibility check；
- `submission_id` admission registry + short-lived admission lock；
- deterministic capability job ID；
- atomic capability job；
- request/policy hash；
- policy precedence；
- BUSINESS/INTERNAL/ADMIN classification；
- bounded admission lock；
- CLI/Python error envelope；
- durability/storage/permission preflight。

Exit：

- caller cannot weaken policy；
- activated request mutation fails closed。

## 40.4 Sprint 3 — Coordinator / Backend Binding

Deliverables：

- foreground runtime；
- deterministic backend id；
- `backend.json` before resource claim and before submit；
- same-backend recovery；
- read-only `status` semantics；
- explicit `reconcile` recovery semantics；
- cancellation/resource release rules；
- subordinate provenance/SUBJOB_BOUND；
- bounded status lookup。

Exit：

all backend crash-window injection tests PASS。

## 40.5 Sprint 4 — Outcome / Approval / Unsafe Boundary

Deliverables：

- single-authority `effect-boundary.json`；
- exact approval binding + boundary-time revalidation；
- approval consumption via effect-boundary record；
- TikTok ordering: effect boundary -> Publisher COMMITTING -> Publish；
- verifier contract；
- final terminal outcomes vs non-terminal `RECONCILE_REQUIRED` semantics。

Exit：

- approval mismatch cannot dispatch effect；
- verifier infrastructure failure after boundary cannot become FAILED/retry。

## 40.6 Sprint 5 — Settings Golden Acceptance

Settings 是 generic architecture proof，不必成为长期 public BUSINESS capability。

Required：

```text
persist backend binding
-> acquire android_ui
-> submit exact backend
-> observe/token
-> guarded change light/dark
-> verify revision/hash
-> guarded restore
-> verify
```

并包含：

- out-of-band human/state drift injection；
- crash injection；
- resource contention。

## 40.7 Sprint 6 — TikTok Migration / Closure

Required：

- `tiktok.publish` BUSINESS contract；
- approval hash binding；
- durable effect boundary；
- existing Profile reconcile；
- frozen DRY_RUN behavior；
- cold-start regression；
- duplicate side-effect regression；
- legacy/gateway concurrency test；
- readiness advertisement schema/status derivation；
- stale-ready snapshot does not authorize execution；
- runtime protocol mismatch fails before backend side effect；
- secure boundary regression：no new direct remote backend exposure；
- pre-submit terminalization + claim-session rollover + STOPPED/ZOMBIE classification tests。

---

# 41. Acceptance Tests

## A0 — Existing baseline

- Bridge v2 regression PASS；
- generic Settings acceptance PASS；
- TikTok DRY_RUN frozen acceptance 不回退。

## A1 — Stale revision

```text
observe token revision=N
other automation commits mutation -> N+1
old token attempts mutation
```

Expected：

```text
STALE_STATE_REVISION
action_attempts=0
```

## A2 — Out-of-band human/system UI drift

```text
observe token
manual/system changes semantic state
revision unchanged
mutation
```

Expected：

```text
STALE_STATE_HASH
action_attempts=0
```

## A3 — Concurrent UI ownership

两个 production mutating workflows 同时开始。

Expected：

```text
exactly one semantic owner
other waits/fails DEVICE_BUSY
no overlapping Android mutation
```

## A4 — Legacy TikTok vs Gateway

Expected：

```text
both use same canonical android-ui.lock/claim
only one proceeds
```

## A5 — Gateway crash while backend alive

Expected：

```text
flock may disappear
durable claim remains
second workflow must inspect backend
no competing UI workflow starts
```

## A6 — Crash after backend submit before Gateway acknowledgement

Expected：

```text
same deterministic backend discovered
no second backend created
```

## A7 — Request mutation after activation

Expected：

```text
JOB_CONTRACT_VIOLATION
no new side effect
```

## A8 — Caller weakens policy

Attempt：

```text
approval NONE
verification NONE
resource none
replay SAFE
```

Expected：

```text
POLICY_WEAKENING_NOT_ALLOWED
```

## A9 — Approval hash mismatch

Expected：

```text
APPROVAL_INVALID
Publish action_attempts=0
```

## A10 — Mutation crash after prepare

```text
MUTATION_PREPARED
-> action maybe occurs
-> process crash before commit
```

Expected：

```text
no blind replay
actual-state reconcile
ambiguous -> RECONCILE_REQUIRED
```

## A11 — Crash immediately before unsafe effect boundary

Expected：

retry only when backend durable evidence proves effect was not dispatched and policy permits.

## A12 — Crash after unsafe effect boundary

Expected：

```text
no automatic external-effect retry
reconciliation path
```

## A13 — Verifier infrastructure failure after Publish

Expected：

```text
RECONCILE_REQUIRED
not FAILED
not OUTCOME_NOT_ACHIEVED
not automatic retry
```

## A14 — Positive not-achieved outcome

Only if capability verifier can positively prove business outcome absent.

Expected：

```text
OUTCOME_NOT_ACHIEVED
```

否则必须 reconcile。

## A15 — Cancellation while backend alive

Expected：

```text
CANCELLING
resource retained
backend safe termination proof required
```

## A16 — result-before-archive race

Expected：

status never returns false `JOB_NOT_FOUND`。

## A17 — TikTok production regression

至少保持当前已接受的 functional safety：

- DRY_RUN final publish hard stop；
- no implicit selector first match；
- PUBLIC production semantics 保持；
- exactly-one COMMIT attempt；
- ambiguous outcome no blind retry；
- Profile reconciliation PASS。

Cold-start run count沿用当前项目已接受 gate；若 implementation 影响 TikTok path，则重新执行相同 gate。

## A18 — Expired intent before execution

```text
expires_at < now
backend not submitted
no mutation started
```

Expected：

```text
EXPIRED
backend_job_created = false
Android side effect = 0
```

## A19 — TTL expires after unsafe boundary

Expected：

```text
must not become EXPIRED
must continue verify/reconcile
no automatic retry
```

## A20 — Node health is advisory

Inject stale/degraded health snapshot, then execute a job whose real preflight differs.

Expected：

```text
execution-time preflight is authoritative for whether execution may proceed
health snapshot alone never produces VERIFIED
```

## A21 — Transport independence

Where supported by the test harness, interrupt the invoking transport after durable capability/backend state exists.

Expected：

```text
no correctness state is stored only in transport memory
explicit later `status` can inspect the durable job; explicit `reconcile` can classify/advance it
```

---


## A22 — Backend binding precedes resource claim

Expected:

```text
backend.json is durable before android_ui claim contains backend_job_id
claim never references an unbound backend identity
```

## A23 — Core direct mutation bypass rejected

Invoke protocol v2 mutating `ui_job` without valid `resource_guard`.

Expected:

```text
RESOURCE_OWNERSHIP_REQUIRED / MISMATCH
action_attempts=0
no revision change
```

## A24 — Same owner, stale claim_id rejected

Release and reacquire `android_ui` for the same capability/owner, then replay a mutation request containing the old claim ID.

Expected:

```text
RESOURCE_OWNERSHIP_MISMATCH
action_attempts=0
```

## A25 — Reconcile is non-terminal until resolved

Force unsafe outcome ambiguity.

Expected:

```text
state = RECONCILE_REQUIRED
job stays active
no final result.json
```

Then supply positive success evidence through explicit reconcile.

Expected:

```text
VERIFIED
result.json written once as final marker
archive/verified
```

## A26 — status is read-only

Repeated `capctl status` against an unresolved job.

Expected:

```text
no backend submit
no claim release
no state transition
no journal recovery mutation
```

## A27 — Effect-boundary / Publisher ordering

Inject crash points:

```text
before capability effect boundary
after capability effect boundary / before Publisher COMMITTING
after Publisher COMMITTING / before Publish click
```

Expected:

```text
no path exists where Publisher unsafe marker/click occurs
while capability effect boundary is absent
```

## A28 — TTL after resource wait

Let job wait until `expires_at`, then make `android_ui` available.

Expected:

```text
recheck TTL
EXPIRED before backend submit
release resource
zero backend/UI side effect
```

## A29 — Approval expires while waiting

Approval valid at initial precheck, then expires before unsafe boundary.

Expected:

```text
final boundary-time approval validation fails
no effect-boundary.json
no Publisher COMMITTING
no Publish click
```

## A30 — OUTCOME_NOT_ACHIEVED does not reuse approval

Consume a single-use approval at effect boundary, then positively prove outcome not achieved.

Expected:

```text
OUTCOME_NOT_ACHIEVED
no automatic second Publish
same approval cannot be reused
new attempt requires new job + new approval
```

## A31 — pressHome / pressBack are mutations

Execute guarded `pressHome` or `pressBack`.

Expected:

```text
MUTATION_PREPARED
revision increments after successful postcondition
MUTATION_COMMITTED
old state token becomes stale
```


## A32 — No nested android_ui reacquisition within one ownership session

Run TikTok through Gateway after shared arbiter migration.

Expected:

```text
one top-level claim_id for the current foreground ownership session
Publisher/Controller does not reacquire canonical android-ui.lock while that session is active
all mutating UI sub-jobs created in that session carry/assert that exact current claim_id
no deadlock / second ownership path
```

A later explicit reconcile after the original claim has been safely released is a **new ownership session** and is covered separately by A66.

## A33 — Top-level backend with multiple subordinate UI jobs

Run `tiktok.publish`.

Expected:

```text
one capability backend.json top-level publisher binding
multiple known subordinate UI workflow job IDs may exist
all correlate to same capability/backend
no subordinate job is treated as a second top-level retry
```

## A34 — Legacy and Capability claim schema compatibility

Acquire shared `android_ui` through:

```text
legacy TikTok entrypoint (owner_kind=LEGACY)
```

and separately through:

```text
Gateway capability (owner_kind=CAPABILITY)
```

Expected:

```text
same canonical claim schema/path
same exact-current-claim ownership enforcement in Core
legacy path does not require a fake capability_job_id
Gateway path requires real capability_job_id
```

## A35 — Durable claim ordering crash injection

Inject crash points:

```text
during temp claim write
after claim file fsync / before rename
after rename / before parent-dir fsync
after durable claim / before backend submit
during claim cleanup before parent-dir fsync
```

Expected:

```text
backend submission never precedes durable claim
no second UI owner is admitted while old backend may run
stale claim after cleanup ambiguity may conservatively block, but never permits unsafe concurrency
```

## A36 — Transport response loss / same submission retry

Flow：

```text
caller creates submission_id=S
-> Gateway activates capability job J
-> invoke response is lost
-> caller retries exact request with submission_id=S
```

Expected：

```text
same capability_job_id J
no second capability job
no second top-level backend
```

## A37 — Concurrent same submission admission

Two callers concurrently send：

```text
same submission_id
same canonical request
```

Expected：

```text
short-lived admission lock serializes compare/create
exactly one durable submission binding
exactly one deterministic capability job
both callers resolve to the same job
```

Then send：

```text
same submission_id
different payload / expires_at / requested_by
```

Expected：

```text
SUBMISSION_ID_CONFLICT
zero new backend side effect
```

## A38 — Admission crash injection

Inject crashes：

```text
before submission binding write
after binding fsync / before rename
after binding rename / before parent-dir fsync
after durable binding / before capability job activation
after capability activation / before invoke response
```

Expected：

```text
no two capability jobs for one submission_id
same-submission retry converges to one deterministic job
no backend starts before normal policy/resource gates
```

## A39 — Semantic fingerprint dynamic-noise immunity

Change only non-allowlisted dynamic attributes：

```text
clock
battery percentage
animation/transient bounds
unwatched tree attributes
```

Expected：

```text
semantic hash unchanged
```

Change a watched safety property：

```text
foreground activity
selector cardinality
checked/selected state
capability-declared property
```

Expected：

```text
semantic hash changes
```

## A40 — Heartbeat/PID evidence never acts as a lease

Simulate：

```text
stale backend heartbeat
missing coordinator PID
old claim remains
backend liveness not positively resolved
```

Expected：

```text
claim is NOT automatically released
new UI mutation remains blocked
doctor/reconcile exposes evidence
explicit recovery required
```

## A41 — Durability failure before backend submit
Inject EIO/ENOSPC at submission/backend/claim boundaries. No backend/mutation before durable prerequisites.

## A42 — Revision persistence failure after UI mutation
Expected STATE_INTEGRITY_UNAVAILABLE + RECONCILE_REQUIRED；future mutation blocked until epoch reset.

## A43 — Effect/result persistence failure
Effect-boundary fsync failure -> external effect attempts=0；terminal-result fsync failure after effect -> RECONCILE_REQUIRED, no effect retry.

## A44 — Permission integrity
Owner/mode/symlink tamper -> RUNTIME_PERMISSION_INTEGRITY_ERROR, mutation attempts=0, no silent repair.

## A45 — GC safety
GC never removes active/reconcile/current claim；submission binding retention >= query retention.

## A46 — ADMIN invalidates tokens
Mutating/unknown ADMIN path bumps epoch before dispatch；epoch durability failure -> ADMIN attempts=0.

## A47 — Time source
Same-boot wallclock jump does not alter boottime TTL deadline；reboot invalidates old token via boot mismatch.

## A48 — semantic-v1 fixed vectors
Vector1=`sha256:074e74b0f725954b789fea7d905715c7e096c4ab159029a1c6c8ef8a6b610b66`；Vector2=`sha256:6bab7e2cd22bb7e2804f75638edfda2546f73802003c57fde3ecbdd322f32fd4`。

## A49 — Subordinate provenance
Missing parent/top-backend/resource_guard on mutating subjob -> SUBORDINATE_BINDING_INVALID, attempts=0.

## A50 — Admission lock bounded wait
Hold `admission.lock` beyond the **effective configured admission timeout** -> `ADMISSION_LOCK_TIMEOUT`, no capability job/backend creation. The same submission retry must reuse the original `submission_id`. Test runs cover 5000/10000/15000ms deployment candidates.

## A51 — Upgrade / rollback gate
Migration refuses unresolved legacy mutation/COMMITTING；Gateway BUSINESS disabled until gates pass；rollback refuses unresolved Rev3.6 active/effect state.

## A52 — Official Controller transport/busy retry contract

Simulate：

```text
invoke response timeout
DEVICE_BUSY
connection reset
RESOURCE_RECONCILE_REQUIRED
```

Expected：

```text
same business intent reuses original submission_id
bounded backoff only
no new capability job due to retry
after retry budget -> exact status/doctor/reconcile path
no fresh submission_id while prior intent unresolved
```

## A53 — Unexpected blocking overlay guard

Baseline token：
```text
blocking_overlay_present=false
```

Inject before final mutation：

```text
runtime permission dialog
system modal
unexpected app dialog/top-level focusable window
```

while Activity/package remain unchanged.

Expected：

```text
UNEXPECTED_BLOCKING_OVERLAY
action_attempts = 0
semantic hash/precondition changes
```

Expected dialog explicitly allowed by current workflow contract may proceed only if its signature matches.

## A54 — In-app modal fallback

Create a blocking app modal that is not exposed as a distinct top-level accessibility window but matches a versioned `blocking_selector`.

Expected：

```text
mutation blocked
action_attempts = 0
```

## A55 — Zombie/PID reuse diagnostics

Cases：

```text
PID missing
PID reused with different proc_start_ticks
process state T (stopped)
process state Z (zombie)
process identity matches but backend progress unknown
```

Expected：

```text
doctor classifies DEAD / PID_REUSED / STOPPED / ZOMBIE / HUNG_OR_UNKNOWN
doctor/status themselves never release claim
when exact backend STOPPED/terminal/proven-not-created + no live mutator are also present, recommended_action=RECONCILE
explicit capctl reconcile may then release deterministically under Section 16.6
STOPPED/hung/unreadable evidence keeps claim until positive termination proof
```


## A56 — Alive does not imply READY

Keep the relevant process/device reachable, but break one mandatory readiness dependency (for example UI protocol/instrumentation compatibility).

Expected：

```text
process may be alive/reachable
capability status != READY
CAPABILITY_NOT_READY or RUNTIME_CONTRACT_MISMATCH
backend/UI side effect = 0 when failure is known pre-start
```

## A57 — Stale READY advertisement cannot authorize mutation

Create a fresh `READY` snapshot, then change runtime state before invoke/mutation.

Expected：

```text
old READY remains advisory only
execution-time preflight/Core guard detects current state
no unsafe action is authorized by node-health alone
```

## A58 — Optional degradation is semantic-no-op only

Disable a component explicitly classified non-safety optional (diagnostic/telemetry enrichment), while all mandatory capability requirements still pass.

Expected：

```text
capability may report DEGRADED
exact degradation reason journaled
minimum_policy unchanged
verifier semantics unchanged
no safety check skipped
```

Then disable approval/verification/resource/state-integrity durability.

Expected：

```text
must NOT downgrade to DEGRADED-and-continue
fail closed / existing reconcile semantics
```

## A59 — Exclusive/uncertain state forbids transparent fallback

Inject runtime loss after a backend/mutation may have started or after `EFFECT_BOUNDARY_CROSSED`.

Expected：

```text
no second top-level backend
no new submission_id for the same intent
no alternate runtime execution
RECONCILE_REQUIRED / exact status-reconcile path
```

## A60 — Capability advertisement compatibility

`capctl list/describe/doctor` must expose static placement/readiness contract plus current dynamic readiness without creating a second SOT.

Expected：

```text
Catalog remains authority for static execution_profile/minimum_policy
node-health remains derivative/advisory
protocol mismatch -> UNAVAILABLE
stale/boot-mismatch -> UNKNOWN
resource contention -> BUSY
unresolved ownership/effect ambiguity -> BLOCKED_RECONCILE
```

## A61 — Single external boundary regression

Where a remote control path exists in the deployment test environment, verify that enabling Gateway/discovery does not expose Bridge/UI/root primitive listeners as independent remote APIs.

Expected：

```text
remote entry -> trusted control/Gateway boundary
internal primitive surfaces remain local/non-public
```

## A62 — Backend bound but never submitted: terminalization matrix

Create a durable `backend.json`, then crash before resource acquisition/backend submit. Positive-prove exact backend never existed.

Cases / Expected：

```text
TTL elapsed before submit      -> EXPIRED
valid cancel before submit     -> CANCELLED
deterministic pre-submit error -> FAILED
backend existence UNKNOWN      -> RECONCILE_REQUIRED
```

In every case：

```text
backend.json remains immutable
status never submits backend
no second backend ID allocated
```

## A63 — Deterministic reconcile releases a dead claim without ADMIN

Crash Coordinator/backend so durable claim remains. Provide evidence：

```text
owner_process_state = DEAD (or PID_REUSED / ZOMBIE)
backend_liveness = STOPPED / terminal / proven-not-created
no subordinate mutator alive
```

Expected：

```text
capctl reconcile acquires canonical flock
revalidates exact claim_id
unlinks claim + fsync parent
records RESOURCE_RELEASED_BY_RECONCILE
ADMIN force-reset not required
```

Negative case：backend/process evidence UNKNOWN/HUNG/UNREADABLE -> claim retained.

## A64 — Fingerprint profile watched-field determinism

Using Appendix A Vector 2 profile with no optional watched text fields：

```text
runtime element.text changes
runtime element.content_desc changes
```

Expected：canonical JSON/hash unchanged because keys are forcibly omitted.

Using a profile that watches `text/content_desc`：

Expected：

```text
value change -> hash change
runtime null -> explicit JSON null
accessor unavailable -> STATE_FINGERPRINT_UNAVAILABLE, attempts=0
profile mismatch -> STATE_TOKEN_PROFILE_MISMATCH, attempts=0
```

## A65 — RECONCILE_REQUIRED status contract

Force blocked ambiguous outcome.

Expected：

```json
{
  "lifecycle_state": "RECONCILE_REQUIRED",
  "terminal": false,
  "result_present": false,
  "next_action": "RECONCILE"
}
```

Official Controller must stop ordinary completion polling and enter reconcile; it must not wait for `result.json` to appear automatically.

## A66 — Reconcile claim-session rollover rejects stale subjobs

Run initial UI phase under `claim_id=C1`, release after backend stopped, then explicit reconcile reacquires `claim_id=C2` for Profile verification.

Expected：

```text
new reconcile/verify subjob binds C2
same capability_job_id/top_backend_job_id preserved
old mutating subjob carrying C1 -> RESOURCE_OWNERSHIP_MISMATCH / zero attempts
no second Publish/external effect
journal records RESOURCE_REACQUIRED C1 -> C2
```

## A67 — Suspend invalidates stale state token

Observe a token, suspend/deep-sleep device longer than `max_age_ms`, resume.

Expected：

```text
CLOCK_BOOTTIME age includes suspend
STATE_TOKEN_EXPIRED
attempts=0
AUTO path performs fresh screen/keyguard/foreground/overlay observation before re-evaluating action
```

## A68 — Benign secondary windows do not create overlay false positives

Cases：

```text
IME visible during expected text input
transient Toast/non-focusable notification window
known allowlisted non-intercepting accessibility overlay
```

Expected：presence alone does not set `blocking_overlay_present=true`.

Control cases：unexpected focused system dialog, permission dialog, or unknown focus/input-intercepting overlay -> `UNEXPECTED_BLOCKING_OVERLAY`, attempts=0.

## A69 — Admission lock under I/O pressure

Stress admission binding during TikTok cold-start / fsync pressure and concurrent same-submission retries.

Expected：

```text
measure p99 admission critical-section hold
p99 < 0.5 * configured timeout before Implementation Authorization
if not, choose 10000/15000ms deployment value and rerun
ADMISSION_LOCK_TIMEOUT remains retryable with same submission_id
no duplicate capability/backend job
```

## A70 — Cancel vs unsafe-boundary race linearization

Run concurrent `capctl cancel` and Publisher `before_irreversible`.

Expected:

```text
exactly one durable winner
cancel.json wins first -> no effect-boundary / no Publish; CANCELLING then safe terminalization
effect-boundary wins first -> CANCEL_AFTER_EFFECT_BOUNDARY; never CANCELLED from that request
crash between steps -> recovery determined only from durable cancel/effect-boundary facts
```

## A71 — ADMIN force-reset requires quiescence

Inject an in-flight mutating subjob that already passed Core ownership guard.

Expected:

```text
best-effort stop alone is insufficient
if old mutator may still execute -> DEVICE_UI_RUNTIME_UNSAFE
claim remains
new mutating BUSINESS work blocked
after reboot/proven quiescence -> exact claim may be released
```

## A72 — state.json crash-safe lifecycle persistence

Inject crash/EIO:

```text
during state temp write
after temp fsync / before rename
after rename / before parent-dir fsync
corrupt/truncated state.json
```

Expected:

```text
no RAM-only lifecycle authority
status never silently repairs
STATE_STORE_CORRUPT/DURABILITY_IO_ERROR
explicit reconcile rebuilds from durable authoritative facts only
state_revision monotonic
```

## A73 — Phase 0 authorization boundary

Attempt during Phase 0B:

```text
validation script/test change
production Core/Gateway runtime change
BUSINESS capability enablement
```

Expected:

```text
tooling/test change allowed after Freeze Approval
production behavior change rejected until separate Implementation Authorization
```

## A74 — LEGACY claim resource-only reconcile

Create `owner_kind=LEGACY`, `capability_job_id=null`, then crash owner.

Expected:

```text
capctl reconcile-resource --claim-id <exact>
positive-stop proof required
safe proof -> resource released
no fake capability job
no business outcome terminalization
```

## A75 — App/UI contract mismatch

Change installed TikTok version/signing/UI contract outside Catalog accepted set.

Expected:

```text
APP_UI_CONTRACT_MISMATCH
readiness=UNAVAILABLE
backend/UI action attempts=0
selector absence alone never means safe
```

## A76 — Android Host / chroot BOOTTIME equivalence

Measure on same boot before and after suspend.

Expected:

```text
same boot_id
documented milliseconds/epoch contract
host/chroot elapsed deltas within Phase-0 tolerance
mismatch -> fail closed / Implementation Authorization blocked
```

## A77 — Reboot with CLOCK_SUSPECT and pre-submit job

Persist an unsubmitted job, reboot, then make realtime clock suspect.

Expected:

```text
no backend submit
no EXPIRED decision from suspect clock
existing pre-submit lifecycle preserved
phase_reason_code=CLOCK_SUSPECT_PRE_SUBMIT
next_action=REPAIR_CLOCK
after clock repair, exact same submission/request may resume only after never-created + no-uncertainty proof and full pre-submit recheck
```

## A78 — Reconcile dwell observability

Leave one resource-free capability in `RECONCILE_REQUIRED`.

Expected:

```text
status exposes reconcile_since/reconcile_age_ms
doctor exposes oldest_reconcile_age_ms
threshold changes alert/escalation only
no auto terminalize / GC / release / replay
```

## A79 — Backend never-created positive proof

Cases:

```text
exact lookup absent + SOT healthy + retention guaranteed
exact lookup absent + permission error
exact lookup absent + retention uncertainty
corrupt partial backend record
```

Expected:

```text
only first case may establish never-created proof
all uncertain cases -> BACKEND_STATE_UNKNOWN / RECONCILE_REQUIRED
plain ENOENT is never sufficient by itself
```

## A80 — Cross-lock non-nesting / deadlock regression

Exercise concurrent:

```text
cancel/effect-boundary transition
resource reconcile cleanup
ADMIN reset cleanup
```

Expected:

```text
no path blocks on android-ui.lock while holding transition.lock
no path blocks on transition.lock while holding android-ui.lock
resource mutation completes/releases canonical flock before lifecycle transition lock acquisition
no ABBA deadlock
```

## A81 — CLOCK_SUSPECT pre-submit recovery is not a dead end

Persist a pre-submit job, reboot with suspect realtime, then repair the clock.

Expected:

```text
while suspect: no submit/no EXPIRED; pre-submit state preserved; next_action=REPAIR_CLOCK
after repair: exact same submission/request re-enters admission
backend never-created + no uncertainty + TTL/readiness PASS -> same job continues
RECONCILE_REQUIRED/unknown backend/effect uncertainty -> invoke must not resume execution
```

## A82 — Terminal result linearization / archive race

Inject crash at every terminalization step:

```text
before result temp fsync
after temp fsync / before rename
after rename / before parent-dir fsync
after result durable / before archive move
during archive move parent fsync
```

Expected:

```text
terminal=true only after durable result.json linearization
state.json never creates a terminal-without-result window
active/<job> + durable result is reported terminal=true
archive placement failure never changes final outcome
result outcome immutable after linearization
```

## A83 — App/UI contract TOCTOU after READY

Early preflight returns READY/MATCH, then update/reinstall the target app before a later mutating step / external commit.

Expected:

```text
JIT Adapter/workflow compatibility check detects mismatch
APP_UI_CONTRACT_MISMATCH
not-yet-dispatched mutation/effect attempts=0
stale node-health READY cannot authorize the action
```

## A84 — Same-submission pre-submit continuation admission

Create an active `BACKEND_BOUND` job with `CLOCK_SUSPECT_PRE_SUBMIT`, positive-prove backend never-created, then repair clock and invoke exact same request/submission.

Expected:

```text
admission resolves same capability_job_id
existing active job is not merely returned without progress
safe pre-submit gates are re-run
if valid -> SAME job continues toward backend submit
if backend/effect uncertainty appears -> no continuation; status/reconcile path
no second capability/backend identity
```

## A85 — Late cancel/reconcile after terminal result

Make `result.json` durable, pause before archive move, then issue cancel and capability reconcile.

Expected:

```text
both observe durable terminal result under transition serialization
cancel.json is not newly written
final outcome is unchanged
no capability lifecycle mutation
archive placement may complete independently
```

## A86 — Phase 0 gate is executable before production implementation

Evaluate the Authorization Gate against a repository where Rev3.6 production runtime changes do not yet exist, but Phase 0B tooling is present.

Expected:

```text
P0B_PRE_IMPLEMENTATION checks can PASS using baseline/synthetic/reference evidence
SPRINT_GATED checks may be NOT_IMPLEMENTED/NOT_APPLICABLE_FOR_PHASE0 but must have executable contracts/fixtures
Authorization Gate does not require pressHome migration, claim-session runtime, readiness runtime, or production fault boundaries to already PASS
Sprint 1 authorization can therefore be decided without circular dependency
later Sprint CI/DoD still blocks on the full production checks
```

## A87 — Terminal result authority vs state/result corruption

Cases:

```text
valid durable result + corrupt state.json
corrupt/unreadable result + intact terminal-looking state/archive path
```

Expected:

```text
valid result wins; terminal outcome remains final despite state corruption
corrupt result -> RESULT_STORE_CORRUPT, terminal not trusted, no outcome guessing from archive/state
no external replay
reconcile may republish only with independent exact evidence
```

## A88 — Status consistent snapshot around terminal publish

Pause terminal writer at:

```text
after result rename
before parent-dir fsync
```

Concurrently invoke `capctl status`.

Expected:

```text
writer holds transition LOCK_EX
status waits boundedly on LOCK_SH and cannot observe/report premature terminal
status after writer fsync/release sees terminal=true
shared-lock timeout returns transient diagnostic, never unlocked terminal inference
status remains read-only
```

# 42. Performance / Engineering Guardrails

v0.6 不把任意新 P95 数值写成 release requirement。

原则：

1. correctness > tens-of-ms Gateway overhead；
2. Sprint 0 先记录 baseline；
3. 新 bookkeeping 应保持 local filesystem operations 量级；
4. 如 Gateway overhead 导致现有 workflow timeout / materially degraded usability，必须诊断；
5. 不因性能优化引入 daemon/socket/MQ，除非后续有 measured evidence；
6. `result.json` / journal 应记录可自然测得的 Gateway timing，供 regression 比较，不建立独立 metrics service；
7. Sprint 0 与 regression 必须记录 durability 指标：

```text
durability_fsync_count
durability_fsync_ms_total
durability_fsync_ms_max
durability_parent_dir_fsync_count
```

8. 任何 future fsync 合并/批处理只能在证明**不改变 durable-before-effect ordering**后讨论；v0.6 不允许把多个 safety boundary 延迟到动作之后统一 flush。

Bridge v2 Sprint 6B measurement gate 不变。

## 42.1 Measurement-Gated Execution Placement

Rev3.5 从 Backburner 吸收一个重要算法原则，但 **只作为未来 placement 的 gate，不在 v0.6 实现 router**。

任何未来将 task 从 canonical runtime 改投另一个 runtime（例如 Mac / Y700 / cloud），必须比较：

```text
T_remote
=
T_setup
+ T_queue
+ T_transfer_in
+ T_compute_remote
+ T_transfer_out
+ T_sync
+ T_recovery_risk_margin
```

只有同时满足以下条件才值得 offload：

```text
semantic contract identical
AND state is available or safely reconstructible before side effect
AND required safety policy is preserved
AND T_remote + safety_margin < T_canonical
AND memory/thermal/battery/foreground headroom is acceptable
```

threshold 必须：

- per capability / workload size / hardware class；
- 来源于真实 benchmark，而不是理论 TOPS/CPU/GPU 数字；
- 记录 measurement date、software version、device profile；
- benchmark stale/unknown 时回到 canonical placement；
- 不能通过 threshold 绕过 `alternate_runtime_fallback=NONE`、resource ownership、backend identity 或 effect-boundary rules。

这保留 Backburner “小任务留本地、大任务达到 break-even 才 offload”的方法论，同时避免在 Y700 v0.6 提前建设 scheduler。

---

# 43. Failure Modes

## 43.1 FM-1 user leaves screen

state hash mismatch -> block。

## 43.2 FM-2 another automation mutates screen

revision mismatch / resource claim -> block。

## 43.3 FM-3 Gateway process dies

flock release 不等于 semantic claim release；inspect backend。

## 43.4 FM-4 backend job exists but Gateway did not record result

lookup deterministic backend；不创建第二 backend。

## 43.5 FM-5 action may have occurred but mutation commit absent

reconcile actual Android state。

## 43.6 FM-6 unsafe effect may have occurred

`RECONCILE_REQUIRED`。

## 43.7 FM-7 verifier cannot reach TikTok/Profile

after boundary -> reconcile，不推断 failure。

## 43.8 FM-8 device-state corruption

fail closed；explicit reset/new epoch；旧 token 全部 invalid。

## 43.9 FM-9 admin bypass modifies UI

state continuity 无法证明时 bump epoch。

## 43.10 FM-10 user touch occurs in micro-window after final guard

无法完全消除。

v0.6 通过：

- semantic re-observe near mutation boundary；
- exclusive automation ownership；
- narrow mutation window；
- postcondition；
- unsafe reconciliation；

降低风险，但不宣称能够锁住 human touch。

## 43.11 FM-11 coordinator hang / stale liveness evidence

如果 coordinator 被 SIGSTOP、死锁或 backend heartbeat stale：

```text
availability may degrade
```

但系统不能把：

```text
heartbeat timeout
PID disappearance
claim age
```

单独解释为 ownership release permission。

正确行为：

```text
doctor/status expose evidence and never mutate ownership
explicit reconcile combines exact process + backend + subordinate-job facts
positive stop proof -> release exact claim deterministically
unknown/unreadable/hung -> keep claim / fail closed
```

因此这里接受的是“**无法证明 stopped 时** Safety > Availability”，不是“只要发生 Coordinator crash 就必须人工恢复”。当 Section 16.6 的 positive-proof 条件成立时，正常 `capctl reconcile` 就应恢复可用性；`ADMIN_FORCE_RESET` 只处理无法建立 positive proof 或需要 coercive stop 的异常。

## 43.12 FM-12 caller transport retry storm

如果 caller 因 response timeout 重发同一 intent：

```text
MUST reuse the same submission_id
```

Gateway admission 将其收敛为同一个 capability job。

如果 caller 故意生成新的 `submission_id`，系统把它视为新的业务 intent；对于 unresolved prior `RECONCILE_REQUIRED`，上层 controller 规范禁止通过新 intent 绕过 reconcile。

## 43.13 FM-13 storage I/O / ENOSPC
Before effect -> no effect；after possible effect -> reconcile；state-store durability loss -> block mutation lane。

## 43.14 FM-14 permission / symlink tampering
preflight/doctor fail closed；不静默修复。

## 43.15 FM-15 clock jump
TTL same boot uses boottime deadline；state-token age uses boottime；reboot invalidates old token。

## 43.16 FM-16 storage accumulation
no background GC；doctor LOW_SPACE；operator dry-run/apply GC。

## 43.17 FM-17 ADMIN emergency reset
bump epoch + audit；never assert old outcome；never auto-replay。

## 43.18 FM-18 official Controller changes submission_id on retry

对于 official Controller 属于 protocol violation：

```text
CONTROLLER_RETRY_CONTRACT_VIOLATION
```

Gateway 无法一般性识别两个不同 ID 的业务等价性，因此防线是：

```text
first-party controller persistence + bounded retry contract + operator audit
```

不因此引入 generic business-idempotency engine。

## 43.19 FM-19 Activity unchanged but blocking Dialog/Window appears

Core JIT overlay guard 在 mutation dispatch 前检测。未显式允许的 blocker：

```text
UNEXPECTED_BLOCKING_OVERLAY
action attempts = 0
```

若 platform window API 不可见，capability/workflow 的 blocking selector 作为 fallback safety guard。

## 43.20 FM-20 owner process is dead/reused/zombie

doctor 分类 process evidence；reconcile 根据 exact backend facts决定资源能否释放。`DEAD/PID_REUSED/ZOMBIE` 本身仍不是自动 lease release authority。

## 43.21 FM-21 reachable runtime but capability not ready

SSH/process/device 仍可达，但 mandatory protocol/instrumentation/permission requirement 不满足。

处理：

```text
capability != READY
fail early where knowable
execution-time guard remains authoritative
```

## 43.22 FM-22 optional auxiliary fails

只有 static/adapter contract 已明确 non-safety optional，且业务/verifier semantics 不变时允许 `DEGRADED` 继续；否则升级为 unavailable/fail-closed，不得“尽量跑”。

## 43.23 FM-23 runtime loss after unique/uncertain state exists

如果 backend/mutation 可能已经发生，或 effect boundary 已 crossed：

```text
do not route elsewhere
do not allocate another backend
do not retry external effect
-> RECONCILE_REQUIRED
```

---

# 44. Reference Flows

这些 flow 保留原始 Capability Gateway PRD 的意图，但已经用 Rev3 unified safety model 修正。

## 44.1 Settings — Generic reversible proof

```text
Controller
  ↓
android.ui.workflow / acceptance wrapper
  ↓
validate + initial TTL check
  ↓
derive + persist deterministic backend.json
  ↓
acquire canonical android_ui claim
  ↓
recheck TTL
  ↓
submit exact backend
  ↓
AUTO observe + state token
  ↓
Core resource_guard assertion
  ↓
MUTATION_PREPARED (fsync)
  ↓
toggle dark/light
  ↓
postcondition verifies semantic checked state
  ↓
device revision +1 (atomic + fsync)
  ↓
MUTATION_COMMITTED
  ↓
restore original state through same guarded mutation path
  ↓
VERIFIED
  ↓
release android_ui after backend stopped
```

若 mutation dispatch 后 crash、但无法证明 toggle 是否发生：

```text
RECONCILE_REQUIRED
```

不是 blind retry。

## 44.2 TikTok Publish — BUSINESS unsafe effect

```text
Controller / authorized workflow
  ↓
tiktok.publish immutable request
  ↓
Catalog policy + initial TTL/approval precheck
  ↓
persist deterministic backend.json
  ↓
acquire canonical android_ui claim
  ↓
recheck TTL
  ↓
submit/attach exact backend
  ↓
guarded navigation / preparation
  ↓
final state/resource guard PASS
  ↓
final approval hash/expiry validation PASS
  ↓
capability effect-boundary.json fsync
  ↓
Publisher COMMITTING fsync
  ↓
final Publish attempt exactly once
  ↓
immediate Profile verification may continue under same android_ui claim
  ├── positive success -> VERIFIED
  ├── positive no-outcome -> OUTCOME_NOT_ACHIEVED
  └── uncertain / verifier unavailable -> RECONCILE_REQUIRED (active, non-terminal)
  ↓
release UI claim once backend/verifier UI liveness is positively stopped
(or retain/block only while liveness itself remains uncertain)
```

若 `RECONCILE_REQUIRED`：

```text
capctl status
= read-only

capctl reconcile
= may reacquire android_ui for profile observation
= must not click Publish again
= may resolve to VERIFIED / OUTCOME_NOT_ACHIEVED / evidence-supported FAILED
```

禁止：

```text
Publish timeout
-> allocate second backend
-> reuse consumed approval
-> click Publish again
```

## 44.3 Future Capability Pattern — e.g. WhatsApp

未来 `whatsapp.send_message` **不属于 v0.6 implementation**，但新 BUSINESS capability 应只新增：

```text
Capability Definition
Payload schema
Adapter translation
Existing/generic workflow
Verifier
Capability-specific minimum policy
```

共享：

```text
Gateway job durability
deterministic backend binding
TTL pre-submit gate
android_ui ownership where required
Core state integrity
effect boundary
approval semantics
outcome/reconcile contract
journal/evidence
```

不共享/不提前建设：

```text
generic scheduler
plugin runtime
event bus
distributed queue
capacity-N resource engine
```

## 44.5 Reference Flow — Full Device Reboot Recovery

设备重启不是普通 coordinator crash。Reboot 后：

```text
old processes are gone
old flock ownership is gone
durable capability jobs / claims / effect-boundary records remain
old state tokens are invalid because boot_id changed
business outcome may still be unresolved
```

第一条显式管理/执行命令（`doctor` / `status` / `reconcile` / `invoke`）必须先执行 reboot-aware preflight：

```text
1. read current boot_id
2. detect durable android_ui claim
3. compare claim.owner.boot_id with current boot_id
4. classify previous-boot owner identity as non-live (`DEAD_BY_BOOT_MISMATCH`, treated as DEAD-equivalent **only for process/resource liveness**, never for business outcome)
5. inspect bound capability/backend/effect-boundary state
6. never infer business outcome merely from reboot
```

若旧 claim 来自 previous boot：

```text
resource execution from that boot is physically stopped
```

因此 explicit `capctl reconcile` 可以在持有 canonical flock 时：

```text
durably remove old claim
fsync parent dir
```

但 capability outcome 的处理取决于 effect evidence：
```text
pre-effect + proof no effect
-> may resolve FAILED / safe final state according to capability

effect boundary crossed / effect may have occurred
-> keep capability RECONCILE_REQUIRED
-> run verifier/reconciliation
-> never repeat external effect automatically
```

State integrity：

- 旧 token 因 `observed_boot_id` mismatch 无条件失效；
- reboot 本身不要求无条件改变 `state_epoch`；
- 若存在 mutation-durability uncertainty、state-store corruption 或 ADMIN force-reset，则按对应规则 durable bump/new `state_epoch`；
- new mutation 只能在 resource claim 与 state-integrity preflight 重新建立后开始。

`doctor` 对 previous-boot claim 应输出：

```text
owner_process_state = DEAD
recommended_action = RECONCILE
reason = PREVIOUS_BOOT_OWNER
```

而不是自动清理。

---

# 45. Trade-offs

## 45.1 Why Capability Gateway now

Y700 capability 数量即将增长；如果继续让每个 Agent 直接绑定 app/controller，后续安全规则会复制和漂移。

Gateway 的价值是：

```text
stable contract
central minimum policy
central ownership/recovery binding
```

不是“多一层框架”。

## 45.2 Why no daemon

当前：

- single device；
- low throughput；
- foreground invocation 可满足；
- daemon 会引入 liveness/upgrade/recovery 新问题。

未来若有真实 detached/scheduling need，再设计。

## 45.3 Why not only revision

human/system changes 不会更新 automation revision。

所以需要 semantic hash。

## 45.4 Why not full UI hash

full tree 太敏感，动态时间、列表、动画可能制造 false stale。

所以使用 scoped semantic fingerprint。

## 45.5 Why durable resource claim + flock

flock 解决 live process exclusion；

durable claim 解决 coordinator crash 后 backend 仍活着的 ownership。

两者缺一不可。

## 45.6 Why deterministic backend id

它关闭最危险的：

```text
backend executed
but Gateway forgot binding
```

crash window。

## 45.7 Why transport retry identity but no business-idempotency engine

Rev3.1 增加 `submission_id`，因为“同一次提交的网络重传”可以用一个很小的 deterministic admission mapping 正确解决。

但 exactly-once business side effect 不是一个 `idempotency_key` 字段就能解决。

当前 deterministic backend identity + no blind replay 已解决更直接的问题。

## 45.8 Why no separate mutation lock

`android_ui` resource 已是 mutation lane。

再加锁是重复 abstraction。

## 45.9 Why MUTATION_PREPARED stays in UI journal

现有 UI job 已有 durable journal/checkpoint。

复用它比新增 global transaction store 更简单、更容易恢复。

## 45.10 Why readiness is a view, not a new authority

动态 READY 很容易过期。若把 readiness snapshot 当 permission，会重新制造 TOCTOU。

所以：

```text
Catalog = static contract
node-health = advisory current evidence
Core/backend durable facts = execution authority
```

## 45.11 Why no automatic alternate-runtime fallback

跨 runtime fallback 在“无副作用纯计算”里可能简单，但 Android automation 会携带 foreground/UI/resource/business effect 状态。

因此 v0.6 宁可：

```text
fail closed / reconcile
```

也不把“设备暂时不可用”误解为“可以换地方再做一次”。

## 45.12 Why benchmark-driven thresholds, not scheduler-first design

Backburner 的收益来自先测通信、计算、内存、thermal，再决定何时 offload。Y700 同样应先证明 break-even。

因此 Rev3.5 只冻结 **measurement gate**，不冻结某个阈值、更不建设 adaptive scheduler。

---

# 46. Machine-Check Catalog — Pre-Implementation vs Sprint-Gated

Rev3.6 要求 machine-executable checks，但**不是所有 check 都必须在 Sprint 1 前 PASS**。否则会形成“必须先实现生产代码，才能获得实现生产代码的授权”的循环依赖。

本节把 checks 分为：

```text
P0B_PRE_IMPLEMENTATION
= Phase 0B 可独立构建/运行；阻断 Production Runtime Implementation Authorization

SPRINT_GATED
= Phase 0B 先定义 test contract / fixture / skeleton；
  等对应 production feature 实现后才要求 PASS，并由对应 Sprint CI/DoD 阻断
```

文件名可按 repo convention 调整，但职责不可省略。

建议最小集合：

```text
scripts/v06/preflight-baseline.sh
scripts/v06/check-runtime-permissions.sh
scripts/v06/check-ui-mutation-inventory.py
scripts/v06/check-presshome-back-migration.py
scripts/v06/check-subjob-provenance.py
scripts/v06/check-semantic-vectors.py
scripts/v06/check-catalog-overlay-policy.py
scripts/v06/check-capability-readiness.py
scripts/v06/check-fingerprint-profiles.py
scripts/v06/check-claim-session-reconcile.py
scripts/v06/check-admission-lock-load.py
scripts/v06/check-clock-source.sh
scripts/v06/check-app-ui-contract.py
scripts/v06/check-upgrade-gate.sh
tests/fault_injection/test_durability_boundaries.py
```

### 46.0 Check staging

| Check | Before Sprint 1 | When full PASS becomes blocking |
|---|---|---|
| `preflight-baseline` | **PASS required** | Phase 0B |
| `check-runtime-permissions` | baseline/readability **PASS required** | enforcement regression again in relevant Sprint |
| `check-ui-mutation-inventory` | **inventory PASS required** | bypass-elimination PASS after Sprint 1 migration |
| `check-presshome-back-migration` | contract/fixture only | **Sprint 1** |
| `check-subjob-provenance` | inventory/fixture only | **Sprint 3 / TikTok migration** |
| `check-semantic-vectors` | reference implementation **PASS required** | Core implementation must match again in Sprint 1 |
| `check-catalog-overlay-policy` | schema fixture may exist | **Sprint 2 / capability Catalog implementation** |
| `check-capability-readiness` | contract fixture may exist | **Sprint 6 / discovery-health implementation** |
| `check-fingerprint-profiles` | reference vectors/profile schema can PASS | production consumer/producer check after Sprint 1 |
| `check-claim-session-reconcile` | proof-matrix fixture only | **Sprint 3 / recovery implementation** |
| `check-admission-lock-load` | synthetic filesystem/flock/fsync benchmark **PASS required** | actual production admission critical-section A69 after Sprint 2 |
| `check-clock-source` | **PASS required** | Phase 0B |
| `check-app-ui-contract` | installed-app evidence collector **PASS required** | runtime enforcement A75/A83 after relevant capability implementation |
| `check-upgrade-gate` | current-state inventory/dry-run fixture | full enforcement before actual upgrade/enablement |
| fault-injection harness | harness/self-test **PASS required** | named production boundaries become blocking as each implementation exists |

因此 “machine check exists” 与 “production behavior check PASS” 是两个不同里程碑。

职责：

- `preflight-baseline`：Git baseline / APK SHA / device health / free space / current claim / unresolved jobs；
- `check-runtime-permissions`：runtime dirs owner/mode/symlink integrity；
- `check-ui-mutation-inventory`：列出所有生产 mutation 入口，禁止未知 direct bypass；
- `check-presshome-back-migration`：Phase 0B 先建立检索/fixture；Sprint 1 后才证明 `pressHome/pressBack` 已走 protocol-v2 mutation；
- `check-subjob-provenance`：Phase 0B 先完成 inventory/fixture；对应 backend/TikTok migration 后才要求 mutating subjob 均有 parent/top-backend/resource_guard；
- `check-semantic-vectors`：固定 canonical hash 向量严格匹配；
- `check-catalog-overlay-policy`：Phase 0B 可验证 schema fixture；Catalog 实现后才要求所有 mutating capability 声明 REQUIRED overlay guard，且 `POSSIBLE` modal 有 blocking selectors；
- `check-capability-readiness`：Phase 0B 定义 contract fixture；discovery/health 实现后验证 Catalog `execution_profile`、node-health schema、reason codes、protocol compatibility 与 `alive != ready` invariants；
- `check-fingerprint-profiles`：profile ID、watched optional fields、omit/null/empty/unavailable canonical vectors；
- `check-claim-session-reconcile`：Phase 0B 先固化 proof matrix/fixtures；recovery 实现后验证 new claim session、新 subjob、stale subjob rejection 与 STOPPED/ZOMBIE 行为；
- `check-admission-lock-load`：Phase 0B 用**synthetic representative critical section**测 filesystem/flock/fsync p95/p99，选择初始候选值；Sprint 2 admission 实现后再跑真实 critical-section A69，并允许在 5000/10000/15000ms 内调整最终 deployment value；
- `check-clock-source`：验证 Android Host / Debian chroot 的 boot_id、CLOCK_BOOTTIME unit/epoch/delta/suspend behavior 一致；
- `check-app-ui-contract`：读取 installed package/version/signing identity 并与 Catalog `app_ui_contract` exact compare；
- `check-upgrade-gate`：legacy mutator/COMMITTING/unresolved effect 存在时拒绝 upgrade/rollback；
- fault-injection：Phase 0B 要求 harness/fixture/self-test；各 named production boundary 在对应代码存在后才成为 blocking test。

所有脚本/测试必须输出 machine-readable PASS/FAIL，并由 affected-path CI gate 调用。

## 46.1 Phase 0A/0B — Freeze-to-Implementation Mandatory Empirical Gates

Rev3.6 是当前 frozen implementation-input baseline；**Phase 0B validation tooling 已授权，但 Sprint 1 production runtime implementation 仍未授权**。在申请 Production Runtime Implementation Authorization 前，必须先在真实 Y700 / Android 16 / Debian 13 chroot 环境关闭以下工程可实现性风险。它们是 deployment/implementation gates，不改变冻结架构语义。

### P0-G1 — Debian chroot -> Android Host `/proc` evidence visibility

必须验证 `capctl doctor` / reconcile 所需的 exact process evidence 在真实设备上可稳定读取：

```text
claim.owner.boot_id
claim.owner.pid
/proc/<pid>/stat -> proc_start_ticks + process state
Android Host JVM / app_process / UI Automator related process identity
Debian chroot process identity
```

最低要求：

1. 在 Debian chroot 中真实读取 Android Host 相关目标进程的 `/proc/<pid>/stat`；
2. 验证 MATCHING / DEAD / PID_REUSED / STOPPED / ZOMBIE 至少能通过可控样例或等价 fixture 正确分类；
3. 若 SELinux/procfs/hidepid/namespace 导致关键证据不可读，则 classifier 必须返回 `UNREADABLE` / UNKNOWN evidence 并 fail closed；
4. 在证据可见性未证明前，不得把 `/proc` classifier 当 release authority，也不得进入 Sprint 1 claim-reconcile implementation。

5. 同一真实 boot 内测量 Android Host 与 Debian chroot 的 `CLOCK_BOOTTIME` delta/单位/boot epoch；熄屏+suspend 前后两侧 delta 必须在记录的 tolerance 内一致；
6. 若跨环境 BOOTTIME 无法证明同源，则跨环境 token/deadline 比较必须 fail closed，Implementation Authorization = NO，直到 contract 被修正。

建议新增 machine check：

```text
scripts/v06/check-proc-visibility.sh
```

### P0-G2 — Admission lock / UFS pressure baseline

Phase 0B 必须先对代表性 filesystem/flock/fsync critical section 做真机基线，选出 **initial deployment candidate**。候选：

```text
5000 / 10000 / 15000 ms
```

测试必须同时覆盖：

```text
TikTok cold start
representative video decode / media I/O
fsync-heavy journal/submission writes
concurrent same/different submission admission
```

Phase 0B 初始选择规则：

```text
synthetic representative p99 < initial_timeout_ms * 0.5
```

若 5000ms 不满足，可把 initial candidate 上调至 10000ms 或 15000ms，并记录证据。

**最终 production effective value 不要求在 Sprint 1 前证明。** Sprint 2 admission implementation 完成后，必须以真实 production critical section 跑 A69：

```text
actual production p99 < effective_timeout_ms * 0.5
```

必要时仍可在已冻结候选集合 `5000/10000/15000ms` 内调整，不构成 architecture change；但在 mutating BUSINESS capability enablement 前必须固定并记录最终值。任何 timeout recovery 始终复用原 `submission_id`。

### P0-G3 — Android 16 / ZUI overlay inventory

在 Settings 与 TikTok production acceptance 前，必须抓取当前 Y700 固件下的实际 top-level window / package / class inventory，至少覆盖：

```text
IME
Toast / transient system notification
ZUI game/performance overlay
floating sidebar / split-screen anchor
PiP / application overlay where present
Accessibility overlay where present
```

只有经实测确认、语义稳定且不会拦截目标输入的窗口才可进入 **versioned exact allowlist**。禁止：

```text
package wildcard ignore
class wildcard ignore
unknown system-window blanket allow
```

建议新增 machine check / evidence collector：

```text
scripts/v06/check-zui-overlay-inventory.py
```

### P0-G4 — Suspend / wake-lock execution policy

`CLOCK_BOOTTIME` 继续包含 suspend；因此睡眠期间 token 失效是冻结的 fail-closed 语义，不得改回 `CLOCK_MONOTONIC` 规避。Phase 0 必须验证当前 workflow runtime 是否能够在**持有 active android_ui ownership 且正在连续执行 UI workflow 时**合法阻止 Deep Sleep。

允许的最小策略：

```text
active mutating UI workflow
-> bounded wake-lock / keep-screen-awake according to Android-host capability
-> release immediately when workflow/ownership session ends or blocks for external interaction
```

约束：

- wake-lock 只改善连续执行可用性，不延长 state-token correctness lifetime；
- resume 后任何已经超过 `max_age_ms` 或 boot/session guard 不匹配的 token 仍必须失效；
- 若无法安全/合法持有 wake-lock，系统仍正确但接受额外 AUTO observe 延迟，不得放宽 token age。

建议新增 machine check：

```text
scripts/v06/check-suspend-wakelock-policy.sh
```

### Phase 0 Authorization Gate

只有以下 **pre-implementation subset** 全部 PASS，才允许召开独立 Production Runtime Implementation Authorization review：

```text
Phase 0A passive baseline/inventory complete
P0-G1 proc visibility/classification evidence PASS
P0-G1 host/chroot CLOCK_BOOTTIME equivalence + suspend-delta evidence PASS
P0-G2 synthetic filesystem/flock/fsync benchmark PASS + initial timeout candidate recorded
P0-G3 ZUI/Android overlay inventory + proposed exact allowlist evidence PASS
P0-G4 suspend/wake-lock behavior characterized + intended policy recorded
semantic-v1 reference fixed vectors PASS
runtime filesystem permission/readability baseline PASS
installed app/version/signing evidence collector PASS
fault-injection harness SELF-TEST / fixture baseline PASS
all P0B_PRE_IMPLEMENTATION checks from Section 46.0 PASS
all SPRINT_GATED checks have executable contract/fixture/skeleton, but are NOT required to report production PASS yet
```

Freeze Approval 本身不得被解释为 Sprint 1 production coding authorization；同样，Phase 0 Gate **不得要求尚未实现的 production behavior already PASS**。

---

# 47. Definition of Done

全部满足才可关闭 v0.6：

- [ ] Bridge v2 frozen guarantees unchanged；
- [ ] no mandatory Gateway daemon；
- [ ] no detached execution；
- [ ] no new MQ/DB；
- [ ] one canonical `android_ui` lock path；
- [ ] durable resource claim implemented；
- [ ] safety-critical durability failures checked/classified；
- [ ] post-mutation state-store durability loss blocks mutation until epoch reset；
- [ ] filesystem permission/symlink integrity preflight implemented；
- [ ] explicit GC dry-run/apply implemented; no background GC daemon；
- [ ] heartbeat/PID/claim age are evidence only and never auto-release ownership；
- [ ] doctor distinguishes STOPPED vs ZOMBIE; STOPPED alone never authorizes release；
- [ ] normal `capctl reconcile` can release exact claim after multi-source positive-stop proof without ADMIN；
- [ ] all production mutating UI paths participate and Core enforces exact `resource_guard`；
- [ ] no nested/reentrant `android_ui` acquisition in Gateway -> Publisher -> Core path；
- [ ] one capability top-level backend may have traceable subordinate jobs without being mistaken for retries；
- [ ] subordinate jobs carry parent/top-backend provenance; mutating subjobs exact resource_guard；
- [ ] reconcile claim-session rollover uses a new exact claim + new reconcile/verify subjob; stale old-claim subjobs are rejected；
- [ ] capability namespace / stable naming rule documented；
- [ ] static Catalog separate from dynamic node health/readiness；
- [ ] minimal static `execution_profile` implemented for shipping capabilities；
- [ ] `alive/reachable != READY != safe-to-mutate` semantics enforced；
- [ ] readiness statuses UNKNOWN/READY/DEGRADED/BUSY/BLOCKED_RECONCILE/UNAVAILABLE + reason codes implemented；
- [ ] stale/boot-mismatched health snapshot cannot authorize execution；
- [ ] runtime contract/protocol mismatch surfaces as UNAVAILABLE / `RUNTIME_CONTRACT_MISMATCH`；
- [ ] optional degradation cannot bypass minimum safety/verifier/resource/state-integrity requirements；
- [ ] fallback/reconstruction preserves same submission/capability/top-backend identity and never bypasses effect boundary；
- [ ] exact capability version matching；
- [ ] mandatory `submission_id` admission binding implemented；
- [ ] same-submission retry returns the same deterministic capability job；
- [ ] official controllers persist submission_id through timeout/DEVICE_BUSY and obey bounded retry/status/reconcile escalation；
- [ ] same submission ID with mismatched request fails `SUBMISSION_ID_CONFLICT`；
- [ ] `expires_at` pre-start stale-job protection PASS；
- [ ] same-boot monotonic TTL deadline + reboot behavior PASS；
- [ ] no `not_before` scheduler in v0.6；
- [ ] caller cannot weaken minimum policy；
- [ ] request/effective policy immutable after activation；
- [ ] deterministic backend ID persisted before resource claim dependency and before submit；
- [ ] `backend.json` is immutable binding intent; pre-submit EXPIRED/CANCELLED/FAILED matrix PASS；
- [ ] coordinator crash recovers same backend；
- [ ] state_epoch/revision/semantic hash implemented；
- [ ] semantic-v1 uses explicit field allowlist；
- [ ] semantic-v1 exact canonical schema + fixed vectors PASS；
- [ ] fingerprint profile/watched-field omission/null/empty/unavailable semantics PASS fixed tests；
- [ ] Catalog overlay_policy validation PASS for every mutating capability；
- [ ] mandatory global blocking-overlay fields participate in all mutation guards；
- [ ] unexpected top-level/system/app modal blocks mutation with zero attempts；
- [ ] IME/Toast/non-focusable benign-window overlay false-positive controls PASS；
- [ ] state-token age uses boot-aware CLOCK_BOOTTIME；
- [ ] suspend/BOOTTIME invalidation + fresh AUTO screen/keyguard/foreground/overlay preflight PASS；
- [ ] dynamic non-allowlisted attributes do not perturb state hash；
- [ ] TOKEN/AUTO mutation guard implemented；
- [ ] stale revision blocks with zero action attempt；
- [ ] out-of-band state drift blocks with zero action attempt；
- [ ] MUTATION_PREPARED durable before mutation；
- [ ] uncertain mutation not blind replayed；
- [ ] EFFECT_BOUNDARY_CROSSED durable before unsafe effect；
- [ ] unsafe ambiguity -> non-terminal active `RECONCILE_REQUIRED`；
- [ ] approval bound to exact request hash and revalidated/consumed at effect boundary；
- [ ] verifier infra failure != business failure；
- [ ] `status` read-only and `reconcile` is the only normal recovery-mutating CLI path；
- [ ] mutating/unknown ADMIN path bumps state_epoch before dispatch；
- [ ] ADMIN force-reset audited and cannot replay/terminalize old outcome；
- [ ] `pressHome` / `pressBack` classified as local UI mutations and invalidate old tokens；
- [ ] capability effect boundary is always durable before Publisher `COMMITTING` / external click；

- [ ] cancel/effect-boundary race is serialized by per-capability transition lock and A70 PASS；
- [ ] effect-boundary winner cannot later become CANCELLED；
- [ ] ADMIN force-reset cannot release claim until old UI mutator quiescence is positively established；
- [ ] `state.json` uses temp+fsync+atomic-rename+parent-fsync and monotonic `state_revision`；

- [ ] `android-ui.lock` and per-job `transition.lock` obey no-nested-blocking-acquisition rule; A80 PASS；
- [ ] terminal outcome linearizes only on durable `result.json`; active-result/archive race A82 PASS；

- [ ] status uses bounded transition `LOCK_SH` for consistent state/result snapshots while writers use `LOCK_EX`; A88 PASS；
- [ ] valid terminal result outranks stale/corrupt state; corrupt result never falls back to archive-path guessing; A87 PASS；
- [ ] corrupted lifecycle snapshot surfaces `STATE_STORE_CORRUPT` and is never silently repaired by status；
- [ ] Settings golden acceptance PASS；
- [ ] TikTok safety regression PASS；
- [ ] legacy vs Gateway concurrency PASS；
- [ ] capability status resolves active `RECONCILE_REQUIRED` and terminal archive races without false not-found；
- [ ] `state.json` is live lifecycle authority; Controller stops normal polling on `RECONCILE_REQUIRED` and does not wait for `result.json`；
- [ ] on-demand `node-health.json` available and clearly advisory；
- [ ] transport contains no unique correctness state；
- [ ] any remote transport terminates at trusted control/Gateway boundary; internal primitive surfaces are not independently exposed；
- [ ] no adaptive cross-runtime scheduler/failover implemented in v0.6；
- [ ] future placement/offload is explicitly measurement-gated；
- [ ] minimal timing observability available without metrics daemon；
- [ ] doctor exposes blocked reconcile + storage/permission/clock health；
- [ ] doctor classifies owner process as MATCHING/DEAD/PID_REUSED/STOPPED/ZOMBIE/HUNG_OR_UNKNOWN/UNREADABLE；
- [ ] standard operational alert rules documented and reference Controller surfaces HIGH/CRITICAL states；
- [ ] full-device reboot recovery reference flow acceptance PASS；
- [ ] CLI/Python machine-readable error envelope implemented；
- [ ] v0.5 -> v0.6 upgrade/rollback acceptance PASS；
- [ ] secrets/runtime state remain outside Git；
- [ ] docs / CHECKPOINT updated after accepted gates；
- [ ] machine-executable implementation preflight suite PASS；

- [ ] Phase 0A passive inventory completed before tooling changes；
- [ ] Phase 0B changes are limited to scripts/tests/diagnostics/CI and do not alter production runtime behavior；

- [ ] Phase 0 Authorization Gate requires only `P0B_PRE_IMPLEMENTATION` PASS; SPRINT_GATED checks are deferred to their owning Sprint without weakening final DoD; A86 PASS；
- [ ] LEGACY `owner_kind=LEGACY` stale resource can be normally addressed by exact `claim_id` without fake capability job；
- [ ] app-specific mutating capability verifies installed app/UI contract before backend start；

- [ ] app/UI contract is revalidated JIT before each app-specific mutating dispatch and again at external effect boundary; A83 PASS；
- [ ] CLOCK_SUSPECT pre-submit recovery preserves same job and has a safe same-submission continuation path after clock repair; A81 PASS；

- [ ] admission explicitly permits only the bounded safe pre-submit same-submission continuation exception; A84 PASS；
- [ ] late cancel/reconcile after durable terminal result is read-only with respect to final capability outcome; A85 PASS；
- [ ] RECONCILE_REQUIRED dwell age is machine-readable and never grants cleanup/replay authority；
- [ ] Phase 0 Debian chroot -> Android Host `/proc` visibility/classification evidence PASS；
- [ ] Phase 0 admission-lock/UFS pressure p95/p99 baseline PASS and effective timeout frozen；
- [ ] Phase 0 Android 16/ZUI overlay inventory + versioned exact allowlist evidence PASS；
- [ ] Phase 0 suspend/wake-lock behavior characterized without weakening BOOTTIME/token-age semantics；
- [ ] admission lock timeout load gate PASS with measured effective deployment value；
- [ ] fault-injection named-boundary tests PASS in CI/simulation layer；
- [ ] Sprint-0 fsync count/latency baseline recorded；
- [ ] GitHub CI affected-path checks PASS；
- [ ] real Y700 closure evidence recorded。

---

# 48. Red Team Closure Mapping

| Finding | Rev3 resolution |
|---|---|
| C1 execution model undefined | Foreground synchronous coordinator; no detached execution |
| C2 backend submission crash window | deterministic backend ID + `backend.json` before submit |
| C3 flock lifetime unsafe | flock + durable claim + Core ownership assertion + backend-aware recovery |
| C4 legacy bypass | one canonical existing `android-ui.lock`; all production mutating paths participate |
| C5 caller weakens policy | minimum policy owned by catalog; weakening rejected |
| C6 ambiguous SOT | one-fact-one-owner authority matrix |
| H1 SIDE_EFFECT_APPLIED unsafe | replaced by pre-effect `EFFECT_BOUNDARY_CROSSED` |
| H2 approval not exact-bound | request hash + version + nonce + single-use approval |
| H3 verifier/business failure conflated | final outcomes separated from non-terminal `RECONCILE_REQUIRED` recovery state |
| H4 idempotency race | business-idempotency engine deferred; Rev3.1 adds only transport-retry `submission_id` admission dedupe |
| H5 cancellation/resource release | resource retained until backend safe termination proof |
| H6 multi-resource deadlock | v0.6 ships only `android_ui` capacity 1 |
| H7 static/dynamic mixed | static Catalog vs advisory `node-health.json` separation |
| H8 requested_by identity | metadata only; not authorization |
| H9 immutable binding missing | request/policy hashes; mutation => contract violation |
| M1 version semantics | exact match only |
| M2 archive race | bounded direct lookup like Bridge |
| M3 capacity-N premature | deferred |
| M4 arbitrary performance | measurement guardrails, not hard product SLA |
| M5 primitive escape hatches | BUSINESS / INTERNAL / ADMIN classification |

---
| H10 pre-submit binding/terminal ambiguity | `backend.json` explicitly means binding intent only; pre-submit EXPIRED/CANCELLED/FAILED matrix; uncertain submit -> reconcile |
| C7 crash availability vs stale claim | deterministic normal reconcile release only after multi-source positive-stop proof; ADMIN reserved for unresolved/coercive recovery |
| H11 STOPPED/ZOMBIE conflation | split states; STOPPED is resumable and cannot authorize release; ZOMBIE can participate in positive proof |
| H12 fingerprint watched-field ambiguity | versioned `fingerprint_profile_id` + explicit watched optional properties; unwatched fields MUST omit |
| H13 blocked-vs-terminal API ambiguity | `state.json` live lifecycle authority; `result.json` terminal marker only; status exposes `terminal/next_action` |
| H14 reconcile claim ABA/stale subjob | claim is ownership-session identity; new session -> new subjob/exact new claim; old subjob remains invalid |
| H15 overlay false positives | window classification excludes benign IME/Toast/non-focusable transients while unknown input-intercepting overlays fail closed |
| M1 suspend token semantics | BOOTTIME includes suspend deliberately; stale token -> fresh AUTO preflight |
| M2 admission timeout under I/O | measured deployment constant with bounded same-submission retry; never changes admission identity |
| A1 runtime reachability ambiguity | explicit readiness state/reason/compatibility advertisement; readiness advisory only |
| A2 unsafe fallback | fallback eligibility bound to state ownership/effect phase; no transparent alternate-runtime retry |

---

# 48A. Rev3.6 Targeted Red-Team Closure Mapping

| Red Team finding | Rev3.6 closure |
|---|---|
| H16 cancel may race with irreversible effect boundary | per-capability `transition.lock`; durable cancel vs effect-boundary winner; A70 |
| H17 ADMIN force-reset may free claim while old action is still in-flight | quiescence proof required before unlink; otherwise `DEVICE_UI_RUNTIME_UNSAFE`; A71 |
| H18 lifecycle authority lacked its own crash-safe persistence contract | atomic `state.json` publish + `state_revision` + corruption recovery; A72 |
| H19 Phase 0 required code before code authorization | Phase 0A passive + Phase 0B validation-tooling authorization + separate production authorization; A73 |
| H20 LEGACY claim had no normal reconcile address | `capctl reconcile-resource --claim-id`; resource-only semantics; A74 |
| H21 versioned blocking selectors not bound to actual installed app build | Catalog `app_ui_contract` + readiness compatibility; A75 |
| M3 cross-environment BOOTTIME source assumption | P0-G1 host/chroot delta+suspend validation; A76 |
| M4 reboot with suspect realtime had ambiguous TTL behavior | no submit/no EXPIRED; blocked reconcile until trusted clock; A77 |
| M5 long-lived RECONCILE_REQUIRED had no per-job dwell signal | `reconcile_since/reconcile_age_ms/oldest_reconcile_age_ms`; A78 |
| M6 backend never-created predicate too abstract | exact positive-proof predicate; ENOENT alone insufficient; A79 |
| M7 controller retry violation error ownership ambiguous | emitter explicitly first-party Controller/auditor, not generic Gateway detector |
| M8 durability error could leave RAM state mistaken for truth | durability failure invalidates RAM-only causal state; re-read durable facts or block |
| FR1 new transition.lock introduced possible ABBA deadlock with canonical resource flock | explicit no-nested-blocking-acquisition rule; A80 |
| FR2 CLOCK_SUSPECT_PRE_SUBMIT could enter reconcile dead-end | preserve pre-submit lifecycle; repair clock then same-submission safe continuation only; A81 |
| FR3 terminal state/result publication order could expose terminal-without-result | result.json is terminal linearization point; state stays nonterminal until result; A82 |
| FR4 app/UI contract could change after advisory READY | JIT Adapter/workflow revalidation before mutation/effect; A83 |
| FR5 admission's generic “active job -> return status” contradicted safe pre-submit continuation | narrow same-submission continuation exception with never-created/no-uncertainty proof; A84 |
| FR6 terminal result could race with late cancel/reconcile before archive move | result-first guard under transition serialization; A85 |
| FR7 Phase 0 gate still required post-implementation behavior before Sprint 1 authorization | staged machine-check catalog: P0B_PRE_IMPLEMENTATION vs SPRINT_GATED; A86 |
| FR8 terminal result authority conflicted with state corruption handling | valid result outranks state; corrupt result has explicit fail-closed contract; A87 |
| FR9 read-only status could observe result rename before durability linearization completed | bounded transition LOCK_SH vs writer LOCK_EX; A88 |

# 49. Consolidation Mapping from the Previous State-Integrity PRD

以下内容 **保留**：

```text
state_epoch
revision
semantic state_hash
state token
compare-before-mutate
AUTO guard
replay-safety vs mutation-class separation
fail-closed stale state
explicit reconciliation
generic Core primitive boundary
```

以下内容 **被 MSA 收敛**：

### Previous

```text
separate mutation.lock
```

### Rev3

```text
use canonical android_ui arbiter
```

---

### Previous

```text
global pending-mutation.json
```

### Rev3

```text
fsynced MUTATION_PREPARED in existing UI job journal
```

---

### Previous

```text
state integrity as stand-alone device transaction layer
```

### Rev3

```text
state integrity remains inside Core execution layer
Gateway consumes it but does not duplicate it
```

---

# 50. Recommended Frozen Decisions

Rev3.6 Freeze Approval 在保留 Rev3.5 决策 1–74 的基础上，正式接受以下增量决定：

1. **Gateway 是 thin facade，不是新 runtime。**
2. **v0.6 没有 Gateway daemon。**
3. **v0.6 没有 detached/scheduled capability execution。**
4. **Bridge v2 不改 architecture。**
5. **android_ui 是唯一 operational exclusive resource。**
6. **复用 existing android-ui.lock，禁止第二 lock namespace。**
7. **resource safety = flock + durable claim；Core mutation assert exact claim。**
8. **claim durable 后才 backend submit；cleanup 在 backend-stop proof 后 durable。**
9. **backend.json 在 claim dependency 与 submit 前 durable。**
10. **backend.json 绑定 top-level backend；内部可有 traceable subordinate jobs。**
11. **mutating subordinate job 必须 parent/top-backend provenance + exact resource_guard。**
12. **Catalog owns minimum safety policy；caller cannot weaken。**
13. **request/effective policy immutable after activation。**
14. **State Integrity belongs Core。**
15. **UI mutation uses compare-before-mutate + ownership assertion。**
16. **pressHome/pressBack are LOCAL_UI_MUTATION。**
17. **MUTATION_PREPARED durable before action。**
18. **revision=N+1 durable before MUTATION_COMMITTED。**
19. **safety-critical durability failure fail-closed；post-action uncertainty reconciles rather than ordinary FAILED。**
20. **EFFECT_BOUNDARY_CROSSED durable before unsafe effect。**
21. **TikTok: effect boundary -> COMMITTING -> exactly-one Publish。**
22. **effect-boundary.json is sole unsafe-boundary authority。**
23. **post-boundary ambiguity never auto-retries。**
24. **Approval exact-request bound and consumed at durable boundary。**
25. **OUTCOME_NOT_ACHIEVED does not grant retry permission。**
26. **RECONCILE_REQUIRED is non-terminal active blocked。**
27. **status read-only；reconcile is normal existing-job recovery mutator。**
28. **backend-stop proof may release UI claim while business outcome remains unresolved。**
29. **TikTok Profile reconcile inherited。**
30. **business idempotency deferred；submission_id only transport retry identity。**
31. **same submission + same request -> same deterministic job；mismatch -> conflict。**
32. **admission.lock bounded；5000ms is initial default, effective deployment timeout is measurement-gated to 5000/10000/15000ms without changing same-submission identity semantics。**
33. **semantic-v1 exact allowlist/canonical JSON/fixed vectors。**
34. **state-token age uses boot-aware CLOCK_BOOTTIME。**
35. **heartbeat/PID/claim age are evidence, never lease authority。**
36. **mutating/unknown ADMIN path bumps epoch before dispatch。**
37. **filesystem owner/mode/symlink integrity failure -> fail closed。**
38. **no background GC；explicit dry-run/apply only；active/reconcile/current claim never normal GC。**
39. **multi-resource/capacity-N deferred。**
40. **Settings is acceptance proof, not necessarily public BUSINESS API。**
41. **android.root.exec is ADMIN escape hatch。**
42. **dynamic health cannot mutate static capability contract。**
43. **expires_at pre-submit only；same boot uses monotonic deadline。**
44. **not_before/scheduler deferred。**
45. **Transport cannot carry unique correctness state。**
46. **stable capability semantics require version/migration。**
47. **Observability reuses per-job journal/result；history via retention/GC。**
48. **v0.5->v0.6 uses gated migration；rollback never crosses unresolved Rev3.6 active/effect state。**
49. **correctness dominates performance optimization。**
50. **official Controller 对 transport timeout/DEVICE_BUSY/unknown invoke 必须复用原 `submission_id`，采用 bounded backoff，并在预算耗尽后走 status/doctor/reconcile；prior intent 未 final 前不得以新 ID 规避。**
51. **所有 protocol-v2 mutation 必须包含 mandatory global blocking-overlay guard；unexpected top-level/modal blocker -> `UNEXPECTED_BLOCKING_OVERLAY`, zero action attempts。**
52. **semantic-v1 global screen facts 必须包含 blocking-overlay presence/owner/class；app 内不可作为独立 window 识别的 blocker 由 versioned blocking selector 补充。**
53. **doctor 必须基于 boot_id/pid/proc_start_ticks + /proc + backend/subjob facts 分类 MATCHING/DEAD/PID_REUSED/STOPPED/ZOMBIE/HUNG_OR_UNKNOWN/UNREADABLE；STOPPED 可恢复，分类本身不自动释放 claim。**
54. **mutating capability 的 Catalog 必须声明 overlay_policy；若 `in_app_modal=POSSIBLE`，blocking_selectors 不得为空。**
55. **Sprint 0 必须记录 fsync count/latency baseline；性能优化不得把 safety-critical flush 延迟到 effect 后。**
56. **fault-injection harness 与 fixed-vector test 属于 build/release gate，不是可选测试。**
57. **full-device reboot 不自动清 claim；old-boot owner 可作为进程已停止的强证据，但业务 outcome 仍按 effect/verifier evidence reconcile。**
58. **operational alert severity 只驱动 surfaced/escalation，不产生 ownership release/replay authority。**
59. **实施前必须有 machine-executable preflight checks 覆盖 legacy mutation inventory、pressHome/back、subjob provenance、semantic vectors、overlay policy、upgrade gate。**
60. **`backend.json` 只证明 deterministic binding intent；backend 未 submit 前允许按事实 terminalize 为 EXPIRED/CANCELLED/FAILED；submit existence unknown -> RECONCILE_REQUIRED。**
61. **`state.json` 是 live lifecycle authority；`result.json` 仅代表五类 terminal business outcome。**
62. **`RECONCILE_REQUIRED` 的 status 必须返回 `terminal=false,next_action=RECONCILE`；Controller 不等待 `result.json`。**
63. **claim_id 是一次 ownership session identity；reconcile 可为同一 capability 取得新 claim，但必须创建绑定新 exact claim 的新 subjob；旧 subjob 永不 rebind。**
64. **STOPPED 与 ZOMBIE 必须分离；STOPPED 可恢复，不能作为 release proof；ZOMBIE 只能与 exact backend/subjob stop facts 共同形成 positive proof。**
65. **normal `capctl reconcile` 在 positive-stop proof 成立时有权在 canonical flock 下 durable release exact claim；无需 ADMIN。**
66. **semantic-v1 optional element fields 由 versioned fingerprint profile 决定；unwatched MUST omit，watched unavailable fail closed。**
67. **CLOCK_BOOTTIME 包含 suspend 是 deliberate safety behavior；resume 后 stale token 重新 AUTO observe/preflight。**
68. **global overlay guard 基于阻断语义而非“存在第二 window”；IME/Toast/non-focusable transient 不因存在而自动阻断，unknown input-intercepting overlay fail closed。**
69. **Catalog 同时验证 overlay_policy 与 execution_profile；dynamic readiness 永远不是 mutation authority。**
70. **shipping mutating BUSINESS capability canonical placement = Y700_REQUIRED，alternate runtime fallback = NONE。**
71. **fallback permission 由 state reconstructibility + effect phase + replay policy 决定，不由 connectivity 决定。**
72. **remote transport 只终止于 trusted control/Gateway boundary；Bridge/UI/root primitive 不单独暴露 remote API。**
73. **future execution placement/offload 必须 benchmark-driven；v0.6 不实现 adaptive scheduler/failover。**
74. **admission lock timeout 是 measured deployment constant；任何调优都不得改变 same-submission deterministic admission semantics。**

75. **cancel intent 与 `EFFECT_BOUNDARY_CROSSED` 必须通过同一 per-capability transition serialization 得到唯一 durable winner。**
76. **unsafe boundary durable 后的 cancel 不能产生 `CANCELLED`；只能停止非必要后续工作并继续 verify/reconcile。**
77. **ADMIN force-reset 不得以 best-effort stop 代替 quiescence proof；quiescence 未证明则 claim 保留且 mutation lane blocked。**
78. **`state.json` 是 crash-safe authoritative orchestration snapshot：temp+fsync+rename+parent-fsync；RAM state 不是 durability fallback。**
79. **Phase 0A=passive evidence；Phase 0B=explicitly authorized validation tooling；Production Runtime Implementation 仍需独立授权。**
80. **LEGACY resource recovery 必须可通过 exact `claim_id` 进入 normal positive-proof reconcile，不要求伪造 capability job。**
81. **app-specific selector/overlay/verifier contract 必须绑定 accepted app/UI version contract；mismatch -> UNAVAILABLE。**
82. **跨 Android Host/chroot 的 BOOTTIME 语义必须在真机证明同源；否则跨环境比较 fail closed。**
83. **reboot + CLOCK_SUSPECT 时旧 pre-submit job 不得 submit/EXPIRE；保留原 pre-submit lifecycle，标记 `CLOCK_SUSPECT_PRE_SUBMIT`，修复时钟后仅允许 same-submission safe continuation。**
84. **backend never-created 需要 SOT integrity + exhaustive exact-ID lookup + retention guarantee；plain ENOENT 不足。**

85. **`android-ui.lock` 与 per-job `transition.lock` 禁止 nested blocking acquisition；resource mutation 与 lifecycle mutation 分阶段完成。**
86. **reboot + CLOCK_SUSPECT 不把未提交 job 强制送入 RECONCILE_REQUIRED；修复时钟后只允许 exact same-submission 的 safe pre-submit continuation。**
87. **`result.json` durable publish 是 terminal business outcome 的唯一 linearization point；archive move 不是第二 outcome commit。**
88. **app/UI compatibility 必须 JIT revalidate；advisory READY 不能跨 app auto-update 授权后续 mutation/effect。**

89. **active job admission 默认只返回 existing status；唯一 execution-continuation exception 是 exact same-submission 的 positive-proven-safe pre-submit continuation。**
90. **durable `result.json` 之后，late cancel/reconcile 不得再修改 capability final outcome；archive placement 与业务终结解耦。**

91. **Phase 0 Authorization Gate 只要求 pre-implementation checks PASS；依赖新 production code 的 checks 必须先定义 fixture/contract，并在 owning Sprint 实现后才成为 PASS gate。**

92. **valid durable `result.json` outranks `state.json` for final outcome；result corruption fail-closed，archive path 不替代 outcome authority。**
93. **status 对单 job 的 state/result snapshot 使用 bounded `transition.lock` shared lock；writers 使用 exclusive lock，status 仍保持 read-only。**

## 50.1 Freeze Approval vs Implementation Authorization

Rev3.6 Frozen 的架构与 implementation-input contract 现已 authoritative；但**Production Runtime Implementation 权限仍为 NO**。Section 46.1 的 Phase 0A/0B empirical gates 是进入 Sprint 1 前的强制条件。

```text
FREEZE APPROVED
!=
IMPLEMENTATION AUTHORIZED
```

任何 Controller、Agent 或开发流程不得因为本文档状态为 FROZEN 而自动开始 Sprint 1 代码修改。

---

# 51. Future Work — Not Authorized by This PRD

仅记录，不实施：

- additional BUSINESS capabilities；
- `package_manager` / `device_global` resource；
- multi-resource acquisition ordering；
- cross-request business-idempotency engine；
- detached execution；
- caller-owned scheduler integration；
- optional Unix socket fast path；
- HTTP capability API；
- OAuth / multi-tenant authorization；
- multi-device Y700 fleet；
- cross-runtime Mac/Y700/cloud placement scheduler；
- automatic alternate-runtime failover；
- dynamic dependency graph / generic capability negotiation engine；
- health heartbeat daemon；
- capability SDK/plugin ecosystem；
- capacity-N shared resources；
- background automatic GC daemon；
- automatic stale-claim lease stealing；

Future Work 只有出现明确需求/measurement 后再进入独立 PRD。

---

# 52. Original Capability Gateway PRD Integration Mapping

| Original design element | Rev3 decision |
|---|---|
| Capability-first stable interface | **KEEP** |
| `Capability = Intent + Policy + Adapter + Verifier` | **KEEP**, with Catalog-owned minimum policy |
| Namespace / stable naming | **KEEP** |
| Runtime capability registry | **SIMPLIFY** to Git Catalog + on-demand node health; no second static SOT |
| Capability Job Store | **KEEP**, filesystem-only |
| `.staging -> active` | **KEEP** |
| `QUEUED` / detached scheduling | **CUT** in v0.6 |
| `not_before` | **DEFER** |
| `expires_at` TTL | **KEEP**, but only as pre-backend-submit stale-intent gate |
| `SIDE_EFFECT_APPLIED` | **REPLACE** with pre-effect `EFFECT_BOUNDARY_CROSSED` |
| Verifier / Outcome Contract | **KEEP + strengthen** |
| `FAILED` after uncertain side effect | **REPLACE** with `RECONCILE_REQUIRED`; positive negative evidence may produce `OUTCOME_NOT_ACHIEVED` |
| Multiple resources incl. storage/network | **CUT** to `android_ui=1` for v0.6 |
| new lock namespace | **REPLACE** by canonical existing `/opt/y700/runtime/android-ui.lock` |
| process-lifetime `flock()` | **STRENGTHEN** with durable claim + Core resource ownership assertion |
| idempotency_key engine | **DEFER** business-semantic dedupe; Rev3.1 separately adds transport-retry `submission_id` admission identity |
| Adapter Layer | **KEEP, narrow**; no per-adapter locking/lifecycle; downstream must propagate, not reacquire, resource claim |
| `node-health.json` | **KEEP**, on-demand/advisory |
| CLI | **KEEP minimal** |
| new transport | **DEFER**, preserve Trigger != Job boundary |
| Gateway event model | **SIMPLIFY** to existing journal phases |
| standalone metrics file | **DEFER**; timings in journal/result |
| Settings migration | **KEEP as acceptance proof** |
| TikTok migration | **KEEP**, strict ordering: capability effect boundary -> COMMITTING -> Publish; inherit Profile reconciliation |
| future WhatsApp/Instagram expansion | **KEEP as architecture rationale, not v0.6 scope** |

# 53. Rev3 Internal Consistency Closure

本 Rev3 针对 Rev2 的统一性审查，关闭以下内部冲突：

| Rev2 inconsistency | Rev3 closure |
|---|---|
| resource claim required `backend_job_id` but flow acquired resource before backend binding | backend ID + `backend.json` now durable before resource claim and submit |
| `RECONCILE_REQUIRED` was both terminal and reconcilable | now non-terminal active blocked state; no final `result.json` until resolved |
| unsafe boundary duplicated in resource claim and `effect-boundary.json` | removed from claim; `effect-boundary.json` is sole authority |
| direct `ui_job` could bypass top-level arbiter | protocol v2 mutation requires exact Core `resource_guard` assertion |
| durable claim existed conceptually but write/clear crash ordering was implicit | claim write and cleanup now have explicit fsync/rename/unlink ordering |
| Gateway + existing TikTok `ui_lease()` could reacquire the same resource | top-level acquire exactly once; downstream components only propagate/assert claim |
| legacy migration was required to share the arbiter but claim schema assumed every owner had a capability job | `owner_kind/owner_id` generalized; `capability_job_id` required only for CAPABILITY owner |
| Gateway boundary and Publisher `COMMITTING` ordering ambiguous | fixed order: capability boundary -> COMMITTING -> external effect |
| effective policy mentioned caller tightening without request schema | no generic caller overrides in v0.6 |
| `EXPIRED` omitted from final outcome set and TTL boundary vague | `EXPIRED` final; only before backend submit |
| mutation revision/journal commit ordering implicit | revision durability must precede `MUTATION_COMMITTED` |
| v0.5 `SAFE_ACTIONS` mixed replay safety and mutation semantics | pressHome/pressBack explicitly reclassified as local mutations |
| `OUTCOME_NOT_ACHIEVED` could be misread as retry permission | explicitly no retry; new external attempt requires new job/approval |
| `status` could mutate recovery classification | status read-only; reconcile owns recovery mutation |
| business outcome ambiguity could unnecessarily hold UI forever | UI claim may release once backend liveness is safely resolved, independent of business outcome |

Rev3 的统一 invariant：

```text
One fact -> one durable owner
One UI resource -> one acquisition protocol
One mutation -> one guarded state transition
One external attempt -> one consumed approval / effect boundary
One uncertain outcome -> explicit reconcile, never blind replay
```

---

# 54. Rev3.1 Admission / Fingerprint / Liveness Closure

Rev3.1 不改变 Rev3 的主体架构，只关闭 freeze 后攻防评审中的一个真实 admission gap，并强化两个已有边界。

| Review concern | Rev3.1 closure |
|---|---|
| caller response timeout may create a second independent capability job | mandatory `submission_id` + deterministic capability job ID + durable admission binding |
| concurrent same-submission requests can race | short-lived filesystem `admission.lock` serializes binding compare/create |
| transport retry could be confused with business idempotency | explicitly separate `submission_id` retry identity from future domain idempotency |
| semantic fingerprint could drift into blacklist maintenance | `semantic-v1` becomes allowlist-first; unlisted dynamic attributes excluded by default |
| heartbeat/PID evidence could be misread as lease expiry | explicitly forbid automatic claim release from heartbeat/PID/age alone |
| coordinator hang can block availability | documented as intentional Safety/Consistency > Availability trade-off; doctor/reconcile only |

Rev3.1 新增 invariant：

```text
One transport submission -> one deterministic capability job
One submission ID -> one immutable canonical request
Same submission retry -> same job
New business attempt -> new submission ID
Liveness timeout -> evidence, never release authority
Fingerprint -> allowlisted semantic facts only
```

Rev3.1 仍然没有：

```text
business idempotency service
daemon
scheduler
database
MQ
automatic lease stealing
automatic unsafe retry
```

因此本修订仍符合 Minimal Sufficient Architecture。

---

# 55. Rev3.2 Operational / Durability Closure

Rev3.2 不改变 Rev3.1 主架构，而是补齐 implementation-input contracts。

| Review concern | Rev3.2 closure |
|---|---|
| fsync/rename/ENOSPC | Durability Failure Contract + A41-A43 |
| orphan staging | non-executable + doctor/GC |
| permission tamper | lstat/owner/mode/symlink fail-closed |
| storage growth | explicit GC, no daemon |
| blocked reconcile operations | doctor visibility + audited ADMIN force-reset |
| ADMIN token continuity | epoch bump before unknown/mutating ADMIN dispatch |
| clocks | realtime absolute TTL + boottime deadline/age |
| semantic-v1 compatibility | exact schema + fixed SHA-256 vectors |
| subordinate trace | mandatory provenance + SUBJOB_BOUND |
| error carrier | machine-readable CLI/Python envelope |
| admission starvation | 5000ms bounded wait |
| upgrade/rollback | gated on-device migration |

仍不引入 daemon/MQ/DB/scheduler/background GC/automatic lease stealing/business-idempotency service。

---

# 56. Rev3.3 Controller / Overlay / Zombie Closure

Rev3.3 只关闭 Rev3.2 之后仍存在的三个端到端实施缺口：

| Concern | Rev3.3 closure |
|---|---|
| official upstream creates a new submission ID after timeout/busy | normative bounded retry/status/reconcile contract; same intent keeps same submission ID |
| Activity/package unchanged while dialog/window covers target | mandatory global blocking-overlay guard + semantic-v1 fields + app-modal selector fallback |
| stale claim diagnosis lacks operator-grade process classification | boot/PID/start-ticks `/proc` classification + machine-readable recommended action |

仍然坚持：

```text
no business-idempotency engine
no automatic claim stealing
no daemon
no background reconcile
```

因此 Rev3.3 强化的是端到端 safety contract，不改变 MSA 主体。

---

# 57. Rev3.4 Documentation / Ops Closure

Rev3.4 不增加新的执行层或持久化子系统，只把实施/运维时最容易产生“理解偏差”的内容变成 normative contract：

```text
Glossary
Reboot recovery reference flow
Operational alert semantics
Machine-executable preflight checklist
Fault-injection harness
fsync performance counters
Catalog overlay-policy validation
```

因此 Rev3.4 是 documentation/operations closure，而不是 architecture expansion。

---

# 58. Rev3.5 Unified Architecture / Deep Consistency Closure

Rev3.5 的外部参考来自 `StayLameBro/backburner`，但采用的是 **design transfer**，不是代码/平台移植。

| Backburner 中可迁移的设计 | Y700 Rev3.5 吸收方式 |
|---|---|
| worker 连接后先 advertise protocol / capability / memory/readiness | `node-health.json` schema v2 + `capctl list/describe/doctor` readiness advertisement |
| device alive 不等于 worker ready | 明确 `alive/reachable != READY != safe-to-mutate` |
| 小任务本地、大任务达到 break-even 才 offload | Section 42.1 measurement-gated placement；v0.6 不实现 router |
| optional accelerator failure 可退回主机，而 unique state loss 不可透明 fallback | Section 5.13 / 21.1：OPTIONAL / RECONSTRUCTIBLE_PRE_EFFECT / EXCLUSIVE_OR_UNCERTAIN |
| unique remote state / effect ambiguity 决定故障语义 | 复用 deterministic backend、resource claim、MUTATION_PREPARED、effect boundary、reconcile；不新增第二 state machine |
| raw worker services 不直接暴露不可信网络；通过单一安全 tunnel/gateway | Section 36.6：remote transport 只终止于 trusted control/Gateway boundary |
| 每个优化 threshold 都有真实 benchmark 证据 | performance guardrail 要求 workload/device/version/date 可追踪的 break-even measurement |

Rev3.5 **明确不吸收**：

```text
iOS Sidecar app
Metal / Apple Neural Engine / SME2
Qwen / llama.cpp fork
split prefill
remote KV cache
split decode
two-phone compute chain
Noise tunnel 的具体实现
```

原因：

- 它们解决 Apple 本地 LLM inference，不是 Y700 Android automation 的当前问题；
- 直接移植会引入 Qualcomm/Vulkan/QNN/Android USB 等新的大规模 runtime；
- 当前 Y700 的价值在 capability runtime / safe automation，而不是把 Y700 变成 Mac 的 LLM accelerator；
- 违反 YAGNI / Minimal Sufficient Architecture。

Rev3.5 新 invariant：

```text
One static capability contract -> one canonical Catalog definition
One dynamic readiness view -> advisory evidence only
One execution attempt -> existing deterministic backend identity
One dependency failure -> fallback only if state/effect facts prove it safe
One remote trust edge -> Gateway/control-plane, not per-backend exposure
One optimization threshold -> measured break-even before architecture expansion
```

仍然没有：

```text
daemon
MQ / DB
adaptive scheduler
cross-runtime failover
generic dependency graph
background health heartbeat
business-idempotency engine
automatic claim stealing
```

因此 Rev3.5 扩展的是 **可发现性、可诊断性与未来扩展边界**，不是增加新的执行平台。

---

## 58.1 Deep Consistency Closure

Rev3.5 针对 Rev3.4 Freeze Review 的 temporal/causal/failure/layering 交叉检查，关闭以下问题：

| Freeze Review finding | Rev3.5 resolution |
|---|---|
| backend binding durable before resource，但 pre-submit terminal outcome 描述不统一 | `backend.json` 明确为 immutable derived intent；BACKEND_BOUND/WAITING_RESOURCE/RESOURCE_ACQUIRED 在 submit 前统一允许 EXPIRED/CANCELLED/FAILED，unknown existence -> RECONCILE_REQUIRED |
| no-daemon + stale durable claim 可能造成永久 availability deadlock | 明确 normal `capctl reconcile` 的 positive-proof release authority；status/doctor 仍 read-only，ADMIN 只用于 unknown/coercive reset |
| semantic-v1 对 text/content-desc 的 watched/omit 规则未形成 schema | 新增 versioned `fingerprint_profile_id` + `watch_element_optional/watch_properties`；unwatched omit、watched null、unavailable fail-closed |
| RECONCILE_REQUIRED 无 result.json，Controller completion semantics 不明确 | `state.json` 定义为 live lifecycle authority；status 返回 `lifecycle_state/terminal/next_action`；RECONCILE_REQUIRED 立即转 reconcile |
| reconcile 获取新 claim 与 old subjob exact claim guard 表面冲突 | 保留 exact claim guard；claim_id 定义为 ownership-session identity；reconcile 新建 subjob 绑定新 claim，旧 subjob 永远 stale |
| overlay guard 可能把 IME/Toast/secondary window 全误判 | 改为 classified candidate algorithm；IME/Toast 不因存在阻断；unknown focus/input-intercepting overlay 仍 fail closed |
| BOOTTIME suspend behavior 未解释 | 明确 suspend 计时是 deliberate safety choice；resume 后 stale token fail closed + fresh AUTO preflight |
| fixed 5s admission wait 在 I/O spike 下缺少工程 gate | 5000/10000/15000ms measured deployment constant + p99 load acceptance；timeout same-submission retry |

### One review suggestion intentionally not adopted literally

Freeze Review 建议在 reconcile 后“只校验同一 `capability_job_id` 即可通过 resource_guard”。Rev3.5 **不采用该放宽**，因为它会允许旧 claim session 下创建的 stale mutating subjob 在新 claim 下继续执行，重新打开 replay/interleaving window。

Rev3.5 的闭环方式是：

```text
same capability_job_id/top_backend_job_id
        +
new resource ownership session -> new claim_id
        +
new reconcile/verify subjob binds exact new claim_id
        +
old subjob keeps old claim_id and must fail if replayed
```

因此同时满足：

```text
multi-phase reconcile can reacquire UI
AND
exact stale-claim protection remains intact
```

### Rev3.5 freeze invariants

```text
Binding identity may outlive execution, but never implies submission.
Only resources with positive proof that all mutators cannot continue are recoverable by explicit deterministic reconcile.
Unknown liveness is never converted into availability by guessing.
Live lifecycle state and terminal outcome are different durable facts.
A claim is an ownership session, not a capability-lifetime token.
A stale subjob can never inherit a new claim implicitly.
Fingerprint omission is contract-driven, never runtime-accidental.
Suspend invalidates stale observations by design.
Window presence is not equivalent to blocking semantics.
Availability tuning may change bounded wait, never correctness identity.
```

---

## 58.2 Preservation of Rev3.4 Frozen Ops/Implementation Gates

Rev3.5 Unified **does not delete or downgrade** the Rev3.4 Frozen implementation-input closures. The following remain normative release gates:

```text
Normative Glossary
full-device reboot recovery reference flow
Operational Alert Rules
machine-executable implementation preflight
fault-injection harness / named durability boundaries
Sprint-0 fsync count/latency baseline
Catalog overlay-policy validation
CI blocking semantic vectors / durability ordering / no-blind-replay tests
```

Any implementation claiming Rev3.5 conformance must satisfy both the deep-consistency deltas and the preserved Rev3.4 operational gates.

---

# 59. Final Product Statement

v0.6 Rev3.5 Unified 的目标不是把 Y700 做成“Android Kubernetes”、异构计算集群或通用 workflow platform。

它只增加当前增长阶段真正需要的三项基础能力：

```text
1. 一个稳定、可发现、policy-bound 的 Capability Gateway；
2. 一个 stale/crash-aware 的 deterministic Android mutation contract；
3. 一个不成为 authority 的 runtime readiness / compatibility advertisement layer。
```

最终形成：

```text
Controller decides WHAT
        ↓
Gateway decides WHETHER / under what policy
        ↓
Readiness view says WHAT appears usable now (advisory)
        ↓
Core decides HOW to mutate safely (authoritative)
        ↓
Bridge guarantees durable privileged execution
        ↓
Verifier proves WHAT actually happened
```

并遵循：

> **No new abstraction may weaken durable ownership, immutable-request binding, unsafe-effect boundaries, crash ambiguity handling, or no-blind-replay guarantees already present below it.**

Rev3.5 额外要求：

> **No readiness signal may become execution authority; no fallback may cross an uncertain state boundary; no routing optimization may exist without measured end-to-end benefit.**

这就是 v0.6 的 Minimal Sufficient Architecture。

---

# Appendix A — Normative Glossary

| Term | Normative meaning |
|---|---|
| Capability Job | Gateway orchestration record for one admitted intent; owns request/policy/orchestration state, not low-level execution truth |
| Backend Job | Deterministically bound top-level executor job for a capability |
| UI Job / Subordinate Job | Workflow-scoped internal execution unit below a top-level backend; cannot become a second top-level retry backend |
| `submission_id` | Caller-generated identity for one transport submission; reused for retries of the same intent; not business idempotency |
| `request_sha256` | Hash of canonical immutable request used for binding/approval/contract integrity |
| `android_ui` | Sole v0.6 exclusive UI mutation resource |
| `flock` | Kernel transient mutual exclusion primitive; process loss releases it |
| Durable Claim | Persistent semantic resource ownership record; survives coordinator death and is not invalidated merely by flock release |
| `owner_kind=CAPABILITY` | Claim owner is a capability execution path |
| `owner_kind=LEGACY` | Migration-time legacy production path using the same canonical arbiter |
| `resource_guard` | Exact claim identity propagated to Core and asserted before mutation |
| `state_epoch` | Coarse continuity generation; bump invalidates all prior state tokens after reset/unknown ADMIN mutation/corruption |
| `revision` | Monotonic durable count of successful Core-tracked UI mutations |
| `state_hash` | `semantic-v1` hash of allowlisted safety-relevant UI facts |
| State Token | Observed `(epoch, revision, semantic hash, boot-aware age)` proof used by compare-before-mutate |
| `MUTATION_PREPARED` | Durable pre-mutation journal boundary; presence does not prove action occurred |
| `MUTATION_COMMITTED` | Durable postcondition-success journal fact written only after revision advance is durable |
| `EFFECT_BOUNDARY_CROSSED` | Capability-level durable pre-effect barrier; crossing consumes approval and forbids blind external-effect retry |
| `COMMITTING` | Existing business/backend-specific marker below the capability effect boundary and before the actual irreversible click |
| `VERIFIED` | Terminal positive business outcome proved by verifier |
| `OUTCOME_NOT_ACHIEVED` | Terminal positive evidence that requested business outcome did not occur; does not grant automatic retry |
| `FAILED` | Terminal confirmed pre-unsafe-boundary failure |
| `CANCELLED` | Terminal cancellation only after execution is safely stopped/classified |
| `EXPIRED` | Terminal stale intent only before backend submission |
| `RECONCILE_REQUIRED` | Non-terminal active blocked state: execution/outcome uncertainty requires explicit reconcile; no final result yet |
| `RESOURCE_RECONCILE_REQUIRED` | Resource ownership durability/liveness ambiguity requiring explicit resource recovery |
| Blocking Overlay | Unexpected top-level/dialog/modal condition that makes target mutation unsafe even if Activity/package is unchanged |
| `status` | Strictly read-only inspection |
| `reconcile` | Explicit recovery operation for an existing job; may mutate recovery/orchestration state but never blindly repeat unsafe effect |
| ADMIN Force Reset | Audited unsafe escape hatch to restore future UI mutation safety; bumps epoch and never claims to undo/resolve prior business effect |
| MSA | Minimal Sufficient Architecture: add only mechanisms required for current correctness/capability growth; defer platform infrastructure until measured need |

---

| `fingerprint_profile_id` | Versioned contract selecting optional semantic fields watched by a token/action; profile mismatch fails before mutation |
| Ownership Session | One concrete `android_ui` claim lifetime identified by exact `claim_id`; a capability may have multiple sequential sessions during reconcile |
| `READY` | Advisory current readiness evidence for a capability; never permission to mutate |
| `DEGRADED` | Only allowed when missing component is statically non-safety-critical and semantics/verifier remain unchanged |
| `STOPPED` process | Exact process identity exists but is stopped and may resume; never sufficient release proof |
| `ZOMBIE` process | Process has exited execution; may contribute to positive stop proof together with backend/subjob facts |
| Positive Stop Proof | Independent exact evidence that backend and all UI mutators cannot continue; authorizes normal reconcile claim cleanup, not business-outcome inference |
| `state.json` | Authoritative live capability lifecycle state, including non-terminal blocked states |
| `result.json` | Final terminal business outcome marker only; absent while `RECONCILE_REQUIRED` |
| Execution Profile | Static placement/foreground/readiness constraints; not scheduler/replay permission |

| Capability Transition Lock | Per-capability ephemeral flock used only to serialize lifecycle transitions such as cancel vs unsafe-boundary crossing; never durable authority or UI resource ownership |
| App/UI Contract | Versioned binding between app package/build/signing identity and tested selectors/modal/commit/verifier semantics; mismatch makes app-specific mutating capability UNAVAILABLE |
| UI Quiescence | Positive evidence that prior backend/subordinate mutators can no longer dispatch/complete Android UI mutations; required before ADMIN claim release |
| Reconcile Dwell Age | Observability-only age since a job entered RECONCILE_REQUIRED; never cleanup/replay authority |

# Appendix B — semantic-v1 Canonical Reference

`fingerprint_profile_id` 绑定在 token/action contract 中，不进入 canonical JSON bytes；producer/consumer 在 hash compare 前必须 exact-match profile。

Vector 1（profile `semantic-v1.foreground-base.v1`）：

```json
{"fingerprint_version":"semantic-v1","foreground":{"activity":"com.android.settings.Settings","package":"com.android.settings"},"scope":"FOREGROUND","screen":{"blocking_overlay_class":null,"blocking_overlay_owner_package":null,"blocking_overlay_present":false,"interactive":true,"keyguard_locked":false}}
```

```text
sha256:074e74b0f725954b789fea7d905715c7e096c4ab159029a1c6c8ef8a6b610b66
```

Vector 2（profile `settings.switch.element-base.v1`，不 watch optional text/content-desc）：

```json
{"cardinality":1,"element":{"checked":true,"clickable":true,"enabled":true,"selected":false},"fingerprint_version":"semantic-v1","foreground":{"activity":"com.android.settings.Settings","package":"com.android.settings"},"scope":"ELEMENT","screen":{"blocking_overlay_class":null,"blocking_overlay_owner_package":null,"blocking_overlay_present":false,"interactive":true,"keyguard_locked":false},"selector":{"resource_id":"android:id/switch_widget"}}
```

```text
sha256:6bab7e2cd22bb7e2804f75638edfda2546f73802003c57fde3ecbdd322f32fd4
```

# Appendix C — Minimum Operational Runbook

```text
capctl doctor
capctl status <job>
capctl reconcile <job>
capctl reconcile-resource --claim-id <claim>
capctl gc --dry-run
capctl gc --apply --older-than <duration>
capctl admin force-reset-ui-runtime --claim-id <id> --reason <text>
```

Normal operation must never manually delete `android-ui.claim.json`, never treat heartbeat timeout/PID absence/STOPPED state alone as release authority, never retry an external effect from RECONCILE_REQUIRED, never bypass ADMIN epoch invalidation, and never GC active/reconcile/effect evidence. When exact process + backend + subordinate-job facts positively prove the UI mutator stopped, use normal `capctl reconcile` to release the exact claim; reserve ADMIN force-reset for unresolved/coercive recovery.

Runbook 必须另外包含：

```text
Safety > Availability / DEVICE_BUSY escalation
HIGH/CRITICAL alert handling
LOW_SPACE periodic explicit GC procedure
full-device reboot -> doctor/status/reconcile flow
READY/DEGRADED/UNAVAILABLE -> inspect reason codes; readiness never bypasses execution guards
STOPPED process -> do not release; ZOMBIE/DEAD/PID_REUSED still require backend/subjob positive-stop proof
ADMIN force-reset warning:
  "This operation does NOT unconditionally delete ownership.
   The claim is released only after UI-mutation quiescence is proven.
   It does NOT undo or prove the outcome of any prior external side effect.
   If quiescence cannot be proven, the claim remains and mutating BUSINESS work stays blocked.
   The affected capability remains RECONCILE_REQUIRED until explicitly reconciled."
```

---

# Review Approval Record

```text
PRD version: v0.6 Rev3.6 Frozen — Targeted Red-Team Consistency Closure
Status: FROZEN ARCHITECTURE + IMPLEMENTATION-INPUT SOT — APPROVED
Architecture approved: YES
Production Runtime Implementation authorized: NO
Phase 0B validation tooling authorized: YES
Canonical implementation-input SOT: v0.6 Rev3.6 Frozen
Supersedes: v0.6 Rev3.5 Frozen
Review basis: independent Red Team + targeted Freeze Review covering A0-A88, cancel/effect-boundary races, ADMIN quiescence, lifecycle durability, lock ordering, terminal-result linearization, governance authorization, LEGACY recovery addressability, app/UI compatibility TOCTOU, time-source evidence, reconcile dwell, backend never-created proof, and pre-implementation-vs-sprint-gated machine checks
Review date: 2026-10-05
Decision: FROZEN AS REPO SOT — no remaining Critical/High internal-consistency blocker identified in the targeted Freeze Review
Implementation gate: Phase 0A passive evidence -> Phase 0B validation tooling (AUTHORIZED) -> pre-implementation empirical gates PASS -> separate Production Runtime Implementation Authorization -> Sprint 1
Notes: Freeze approval authorizes only Phase 0B validation tooling/tests/evidence collection. It does not authorize production Gateway/Core/Bridge behavior changes. SPRINT_GATED checks become blocking only after their owning implementation Sprint exists, while final v0.6 DoD still requires all applicable checks PASS.
```
