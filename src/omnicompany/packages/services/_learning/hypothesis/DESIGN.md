<!-- [OMNI] origin=claude-code domain=services/hypothesis ts=2026-04-20T00:00:00Z type=doc status=active -->
<!-- [OMNI] material_id="material:services.learning.hypothesis.service.design_doc.md" -->

# Hypothesis Service · 设计文档

## 状态

- **版本**: V4（语义判断，取代 V1 四角色）
- **成熟度**: active
- **下一步**: 接入 Guardian Agent 对主题文档做 LLM 巡逻（检查假设是否与新证据冲突）

## 核心目的

把"agent 通过探索学习假设"这件事从 L2 Claude Code 的单 context 手工操作，变成一个有结构的、可观测的、可持久化的多节点系统。

核心区别：
- **之前**：我（Claude Code）在一个 context 里同时扮演 Experimenter + Observer + Reflector，三者无分离，思路忠实度（CoT faithfulness）无保障
- **之后（V4 语义判断）**：Experimenter 自由探索产轨迹；Reflector（AgentNodeLoop）读轨迹 + 当前主题文档，用工具箱直接编辑文档；所有状态判定都是 Reflector 的语义判断（不做自动状态转移、不做自动证据匹配）

## 核心接口

**两个核心 Router**（管线节点）：
- **`ExperimenterRouter`** — AgentNodeLoop，主探索 agent；有内嵌编辑工具 + 写工具 + 读工具；自行决定终止 — [routers.py:77](routers.py#L77)
- **`ReflectorRouter`** — AgentNodeLoop，总结 agent；读 Experimenter 轨迹 + 当前主题文档；用工具箱（add_evidence / set_maturity / create_hypothesis 等）直接编辑文档 — [routers.py:396](routers.py#L396)

**数据层**：
- **`HypothesisStore`** — 假设存储抽象 — [store.py:66](store.py#L66)
- **`HypothesisEntry`** — 单条假设条目（summary / maturity / kind / depends_on / derived_from / contradicts / format_in / format_out）— [store.py:30](store.py#L30)
- **`KHypothesisEntry`** — 主题文档（含 hypotheses 列表 + body 叙事）— 来自 `packages/services/knowledge/schema.py`

**管线入口**：`hypothesis.explore` 管线 — [pipeline.py](pipeline.py)，每个 domain 一份主题文档，落 `data/knowledge/hypotheses/<domain>.md`

## 架构决策

### D1 — 不是传统管线，是自驱动循环

无确定性 exit_format，不注册到 core/pipelines.py。
ExperimenterRouter（AgentNodeLoop）自行决定终止。
后果：dashboard 看不到本管线，但主题文档 `.md` 可单独查看。

### D2 — ObserverNode 已并入 Reflector（V4 取消独立角色）

V1 设计：Observer 是确定性 HARD 节点，LLM 不介入，防止 LLM 给解释。
V4 调整：Reflector 接管 Observer 职责 — LLM 直接读 Experimenter 轨迹（stdout/stderr/tool calls）并做语义判断。
代价：失去"纯事实观察"保障。
为什么可接受：Reflector 只读 Experimenter 的行为轨迹（不读 Experimenter 的推理文字），语义干扰可控。

### D3 — Reflector 的 input F-14 合规

Reflector 接两路输入：factlog（当轮事实）+ store.snapshot（现有假设）。
若只接 factlog，Reflector 会重复发现已知假设（无法去重）。
若只接 store，Reflector 无法做 state_changes（没有证据）。
两者缺一不可。

### D4 — JTMS 用 JTMS 不用 ATMS

场景：单 session 内线性探索，不需要多 context 并行。
ATMS 的多 context 并存 ≈ 我们的 scene_fingerprint（在 entry 级别区分），不需要 store 级别。
代价：依赖链只做一层 depends_on，不做完整 justification set。
若日后跨 session 对比假设，再考虑升 ATMS。

### D5 — 数据路径通过 config.resolve_db_dir("hypothesis")

禁止硬编码 cwd 或绝对路径（铁律 feedback_omnicompany_data_paths）。
落盘路径：`data/knowledge/hypotheses/<domain>.md`（V4 路径，由 KBStore 管理）

### D6 — qwen-3.6-plus 全程，不升级

ExperimenterRouter 和 ReflectorRouter 都用 qwen-3.6-plus（project_llm_model_choice 铁律）。
其余辅助节点（session_init / store_save）是 HARD 节点，不用 LLM。

## 数据流 / 拓扑

```
dispatch(domain, goal, scene)
  │
  ├─ load_or_create_topic_doc(domain)
  │   └─ KBIndex.get("kb.hyp.<domain>") or 新建 KHypothesisEntry
  │
  └─ for iteration in range(max_iterations):
        │
        ├─ [ExperimenterRouter] AgentNodeLoop
        │     读: goal + scene + 当前假设列表
        │     做: 自由探索（跑命令 / 读文件 / 调工具）
        │     出: 行为轨迹（trace）
        │
        ├─ [ReflectorRouter] AgentNodeLoop
        │     读: Experimenter trace + 当前主题文档
        │     做: 工具箱编辑（add_evidence / set_maturity /
        │         create_hypothesis / mark_contradicts 等）
        │     写: 主题文档直接更新（原地）
        │
        └─ 若 Reflector 判定"足够稳定" → break；否则继续
  │
  └─ KBStore.save(topic_doc) → data/knowledge/hypotheses/<domain>.md
```

## 已知局限

1. **V1 描述与 V4 实现未完全对齐**：本文大量内容仍参考 V1 四角色模型；V4 已合并为两角色（Experimenter + Reflector）。已知局限，下次完整文档升级时重写整体叙事。
2. **max_iterations 硬上限**：若探索未完但 iteration 到上限，Experimenter 无法自动扩展，需手动重启。
3. **loop 不注册到 dashboard**：可观测性弱，后续考虑向 SQLiteBus 发事件。
4. **CoT Faithfulness 未完全消除**：Reflector 仍有机会看到 Experimenter 的工具调用参数（暗含推理痕迹），后续考虑过滤。
5. **依赖 KBStore 路径迁移**：V4 落盘路径从 `data/hypothesis/sessions/` 迁到 `data/knowledge/hypotheses/`，旧 session 数据已废弃。

### doctor.blackboard 扫描已知违规（Phase D · 保留登记）

| Material | 违规类型 | 决定 | 理由 |
|---|---|---|---|
| hypothesis.store | kind.internal 无 producer Worker | **保留** | store 由 AgentNodeLoop 内部落盘，不经 FORMAT_IN/OUT 声明；Diamond shortcut 上层无法感知 |
| hypothesis.store_diff | kind.internal 无 consumer Worker | **保留** | 同上；store_diff 是 Reflector 内部对比产物，在 AgentNodeLoop 内部消费 |
| hypothesis.step_observation | kind.internal 无 producer/consumer | **保留** | AgentNodeLoop 内部工具调用结果，不暴露为 Worker 级 FORMAT |
| hypothesis.reflection_result | kind.internal 无 producer/consumer | **保留** | Reflector 内部决策信号，不暴露为 Worker 级 FORMAT |
| hypothesis.context_substitution | kind.internal 无 producer/consumer | **保留** | Phase C 引入的 KhypSubstitution 机制，AgentNodeLoop 内部处理 |

**根因**：Diamond shortcut 将 AgentNodeLoop 整体包装为单个 Worker，内部 Materials 的生产/消费关系对 doctor 不可见。这是 Diamond 模式的固有局限，Stage 3 真迁移时解决。

## 新哲学对齐（Phase D · 2026-04-20）

### Material 层（F-16/17/18/19）

| 条款 | 状态 | 说明 |
|---|---|---|
| F-16 kind 三分 | ✅ | session=source; factlog/store/store_diff/step_observation/reflection_result/context_substitution=internal; 无 sink（D1：无确定性 exit_format，输出直接落盘到 data/knowledge/hypotheses/）|
| F-17 Workspace 大明文 | ✅ | 假设文档落盘到 data/knowledge/hypotheses/<domain>.md，DB 留指针 |
| F-18 Job × Material 绑定 | N/A | 传统 pipeline，待新 Runtime |
| F-19 kind.* tag 必填 | ✅ | Phase D 修正：7 条 Material 全部补 kind.* |

### Worker 层（R-18~R-25）

| 条款 | 状态 | 说明 |
|---|---|---|
| R-18 粒度 | ✅ | ExperimenterWorker/ReflectorWorker 各有完整职责 + FORMAT 边界 |
| R-19 Agent Worker 升级 | ✅ | ExperimenterRouter/ReflectorRouter 已是 packages.services.agent.AgentNodeLoop (Phase C 迁移) |
| R-20 Agent Worker 三件套 | ✅ | PromptBuilderRouter + ExtractResultRouter + TOOL_ROUTERS (SingleToolRouter 子类) 均已实现 |
| R-21 Diagnosis Agent Worker | N/A | |
| R-22 WorkspaceWriterWorker | N/A | 无独立 WorkspaceWriter；Reflector 直接用 IDE 工具编辑假设文档 |
| R-23 Verdict.output 平铺 | ✅ | ExtractResult 输出无嵌套 format_id |
| R-24 FORMAT_IN_MODE | N/A | 所有 pipeline Worker FORMAT_IN 为单 str |
| R-25 子 job | N/A | 无 _emit_as_new_job |

### Team 层（P-13~P-17）

| 条款 | 状态 | 说明 |
|---|---|---|
| P-13 声明即消费 | ✅ | ExperimenterWorker 消费 hypothesis.store；ReflectorWorker 消费 hypothesis.factlog |
| P-14~17 Workspace 目录 | ✅ 部分 | 落盘路径通过 KBStore → data/knowledge/hypotheses/，不硬编码 cwd (D5) |

**结论**: F-19 缺口已修正。Diamond shortcut 完成（3 Workers）。R-19/R-20 已是新 AgentNodeLoop Phase C 实现，无额外迁移需求。无 sink Material 是有意设计（D1）。

## 参考资料

- 理论：[`docs/plans/[2026-04-15]hypothesis-learning/META_HYPOTHESIS.md`](../../../../../docs/plans/[2026-04-15]hypothesis-learning/META_HYPOTHESIS.md)
- 实现计划：[`docs/plans/[2026-04-15]hypothesis-learning/IMPLEMENTATION_PLAN.md`](../../../../../docs/plans/[2026-04-15]hypothesis-learning/IMPLEMENTATION_PLAN.md)
- 吸收研究：[`docs/plans/[2026-04-15]hypothesis-learning/ABSORPTION.md`](../../../../../docs/plans/[2026-04-15]hypothesis-learning/ABSORPTION.md)
- 同类参考：`packages/domains/voxelcraft/routers/mod_explorer_agent.py`（AgentNodeLoop 用法）
- TMS 理论：Doyle 1979 JTMS / de Kleer 1986 ATMS
