<!-- [OMNI] origin=claude-code domain=standards ts=2026-04-19T00:00:00Z type=doc status=active -->
<!-- [OMNI] material_id="material:standards.global.terminology_migration_mapping.md" -->

# 术语迁移规范（Terminology Migration）

> **状态**: active · 2026-04-19 立档
> **上游决策**: [`docs/plans/[2026-04-19]BLACKBOARD-ARCHITECTURE/plan.md`](../plans/[2026-04-19]BLACKBOARD-ARCHITECTURE/plan.md) §三 Q1 + §五
> **强制等级**: 新代码 MUST; 旧代码 grandfathered
> **Guardian 规则**: OMNI-036（新 module 用旧名 → WARN）

---

## §1 为什么改名

OmniCompany 是一个**自己编辑自己**的软件。命名不只是给协作者看，更是给自己（LLM）读自己代码时的**认知查询词典**。
"材料 / 工人 / 车间 / 部门 / 公司" 这套隐喻直接对应 self-portrait、订阅关系、职责边界这类高频查询——语义贴合降低推理层数。
改名不是美化，是**认知加速器**。

---

## §2 层级对照表

```
OmniCompany                           [项目]  ← 原 omnicompany
  └─ Department                       [域]    ← 原 packages/services/ + packages/domains/
        └─ Team                       [团队]  ← 原 pipeline
              └─ Worker               [工人]  ← 原 router
                    消费/产出 Material [物料]  ← 原 format
                    存 Stock           [库存]  ← 原 eventbus

贯穿层: Job                            [作业]  ← 原 run / trace (一次外部作业)
特殊 Department: 行政部 = 核心基础设施 (服务全公司, 非业务)
  - runtime/*                 (执行 / 观察 / agent / info_audit)
  - packages/services/guardian   (自检查员)
  - packages/services/doctor     (诊断员)
  - packages/services/registry   (户籍)
  - packages/services/repair     (修理员)
  - packages/services/selftest   (自测)
```

**为什么选这组词**：

| 新名 | 选用理由 |
|---|---|
| Material | 强调"可消费的实体"而非仅 schema |
| Worker | 强调"主动认领"而非机械转发 |
| Stock | 强调"存货仓"而非瞬时消息流 |
| Team | 一组工人协作完成一类任务 |
| Department | 一个部门统管一类职责 (一组 Team) |
| OmniCompany | 多部门协作的"自治组织" |
| Job | 一次外部订单作业 (继承原 run_id) |

---

## §3 自底向上替换顺序（硬规则）

**从数量最多的底层先换**，下层未 100% 替换完 **禁止** 向上推进：

| Phase | 替换对象 | 理由 |
|---|---|---|
| **A** | Material + Worker | 底层 primitive, 数量最多 (338 router / 161 format) |
| **B** | Team + Stock | 容器层 (48 pipeline + 1 eventbus) |
| **C** | Department | 域层 (services + domains) |
| **D** | OmniCompany | 顶层 (包名 / CLI) |

每 Phase 有 alias 过渡期。**下层未签章完成 → 不得开启上层 Phase**。

---

## §4 过渡期规则

- **新代码**: MUST 用新名（新建的 worker / material / group / etc.）
- **旧代码**: grandfathered, 按自然活跃度被动替换；不强制批量重构
- **Alias 过渡**: 协议层提供等价别名（如 `Material = Format` 一行 export）
- **Sunset 条件**: 某 Phase 的所有旧名使用点 = 0 **且** L1 签章 → 移除该层 alias
- **违反检测**: Guardian OMNI-036 扫新 module 的旧名 import → WARN（不阻塞）

### §4.1 Guardian OMNI-036 规则草案

**ID**: `OMNI-036` · **name**: `new-module-legacy-naming` · **severity**: `MEDIUM` · **disposition**: `[warn]`

**代码位置**: `packages/services/guardian/rules/terminology.py`

**触发条件**（AND）:
- 文件位于 `_NEW_MODULE_WHITELIST` 列表内
- 且源代码文本中出现以下任一：
  - 含 legacy identifier: `PipelineEdge` / `PipelineSpec` （Phase A 可扩展）
  - 含 legacy import pattern: `from omnicompany.protocol.format import Format` / `from omnicompany.protocol.* import PipelineEdge`

**豁免**:
- `_graveyard/` / `_archive/` / `packages/vendors/` 路径
- 白名单外的 legacy 目录（当前全部 legacy）
- alias 协议层代码（`Material = Format` 一行 export 自身）

**当前 Q0 状态**: `_NEW_MODULE_WHITELIST = ()` → 规则实装但暂不触发任何文件。

