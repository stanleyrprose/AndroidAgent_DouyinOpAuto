# PRD — Y700 Android Automation Core v0.6 Rev3.7

## Capability Gateway + Deterministic Execution, State Integrity, Conditional Dispatch, Frame Freshness & Runtime Lifecycle

**文档状态**：FROZEN ARCHITECTURE + IMPLEMENTATION-INPUT SOT — Rev3.7 Cross-Cutting Runtime Contract Update  
**版本**：v0.6 Rev3.7 Frozen — Rev3.6 Frozen Baseline + Capability/Permission, Conditional Dispatch, Frame Freshness, Patch Lifecycle & Stage Diagnostics Closure  
**日期**：2026-10-08  
**目标设备**：Lenovo Y700 / TB323FU / Android 16 / Debian 13 chroot  
**Canonical Repository**：`stanleyrprose/AndroidAgent_DouyinOpAuto`  
**Canonical Branch**：`main`  
**Canonical Baseline**：`v0.6 Rev3.7 Frozen`；自本次 Freeze Approval 起 supersedes Rev3.6 Frozen，成为唯一 frozen implementation-input SOT。  
**实施授权**：**AUTHORIZED — Phase 1 / Sprint 1 + Phase 1A / Sprint 1A ONLY。用户于 2026-10-08 明确要求继续落地 Rev3.7；该授权在本次 Freeze Approval 后生效。Sprint 2+、BUSINESS activation、effect-boundary/approval、new daemon/MQ/DB、cross-device scheduler 仍未授权。**

**本文档取代/合并：**

1. `PRD-Y700-Android-Automation-Core-v0.6-Deterministic-Execution-State-Integrity.md`
2. `PRD-Y700-Android-Automation-Core-v0.6-Capability-Gateway.md` 的 Capability-first、namespace、TTL/expiration、Adapter、discovery/health、transport boundary、observability、Outcome Contract 与 migration intent；
3. Rev3/Rev3.1/Rev3.2/Rev3.3 已关闭的 concurrency、durability、transport retry、semantic fingerprint、overlay、zombie/liveness、upgrade/rollback 等问题；
4. **Rev3.4 Frozen 的 Documentation/Ops/Preflight Closure 全量保留**：Glossary、reboot recovery reference flow、operational alert semantics、machine-executable preflight checklist、fault-injection harness、fsync performance counters、Catalog overlay-policy validation；
5. Backburner 可迁移架构原则：capability/readiness advertisement、`alive != ready`、state ownership 决定 fallback、安全单一 gateway boundary、measurement-gated break-even；**不移植** iOS/Metal/ANE、LLM split-prefill/remote-KV/split-decode 实现；
6. Rev3.5 深层一致性闭环：pre-submit backend terminalization、deterministic claim reconcile、STOPPED/ZOMBIE 分离、fingerprint profile/watched-field schema、`state.json`/`result.json` 语义分离、claim-session rollover + stale-subjob rejection、overlay window classification、suspend/BOOTTIME、admission-lock load gate。

7. Rev3.6 targeted Red Team closure：cancel/effect-boundary linearization、ADMIN reset quiescence proof、`state.json` crash-safe lifecycle persistence、Phase 0A/0B authorization split、LEGACY resource reconcile addressability、app/UI contract compatibility、cross-environment BOOTTIME validation、CLOCK_SUSPECT reboot semantics、reconcile dwell observability、backend never-created positive-proof predicate。

8. **Rev3.7 cross-cutting runtime closure**：在不引入新 daemon/MQ/DB/fleet scheduler 的前提下，新增并冻结以下五个原则：
   - `Capability != Permission`：设备/adapter 能否完成某类动作，与当前请求是否被 policy/approval 允许，必须分别建模；
   - `Conditional Dispatch`：执行路径由 target state + device/UI evidence + action contract 决定，不把所有操作强制塞进同一 UI/Vision/host primitive；
   - `Frame Freshness`：任何基于 screenshot/frame 的定位结果必须绑定 exact frame identity、boot、revision、rotation/display 与 monotonic age；
   - `Patch Lifecycle`：已部署节点必须能识别旧 runtime/schema，使用 immutable release + atomic switch + bounded auto-upgrade + reversible rollback；
   - `Stage Diagnostics`：connectivity / observation / frame / localization / dispatch / postcondition / business verification 分层报告，禁止用单一 `healthy=true` 掩盖根因。

