
# repo_learner · 设计文档

## 状态
- **版本**: V1 (Phase D 2026-04-20 补全)
- **成熟度**: active
- **下一步**: 待新 AgentNodeLoop Runtime 成熟后，规划 R-19/R-20 Agent Worker 三件套迁移

## 核心目的
从外部开源仓库中自主学习，产出带文件位置证据的学习报告。

三节点 pipeline (LearnDimensionsLoader → MainLearnerAgent → 落盘):
- **LearnDimensionsLoader**: 确定性注入 19 条 AI 项目观察维度 (非 OmniCompany 自画像)
- **MainLearnerAgent**: 自由读外部仓库 + 维护 ledger + 可 spawn 最多 3 个子 agent
- **ModuleReaderAgent**: 子 agent, 深读单个模块 + 返回结构化 findings

复用 repo_architect 上游节点: input_validator / repo_acquirer / repo_identity_anchor / scale_surveyor。

## 核心接口
<!-- TBD: 此节尚未填充 — 需要补：对外暴露的关键类/函数/协议（含源码链接） -->

## 架构决策
<!-- TBD: 此节尚未填充 — 需要补：至少 5 条 ### D1-DN 决策（状态 skeleton 可暂空） -->

## 数据流 / 拓扑
<!-- TBD: 此节尚未填充 — 需要补：输入→处理→输出，或关键组件协作图 -->

## 已知局限

1. **旧 AgentNodeLoop 基类** — `MainLearnerAgent` / `ModuleReaderAgent` 继承自 `runtime/agent/agent_node_loop.py` (DEPRECATED, 阶段 D 计划删除)。R-19/R-20 的 Agent Worker 三件套 (Context/LLM/Tool Script + 迷你 stock) 未实现。**升级路径**: 待新 `packages/services/agent/` Runtime 成熟后独立计划迁移; Phase D 暂 grandfathered。

2. **ToolDefinition 使用** — 内部 `ledger_record / ledger_list / spawn_module_reader / finalize_report` 工具以 `ToolDefinition` 构造 (DEPRECATED)。**升级路径**: 同上, 随 AgentNodeLoop 迁移一并替换为 SingleToolRouter 子类。

3. **learner_tools 闭包耦合** — `_make_learner_tools()` 通过 Python 闭包捕获 `main_agent` 实例, 无法用 MaterialDispatcher 独立激活。**升级路径**: R-20 三件套重构时自然解决。

4. **落盘路径硬编码 "absorption"** — `resolve_domain_data_dir("absorption")` 把学习报告写入 absorption 子域。**升级路径**: 依赖 repo_architect domain 迁入 repo_learner 或自有 data 域时修正。

## 新哲学对齐（Phase D · 2026-04-20）

> 对照 13 条新世界条款逐项评估（完整权威见 docs/standards/material.md + worker.md + team.md）。

### Material 层（F-16/17/18/19）

| 条款 | 状态 | 说明 |
|---|---|---|
| F-16 kind 三分 | ✅ | learn-dimensions=internal (LearnDimensionsLoaderRouter → MainLearnerAgent); learning-report=sink (最终产出, 无 consumer) |
| F-17 Workspace 大明文 | ✅ | learning-report Material 存路径指针; 报告正文通过 write_file() 落盘 — 符合 F-17 大 payload 走文件模式 |
| F-18 Job × Material 绑定 | N/A | 当前走传统 AgentNodeLoop pipeline 模式, MaterialDispatcher job_id 链路待新 Runtime 接通 |
| F-19 kind.* tag 必填 | ✅ | Phase D 修正：2 条 Material 全部补 kind.* (本次 commit) |

### Worker 层（R-18~R-25）

| 条款 | 状态 | 说明 |
|---|---|---|
| R-18 粒度 | ✅ | LearnDimensionsLoaderRouter (确定性注入) / MainLearnerAgent (主学习) / ModuleReaderAgent (子学习) 各有完整职责 + FORMAT 边界 |
| R-19 Agent Worker 升级 | ⚠️ grandfathered | MainLearnerAgent 有动态 spawn 需求，应升级 Agent Worker 三件套；待新 Runtime 计划独立迁移 |
| R-20 Agent Worker 三件套 | ⚠️ grandfathered | 同上；当前单体 AgentNodeLoop 继承非三件套结构 |
| R-21 Diagnosis Agent Worker | N/A | repo_learner 是学习 agent，不需对自身上游质疑 |
| R-22 WorkspaceWriterWorker | N/A | 报告落盘是最终输出而非中间 workspace 文件，write_file() 封装足够 |
| R-23 Verdict.output 平铺 | ✅ | LearnDimensionsLoaderRouter / MainLearnerAgent / ModuleReaderAgent 输出均无嵌套 format_id |
| R-24 FORMAT_IN_MODE | N/A | 所有节点 FORMAT_IN 均为单 str，无 list 多入 |
| R-25 子 job | N/A | 无 _emit_as_new_job 使用 |

### Team 层（P-13~P-17）

| 条款 | 状态 | 说明 |
|---|---|---|
| P-13 声明即消费 | ✅ | 各节点只消费 FORMAT_IN 声明的 Material，无搭便车 |
| P-14~17 Workspace 目录 | N/A | 无 workspace 目录约定 |

**结论**: 唯一 F-19 缺口已修正。R-19/R-20 旧 AgentNodeLoop 体系为 grandfathered 遗留，登记为已知局限，独立计划处理。

## 参考资料

- [formats.py](formats.py) — 2 个 Material 定义
- [routers.py](routers.py) — LearnDimensionsLoaderRouter + MainLearnerAgent + ModuleReaderAgent
- [pipeline.py](pipeline.py) — 管线装配
- [../repo_architect/DESIGN.md](../../../../../../../data/_workspaces/team_builder/repo_abs_140156/src/omnicompany/packages/services/repo_architect/DESIGN.md) — 上游共享节点 (input_validator / repo_acquirer 等)
