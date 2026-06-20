# 治理部门 (_governance)

用性价比模型(默认 deepseek-v4-pro)做仓库治理的常态化部门。2026-06-12 由用户设立：
分类/汉化/历史整理这类大批量判断**不该烧主力模型的 token**。

## 成员与职责

### plan_steward — 计划治理
- 给 docs/plans 全量计划逐个判定：**归属项目**（写显式覆盖表，物理位置不动）、
  **中文标题**（title_zh，/api/plans 与项目页浮出）、**格式检查**（缺 plan.md 等）。
- 产物：`data/registry/plan_governance.json`（唯一权威覆盖表）+ `data/governance/plan_steward/report-*.md`
- 消费方：`core/projects_registry.resolve_project_plans`（覆盖优先，未治理退回类目前缀规则）。
- 教训（设立当天）：项目注册表里手写的"精确计划 id"类目会反过来污染模型判断——
  hint 只许给结构性目录前缀；归属判据 = 内容，"与项目主题相关"≠"是该项目的工作"。

### work_history — 工作历史整理（原进化部门重组）
- 进化部门(evolution_v1)已入 `_graveyard`；本部门继承其"学习-改进"使命，当前工作中心：
  用便宜模型 review 用户的 claude code / codex **对话历史**（只抽用户亲手发的消息，
  剥系统注入）+ 两边 memory，整理出**重复需求**与**重复指正**。
- 产物：`data/governance/work_history/findings-*.json` + `report-*.md` + `latest.json` 指针。
- 重复需求是 PROJECT_INDEX `quick_actions` 的**唯一合法证据来源**——AI 不得凭感觉
  捏造"常用工作选项"（2026-06-12 用户抓包的事故）。

## 用法

```bash
omni governance plans-run            # 全量计划治理(增量补登记用 --only-missing)
omni governance plans-status         # 覆盖表摘要
omni governance history-run          # 历史挖掘(默认近 45 天)
omni governance history-report       # 最近一次报告
omni governance actions-check        # quick_actions 的 skill 存在性体检(不调模型)
```

新计划出现后跑 `plans-run --only-missing` 补登记；归属争议看报告的"位置与归属不一致"节。

## 质量控制 — benchmark 金标签（2026-06-12 用户立规）

> "不要过分相信（便宜模型），建立 benchmark 机制，你亲自操作的结果其实是要更准确的
> （只要你真的去看了）。"

- 便宜模型的产出**不免检**。主力模型/人**亲自读过计划内容**后的判定写进
  `data/governance/plan_steward/benchmark.json` 的 `labels`（金标签）。
- 金标签权威高于便宜模型：`plans-run` 合并时强制覆盖（模型原判留在 `model_project`），
  重跑不回退。
- `omni governance plans-benchmark` 随时算一致率；一致率明显下滑 = 提示词或批次出了问题。
- 抽样原则：每项目至少 1 个 + 无归属若干 + 全部低置信/位置不一致项；抽到必须真读内容，
  不许只看目录名。
- work_history 同理：findings 里的引语在用于 quick_actions 前要回 grep 原始会话验真。

## Structured JSON LLM

Governance does not own a private JSON LLM helper. Single-call structured JSON
requests consume `omnicompany.runtime.llm.structured.call_json`.

- Default structured model slot: `OMNI_STRUCTURED_LLM_MODEL`, fallback
  `deepseek-v4-pro`.
- History assignment slot: `OMNI_STRUCTURED_ASSIGN_MODEL`, fallback `glm-5.1`.