> **Rev3.7 authority rule**：Rev3.7 Frozen 自本次 Freeze Approval 起 supersede Rev3.6 Frozen 作为 implementation-input SOT。Rev3.6 既有 acceptance evidence 仅在 authority assumptions 未被 Rev3.7 delta 改变时继承；本次 production implementation authorization 只覆盖 Sprint 1 + Sprint 1A。

---

# 0. Executive Summary

Y700 Android Automation Core v0.5 已完成 generic Android automation runtime 的核心基础：AndroidX UI Automator 2.4 driver、workflow-scoped instrumentation、semantic selector、deterministic cardinality、bounded retry、failure evidence、checkpoint、cooperative cancellation、driver reset、Bridge v2 integration，以及真实 Settings / TikTok DRY_RUN 验收。

随着 Y700 很快承担更多 Android 自动化能力，下一阶段出现三个相互关联的问题：

1. **Capability growth**：Cloud ChatGPT、Telegram、Hermes、未来其他 Agent 不应继续直接理解每个 app/controller/backend 的内部实现，需要一个稳定、可发现、可审计的 capability interface。
2. **State integrity**：Agent 观察 Android 状态与真正执行 mutation 之间可能发生状态漂移；多个自动化入口、用户手工触屏、runtime crash 都可能让旧判断变成危险动作。
3. **Runtime readiness / fallback ambiguity**：设备或进程“还活着/可连接”不代表某个 capability 当前可安全执行；同样，某个依赖失败后能否降级、重建或 fallback，取决于当前 state ownership、backend/effect phase，而不能由 controller 临时猜测。

v0.6 Rev3.5 以 **Rev3.4 Frozen** 为 canonical mother baseline：完整保留其 Documentation/Ops/Preflight closure，并合入 Backburner-derived readiness/fallback/secure-boundary/measurement guardrail，再关闭 Freeze Review 发现的深层时序与接口语义缺口：**pre-submit terminalization、deterministic resource reconcile、fingerprint profile/watched-field determinism、blocked-vs-terminal status semantics、claim-session reacquisition、overlay classification、suspend invalidation 与 admission-lock load behavior**。Rev3.5 仍不扩大 runtime 基础设施。

Rev3.6 不改变上述架构方向，只对 Red Team 暴露的 implementation-determinism gaps 做窄修订：**cancel/effect-boundary concurrency、ADMIN reset quiescence、lifecycle state durability、Phase 0 authorization semantics、LEGACY resource recovery addressability、app/UI runtime compatibility 与时间/恢复证据闭环**。

Rev3.7 继续保持 MSA，但补上设备 Agent 在真实长期运行中暴露出的五类 cross-cutting 缺口：

1. **能力与权限解耦**：`SUPPORTED` 不等于 `ALLOWED`，policy denial 不能把真实设备能力伪装成 `UNAVAILABLE`；Catalog 漏宣告也不能直接证明设备不具备能力；
2. **条件执行路径**：同一个目标状态可以经 semantic UI、fresh-frame vision、host primitive 或 verified no-op 达成；route 必须 versioned、deterministic、可审计，而不是所有请求都强制走同一 pipeline；
3. **画面新鲜度**：frame/locator result 是带时序与状态绑定的 evidence，不是永久真相；任何 mutation 前必须证明 frame 仍属于当前 boot/revision/display/rotation/foreground；
4. **补丁生命周期**：runtime 必须能识别自身 release/schema level，支持 quiescent staged upgrade、自动安全 patch、last-known-good rollback 与不确定升级 reconcile；
5. **分阶段故障模型**：连接、取帧、定位、动作 dispatch、postcondition 与 business verification 分开建模，aggregate health 只做摘要，不作为根因或 mutation authority。