**Phase A 启用**:
1. L1 将新 module 路径（例如 `src/omnicompany/packages/services/omnicompany/`）填入白名单
2. 该层 alias sunset 时 `severity: MEDIUM` → `HIGH` 并扩展 legacy identifier 列表

**与其他规则关系**:
- **OMNI-033**: 原扫 `forbidden_aliases`（含 worker）已移除 worker 条目，不再误判
- **F-15 / LAP D9**: 按 Material 禁搭便车继续守, 本规则 orthogonal

---

## §5 适用范围

MUST 用新名：

- 代码标识符（类名 / 函数名 / 变量名 / 参数名）
- 文档正文（DESIGN.md / plan.md / standards / README）
- commit message / PR 标题与描述
- 日志 / 事件字段 / trace 标签
- CLI 命令名与 help 文本

MAY 用旧名：

- 引用 legacy API / 导入 legacy 模块时保持原名
- 讨论历史（"当年的 format 体系"）
- alias 过渡期内, 旧代码内部保留

---

## §6 两层命名：protocol 保留 · omnicompany 用新名（2026-04-20 L1 修正）

### §6.1 基本原则

**协议层 (`src/omnicompany/protocol/`) 及核心标准规范 (`docs/standards/concepts/material.md` / `pipeline.md` / `router.md` / `llm_first.md` 等) 保留原抽象名字**: `Router` / `Format` / `Pipeline` / `EventBus`。

**omnicompany 业务/组织层** 用新名: `Worker` / `Material` / `Team` / `Stock` / `Department`。

两者是**同构对应**, 不是命名迁移后取代:

| protocol 层 (不变) | omnicompany 层 (新) | 关系 |
|---|---|---|
| `Router` | `Worker` | Worker 本质是 Router 的子类 + omnicompany 术语包装 |
| `Format` | `Material` | Material 是 Format 的一次实例化, 带 job_id / 生命周期语义 |
| `Pipeline` | `Team` | Team 是一组 Worker 的 omnicompany 组织单位; protocol 层仍叫 Pipeline |
| `EventBus` | `Stock` | Stock 是 bus 的 omnicompany 角色名, 强调"存货仓"语义 |

### §6.2 为什么分两层

- **协议层要抽象稳定**: `Router` / `Format` 是数据契约, 命名应通用, 不贴业务组织学
- **omnicompany 层要贴业务**: 工人认领物料, 部门协作完成订单 — 这些词帮 LLM 建立高质量心智模型
- **语义升级不是取代**: Material 比 Format 多了"可消费实体 + 生命周期 + 流通状态", 但底层仍是 Format schema

### §6.3 何处用哪个（2026-04-20 修正 · 规范也用新命名主体）

**旧规范被新命名顶掉**, 不保留严格双轨, 旧命名仅**一句话带过**作兼容说明。

**protocol 原名保留**（仅以下场景）:
- `src/omnicompany/protocol/` 代码与 DESIGN.md （Python 类名: `Router` / `Format` / `PipelineSpec` 等）
- 代码层类引用 (`class FooRouter(Router):` / `from omnicompany.protocol.format import Format`)
- standards 文档**开头"术语"说明段一句话**: "Format 是 protocol 层类名, 读作 Material"

**omnicompany 新名（主体）**:
- 所有 standards 文档**叙述层**: format.md / router.md / pipeline.md 主体用 Material / Worker / Team
  （条款编号 F-01~F-18 / R-01~R-22 / P-01~P-17 稳定, 内含 "Format" 字样按术语说明段读作 Material）
- `docs/PROGRESS.md`（状态叙述）
- `docs/plans/**` 活跃 plan 的正文叙述（非归档 `_archive/`）
- `docs/reports/**` 新写的报告
- `src/omnicompany/packages/services/<team>/DESIGN.md` 业务层叙述
- `.claude/skills/omnicompany-dev/SKILL.md` 业务教学语境
- CLAUDE.md workspace 指引
- Memory 文件

**规则验证**: 新建文档时用新命名为主; 碰到代码 class 名时保留 protocol 原名。不造双轨噪音。

### §6.4 混用场景（合法）

一段话同时指向两层时, 允许混用并附对应括注:

> "每个 Worker（即 protocol 层的 Router 子类）订阅 Material（即 Format 实例）后激活..."

这种混用是**清晰的**而不是混乱的, 它同时表达了组织语义和底层契约。

### §6.5 Worker 粒度原则（2026-04-20 Patch-1 · guardian Team 1 迁移认知）

**硬规则**: Worker 粒度 = **完整职责 + FORMAT 边界 + 独立测试价值**。**不是"每个函数一个 Worker"**。

**反例**（错误粒度）:
- Guardian 14 条 rule 每条做一个 Worker → 样板代码爆炸 + 把 O(F) 批判断拆成 O(F×R) 激活 + 失去 RuleEngine 简洁性

