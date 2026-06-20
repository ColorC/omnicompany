<!-- [OMNI] origin=ai-ide domain=services/omnicompany ts=2026-05-04T14:15:00Z type=doc status=active agent=ai-ide belongs_to_service=omnicompany -->
<!-- [OMNI] summary="omnicompany service 自我叙事 README — 黑板架构中心承载. Worker/Material/Team 基类 + MaterialDispatcher + 金标范本库. 是其他 agent 建新 Team 必参考的规范权威之一" -->
<!-- [OMNI] why="按 self_narrative_three_files.md §四 模板严格写. 抽核心目的+设计原则到 README, DESIGN 留 Team 新建统一形式硬规则段 (是架构内容)" -->
<!-- [OMNI] tags=readme,omnicompany,core,blackboard,self-narrative -->
<!-- [OMNI] material_id="material:services._core.omnicompany.readme.self_narrative.md"-->

# omnicompany · 黑板架构中心承载

> Worker / Material / Team 基类 + MaterialDispatcher (Worker × EventBus 激活引擎) + 金标范本库. **其他 agent 建新 Team 必参考的规范权威之一** (跟 self_narrative_three_files.md / design_md_template.md 平级).

---

## 这是什么

omnicompany 是 omnicompany 项目的**中心承载 service**. 它有两大职责:

1. **统一 shape 样板的权威实现** — 提供 `Worker` (Router 子类别名) / `Material` (Format 别名) / `Team` (PipelineSpec 别名) 三个基类, 让新代码 `from omnicompany.packages.services.omnicompany import Worker, Material, Team` 直接拿到对的 import.

2. **MaterialDispatcher** — Worker × EventBus 激活驱动. 让 Worker 通过 EventBus (stock) 订阅激活的材料黑板执行器. ~230 行小代码, **不造新 runtime**, 复用现有 EventBus / FactoryEvent / Router. TeamRunner 负责显式 DAG 编排, MaterialDispatcher 负责材料到达后的订阅激活; 二者共享同一 Format/EventBus, 不是二重权威。

3. **金标范本库** — 含 [agent_team_demo.py](agent_team_demo.py) Agent Team 4 Worker 示例 (Context Script / LLM / Tool / Finalizer) + Team 新建统一形式硬规则.

**设计原则** (用户 2026-04-20 洞察):
> "stock 就是 eventbus, 不用想太多, 大部分是重命名 + 设计思维调整 + 原本不严谨的内容清除"

omnicompany 不引入新概念, 只把已有 EventBus + Router 加一层订阅激活 adapter + shape 约定.

跟项目里其他规范权威的关系:
- **omnicompany** (本 service) 管 **代码层** Worker/Material/Team 基类 + dispatcher + Team 新建硬规则 (目录结构 / formats.py / workers/__init__.py / etc)
- **self_narrative_three_files.md** 管 **文档层** README/DESIGN/SKILL 三件套规范
- **design_md_template.md** 管 **DESIGN.md 七节** 模板 (旧规范, 三件套规范立后部分让位)
- **terminology.md** 管 **命名迁移** ABCD 四阶段 (router→worker / format→material / etc)

## 解决什么 / 不解决什么

**解决**:
- 新 Team 建立时该怎么组织目录 / 命名 / 写 formats.py / 写 workers/
- Worker 怎么订阅 Material 激活 (MaterialDispatcher)
- Worker 间数据流过 EventBus (stock) 怎么走
- 子 job 语义 (R-25 `_emit_as_new_job`) 怎么用
- Q4 诊断 (orphan_workers / unconsumed_materials) 给订阅图做静态完整性检查
- 给其他 agent 一个 Agent Team 4 Worker 金标参考

**不解决**:
- 异步并发 dispatcher (Q3 当前同步顺序激活)
- 完整预算机制 (Q2.A 三上限当前只有 max_iterations 兜底)
- Workspace 集成 (F-17 大明文 material 走 WorkspaceWriterWorker, 暂无 pilot)
- 完整 Q2/Q3 预算与并发模型 (当前仍是串行激活 + max_iterations 兜底)

## 设计目的与最终目标

**设计目的**: 给其他 agent / 新代码一个**单一权威**的 import 入口 (`from omnicompany.packages.services.omnicompany import Worker, Material, Team`), 不再每次 grep terminology.md 看"读作什么". 同时 MaterialDispatcher 让 Worker 真能通过 EventBus 跑通 (而不仅是命名上的).

**理论锚点**: 体现 omnicompany 黑板架构 — Worker 不直接调下游, 都通过 stock (EventBus) 异步交互. 跟 LAP 协议第一红线"事件总线驱动" 直接对应.

**最终目标** (当下能认知的):
- 随命名迁移 A→B 推进到位时扩 Team 形式规范
- Phase 1 黑板 pilot 沉淀更多金标 (Diagnosis Agent Worker / WorkspaceWriterWorker / 等)
- dispatcher 优化: 并发激活 / 真 SQLite bus 订阅 / 更高效订阅匹配
- Q2 三上限完整实装 (max_workers_per_job / max_child_jobs / max_job_tree_depth)

## 规划

- **当前 V1 active** (2026-04-20 立档, 2026-06-13 材料统一计划转正): MaterialDispatcher + Worker/Material/Team 别名 + AgentTeam demo + Team 新建硬规则
- **下一步**: 按材料统一计划继续接入公司级 material 事件流与 material registry 收束
- **远景**: Phase 2 完整预算 / Workspace 集成 / SQLiteBus 真跑

## 构成

- 黑板架构核心 → [material_dispatcher.py](material_dispatcher.py) (`MaterialDispatcher` 类 ~230 行)
- 基类承载 → [worker.py](worker.py) (`Worker(Router)` + `Material = Format` + `Team = PipelineSpec`)
- 金标范本 → [agent_team_demo.py](agent_team_demo.py) (4 Worker mock: AgentContextScript / AgentLLM / AgentTool / AgentFinalizer)
- Team 新建硬规则 → [DESIGN.md `## Team 新建统一形式`](DESIGN.md#team-新建统一形式硬规则--其他-agent-必须遵守) (含目录结构 / formats.py 约定 / Worker 基类约定 / workers/__init__.py 清单)

技术架构详述 (含 D1-D5 决策 / 数据流 / Team 新建硬规则段) 见 [DESIGN.md](DESIGN.md), 操作手册见 [SKILL.md](SKILL.md).

## 想了解更多

- 架构 + Team 新建硬规则 → [DESIGN.md](DESIGN.md)
- 操作手册 → [SKILL.md](SKILL.md)
- 文档层三件套规范 → [docs/standards/protocol/self_narrative_three_files.md](../../../../../../docs/standards/protocol/self_narrative_three_files.md)
- 命名迁移 → [docs/standards/terminology.md](../../../../../../docs/standards/_global/terminology.md)
- Worker 设计单 R-01~R-25 → [docs/standards/worker.md](../../../../../../docs/standards/concepts/worker.md)
- Material 五要素 F-01~F-19 → [docs/standards/material.md](../../../../../../docs/standards/concepts/material.md)
- Team 新建参考样本 (类 A 迁移 4 Worker) → [../guardian/workers/](../guardian/workers/)
- 黑板架构 plan → [docs/plans/[2026-04-19]BLACKBOARD-ARCHITECTURE/plan.md](../../../../../docs/plans/%5B2026-04-19%5DBLACKBOARD-ARCHITECTURE/plan.md)
- 项目根叙事 → [../../../../../README.md](../../../../../../README.md)