Rev3.7 的核心意图不是增加更多组件，而是把“**能做什么、现在允不允许做、应该走哪条路径、看到的是不是最新状态、失败发生在哪一层、已部署实现如何安全演进**”变成可机器检查的独立事实。

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
Capability support / permission / readiness three-axis model
Deterministic conditional-dispatch route contract inside canonical Y700 runtime
Frame freshness token + locator-to-frame binding for all visual-assisted mutations
Immutable release manifest + deployed runtime version detection + safe patch upgrade/rollback
Stage-level health/failure evidence; aggregate health is summary only
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
generic rule-language / dynamic route optimizer
continuous screen-stream daemon solely for freshness
background fleet-wide auto-upgrade daemon
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

\n## 5.17 Capability Is Not Permission\n\nRev3.7 强制把三个事实拆开：\n\n```text\nsupport_state\n= 设备/runtime/adapter 是否具备完成该 capability 的实现与兼容条件\n\npermission_state\n= 当前 caller/request/policy/approval 是否被允许发起该 capability\n\nreadiness_state\n= 当前时刻 mandatory runtime dependencies / resource / reconcile 状态是否可开始\n```\n\n禁止：\n\n```text\npermission denied -> capability=UNAVAILABLE\ncatalog omission -> capability=UNSUPPORTED\nREADY -> permission automatically ALLOWED\nSUPPORTED -> safe to mutate now\n```\n\n最小状态：\n\n```text\nsupport_state = SUPPORTED | UNSUPPORTED | UNKNOWN\npermission_state = ALLOWED | DENIED | APPROVAL_REQUIRED | POLICY_UNRESOLVED\nreadiness_state = UNKNOWN | READY | DEGRADED | BUSY | BLOCKED_RECONCILE | UNAVAILABLE\n```\n\n规则：\n\n1. static Catalog 是 capability contract SOT，但 **Catalog 的缺失/禁用本身不能作为物理能力不存在的唯一证据**；若 runtime/adapter probe 发现实现存在但 Catalog 未声明，必须返回 `CAPABILITY_CATALOG_DRIFT` / `support_state=SUPPORTED_UNADVERTISED|UNKNOWN` 的诊断，不得伪装成 hardware/runtime unsupported；\n2. shipping BUSINESS mutation 仍必须有 versioned contract 才能执行；“设备其实会做”不能绕过 contract/policy；\n3. policy/approval 只改变 `permission_state`，不能改写 `support_state`；\n4. permission denial 的错误码必须是 `PERMISSION_DENIED` / `APPROVAL_REQUIRED`，不能复用 `CAPABILITY_UNAVAILABLE`；\n5. support/readiness evidence 可以 fail closed，但不得通过错误 capability declaration 产生不可诊断 false negative；\n6. `capctl list/describe/doctor` 必须同时展示 support / permission / readiness 三轴，而不是折叠成一个 status。\n\n因此：\n\n```text\nCapability ≠ Permission ≠ Readiness ≠ Execution Outcome\n```\n\n## 5.18 Conditional Dispatch Follows Target State\n\nRev3.7 不增加 fleet scheduler；它增加的是**单个 canonical Y700 runtime 内部的 deterministic route selection**。\n\n同一 request 的 route 由以下事实共同决定：\n\n```text\ntarget state\ncurrent state evidence\ndevice/app/UI contract\naction class\navailable observation source\nframe freshness\nminimum safety / replay / approval policy\n```\n\n允许的 route class 至少区分：\n\n```text\nVERIFIED_NOOP          # target state 已满足，仅验证，不 mutation\nSEMANTIC_UI            # Accessibility/UI Automator semantic route\nVISION_ASSISTED_UI     # fresh-frame locator + guarded UI action\nHOST_PRIMITIVE         # 已授权、可验证且无需 UI 的 host primitive\nBLOCKED                # 没有满足 contract 的安全 route\n```\n\n规则：\n\n1. route 是 versioned adapter/workflow contract 的一部分；caller 不能临时指定更弱 route；\n2. route 选择必须 deterministic + auditable，并写入 job/action evidence；\n3. target 已满足时优先 `VERIFIED_NOOP`，禁止为了统一流程先改再改回；\n4. visual route 只有在 Section 18.8 Frame Freshness Contract 通过时可用；\n5. `EXTERNAL_IRREVERSIBLE` 默认不得因 semantic route 失败而自动降级到未验收 Vision route；\n6. `HOST_PRIMITIVE` 不等于 ADMIN/root bypass；它仍需 classification、resource/state/effect contract 与 postcondition；\n7. route fallback 仍受 Section 5.13 state ownership/effect phase 约束，不能因“另一条路可用”就 replay 不确定操作；\n8. v0.6 shipping implementation 仍只要求 Y700；device-specific route table 可 versioned，但不实现跨设备 scheduler。\n\n## 5.19 Frame Freshness Is a Safety Precondition\n\n视觉定位错误和**基于过期画面正确定位**是两类风险。后者可能在 locator 完全正确时仍点击错对象，因此 Rev3.7 将 frame freshness 提升为 mutation precondition。\n\n```text\nlocator result is valid only for the exact frame it was computed from\nframe is valid only for the exact device state window it represents\n```\n\n任何 visual-assisted mutation 必须携带 exact `frame_guard`；详细 contract 见 Section 18.8。\n\n## 5.20 Patch Lifecycle Must Be Versioned and Reversible\n\n已部署设备不是 disposable node。Rev3.7 要求 runtime 明确知道：\n\n```text\nwhat release is active\nwhat schema/migration level is active\nwhat last-known-good release is\nwhether this node may auto-upgrade\nwhether rollback is still safe\n```\n\n禁止 in-place 覆盖 production release 后再猜测如何恢复。详细 contract 见 Section 39.8。\n\n## 5.21 Health Is a Pipeline, Not a Boolean\n\nRev3.7 禁止用单一 `healthy=true` 回答“为什么 Agent 不能完成动作”。至少分离：\n\n```text\ncontrol/device connectivity\nobservation source\nframe acquisition\nframe freshness\ntarget localization\npermission/resource/state guard\naction dispatch\npostcondition\nbusiness verification\n```\n\naggregate status 可以用于摘要/告警，但**不能替代 stage evidence，更不能授权 mutation**。详细 schema 见 Section 33。\n\n# 6. Target Architecture

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