**正例**（正确粒度 · guardian 4 Worker）:

| Worker | 职责 | 为什么不再细分 |
|---|---|---|
| GitDiffScan | 扫 git 变更 → FileContext 集合 | 扫描是单一动作 |
| RuleEngine | 对 N 文件跑 M 规则 → violation 三分（确认/疑似/重复）| 规则批判断本质是一个"引擎"职责; 内部可继续用纯函数 rule 库 |
| LLMJudge | needs_judgment 子集复核 | 复核是独立 LLM 调用 |
| AuditTow | violation → sink（落盘 + 处置）| 落盘是外部边界动作 |

**判定方法**（写新 Worker 前自问）:
1. 此 Worker 有**明确 FORMAT_IN/FORMAT_OUT 边界**吗？边界模糊 → 合并到上下游
2. 单独写一个**Worker 级集成测试**有价值吗？没价值 → 它只是内部函数, 不该独立 Worker
3. 把职责再拆会变清晰还是更碎？更碎 → 停止拆分

**内部保留纯函数库合法**: Guardian 的 14 条 rule 保留为 checks.py 纯函数, 被 RuleEngineWorker 调用 — 这是 Worker 内部实现选择, 不上升为 Worker 粒度。

**来源**: [`docs/plans/[2026-04-19]BLACKBOARD-ARCHITECTURE/migration_log.md`](../plans/[2026-04-19]BLACKBOARD-ARCHITECTURE/migration_log.md) Team 1 guardian · Patch-1。

---

## §7 Agent Team（纯 bus 驱动的 Worker 组合 · 2026-04-20 Patch-7 修正）

**Agent Team** = 一组 Worker 通过**主 bus** 订阅激活, **不是单 Worker + 迷你 stock**（原 R-19 "Agent Worker" 设计作废）:

- `Context Script Worker` — 组装 LLM 上下文（无 LLM 调用）· FORMAT_IN_MODE=`"or"` 订阅 `agent.request` OR `agent.tool_result`
- `LLM Worker` — 调 LLM 产 response（单轮调用, kind ∈ {tool_call, finish}）
- `Tool Script Worker (N)` — 响应 tool_call, 产 `agent.tool_result` 带 `_emit_as_new_job: True` (触发新子 job)
- `Finalizer Worker` — 响应 finish, 产 `agent.final_output` sink material 终止

**无"迷你 stock"** — 所有 material 流经主 bus, 可被外部审计/replay/调试。

**每轮循环 = 一个子 job**: 发起者 = tool_result 产出（带 `_emit_as_new_job`）, parent_job_id 链 agent 内部因果。Q1 "worker 每 job 单次激活" 和 "agent 多轮循环" 天然兼容（不同 job_id 允许 worker 再激活）。

**升级规则**: LLM Worker 不确定需要什么 material 时, **默认升级为 Agent Team**, 开放 workspace 供 Tool Script Worker 自取。

**Patch-7 pilot 实现**: `packages/services/omnicompany/agent_team_demo.py` 4 Worker mock · 6 测试全过。

**详见**: `router.md` R-19 (修正) / R-20 / R-24 FORMAT_IN_MODE / R-25 子 job。

---

## §8 Workspace（Team 工作空间 + material 本体存储）

**Workspace** = Team 的磁盘工作目录, 保存大明文 material 的本体（database stock 只留指针）。

**命名**: `workspace.<team>.<session_kind>[.<job_id>]`

**读写约束**:
- **写**: 仅 `WorkspaceWriterWorker` 子类可写（避免审计断链）
- **读**: 任意 worker, 建议用 Tool Script Worker 包装

**大明文判定**: ≥ 10 KB 建议走 workspace, ≥ 1 MB 或二进制强制走 workspace。

**详见**: `pipeline.md` P-14 / P-15 / P-16 + `router.md` R-22 + `format.md` F-17。

---

## §9 Diagnosis Agent Worker（质疑上游, 少归因幻觉）

**Diagnosis Agent Worker** = Agent Worker 子类, 内置对上游 material 质疑能力。

**核心原则**（硬规则）: Worker 拿不到 material 或输出异常时, **沿 trace 往上查 material**, **尽量少归因于 LLM 幻觉**。不确定时 → 替换原 LLM Worker 为 Diagnosis Agent Worker 重试。

**特殊工具**:
- `trace_back_tool` — 查 material 上游 producer
- `material_assertion_tool` — 对 material 内容提出假设验证

**输出分支**:
- `diagnosis.material_dispute` → 路由 validator, 可能发新 job 修上游
- 正常 FORMAT_OUT → 说明原 LLM Worker 是被劣质 material 拖累, 非幻觉