\n## 7.4 Conditional Dispatch Contract\n\nGateway/Adapter 在 backend dispatch 前必须解析一个 `execution_route`：\n\n```json\n{\n  "route_version": 1,\n  "route_id": "tiktok.upload.semantic-ui.v1",\n  "route_class": "SEMANTIC_UI",\n  "selected_for": {\n    "target_state": "POST_CONFIG_READY",\n    "device_contract": "y700-android16-zui",\n    "evidence_revision": 42\n  }\n}\n```\n\n`execution_route` 必须：\n\n- 来自 versioned adapter/workflow route table，不由 caller 任意构造；\n- 在 action journal / backend evidence 中可追踪；\n- 不能改变 minimum policy、replay class 或 effect boundary；\n- route 切换前若已有 mutation/effect ambiguity，必须先 reconcile，不得透明 fallback；\n- route 所需 observation source/frame/locator/primitive 不 ready 时返回明确 stage error，而不是笼统 `UNAVAILABLE`。\n\n最小 deterministic selection：\n\n```text\nif target_state already proven:\n    VERIFIED_NOOP\nelif exact semantic route contract matches and semantic target is available:\n    SEMANTIC_UI\nelif visual route is allowed for this action class and fresh frame + locator contract pass:\n    VISION_ASSISTED_UI\nelif versioned host primitive exists and is allowed for this action class:\n    HOST_PRIMITIVE\nelse:\n    BLOCKED\n```\n\n这不是 generic workflow engine：route table 仍由少量 shipping adapter 显式编码并 versioned test。\n\n# 8. Capability Classification

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