**详见**: `router.md` R-21。

---

## §11 Job 发起者（2026-04-20 Patch-8 · Q1.C 扩展）

**Job 的四类发起者**:

| 类型 | 语义 | 实现 |
|---|---|---|
| **Source material** | 用户输入 / 外部事件 / 定时触发 | 外部 `publish` 初始 material event (kind=source) |
| **Tool result** | Agent Team 内 tool 执行返回 | Worker output 带 `_emit_as_new_job: True` → dispatcher 用新 trace_id (parent=触发 event.id) |
| **Validator 发起** | validator worker 判不合格 / 需补 material (Q1.C 已有) | validator Worker 产出带 `_emit_as_new_job` + 新 `job.request` material |
| **Child job (显式)** | worker 显式请求子 job | 同 Tool result, 区分只在语义 |

**parent_job_id 链**: 通过 `payload._parent_job_id` 记录, Q4 诊断追溯 agent 内部因果。

**详见**: `router.md` R-25 + `packages/services/omnicompany/material_dispatcher.py`。

---

## §12 迁移分型（2026-04-20 Patch-2/3/4 · Stage 1 沉淀）

**四分型**（迁移动作差异）:

| 类 | 特征 | 动作 | 时间基线 |
|---|---|---|---|
| **A · 单体旧架构** | 内置 class (RuleEngine 等) + 旧入口文件 | 建 `workers/` + `materials.py` + 归档旧入口到 `_archive/` + 改外部 import | ~1.5 h |
| **B · 原生 pipeline** | 已有 `pipeline.py` + `routers.py` + `formats.py` 三件套 | 标 Material kind + DESIGN.md 填充 | ~0.25 h |
| **B 单体 AgentLoop** | 1 node pipeline 封装 while 循环 | 同 B + DESIGN 写明 R-19 Agent Team 迁移路径 | ~0.2 h |
| **C · 元服务库** | 无 Format/Router/Pipeline 三件套 | DESIGN.md 角色说明 + 概念映射表 + 零代码 | ~0.15 h |

**彻底归档原则**（Patch-2, 类 A 专用）:
- 旧入口文件（如 `patrol.py` / `patrol_runner.py`）归档到 `_archive/`, **不留原地**
- `__init__.py` 保留兼容 shim（re-export 旧 API）
- 外部调用者改 import 路径经 shim
- 测试 import 同改

**Dispatcher pilot 模式**（Patch-5, 用于 B 类验证）:
- 让 Team 通过 `MaterialDispatcher` 跑 Worker 订阅驱动
- 跑不通 = 暴露之前不严谨（F-15 透传 / F-16 错标 / output 约定不一致 等）
- **验证方法而非新需求**（用户 2026-04-20 洞察）

---

## §10 两层命名落地清单（2026-04-20 归档补全）

**protocol 层文件**（保留原 Router/Format/Pipeline 名, 不改）:
- `src/omnicompany/protocol/*`（代码 + DESIGN.md）
- `docs/standards/concepts/material.md` / `router.md` / `pipeline.md` / `llm_first.md` / `information_sufficiency.md` 等（原抽象条款 F-01~F-18, R-01~R-22, P-01~P-17 编号稳定）
- LAP D1-D9 规则原文

**omnicompany 层扩展**（新 omnicompany 概念, 在 standards 末尾"omnicompany 层扩展"节内）:
- `format.md` · F-16 Material kind / F-17 Workspace 映射 / F-18 Job 绑定 / FA-09~FA-12
- `router.md` · R-18 Worker 粒度 / R-19 Agent Worker / R-20 升级 / R-21 Diagnosis / R-22 Workspace Writer / RA-11~RA-14
- `pipeline.md` · P-14 Workspace / P-15 Team-Workspace 关系 / P-16 读写契约 / P-17 生命周期 / PA-12~PA-15

**omnicompany 业务叙述层**（用新名）:
- `docs/PROGRESS.md` / `docs/plans/**` / `docs/reports/**` / `.claude/skills/omnicompany-dev/SKILL.md`
- `src/omnicompany/packages/services/<team>/DESIGN.md`（业务层 DESIGN 叙述）
- CLAUDE.md workspace 指引

---

## 关联

- **Plan**: [`docs/plans/[2026-04-19]BLACKBOARD-ARCHITECTURE/plan.md`](../plans/[2026-04-19]BLACKBOARD-ARCHITECTURE/plan.md) §五（迁移与反倒退协议）
- **Guardian 规则**: OMNI-036（草案在本文 §4 · 代码实现待 Phase A 开启时落地）
- **F-15 承接**: `Material 禁搭便车` = 原 `Format 禁搭便车`（`format.md` F-15）
