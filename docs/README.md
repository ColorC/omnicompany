# docs/ 总索引

> 规范权威：[`standards/distributed-docs.md`](standards/distributed-docs.md) — 所有放置/拆分/归档决策以此为准。
> 新增目录/顶层文件时必须在本文件增加一行索引。

## 顶层文件

- [PROGRESS.md](PROGRESS.md) — **全局进度唯一权威**（当前阶段 / 最新状态 / 下一步）— owner: L2
- [控制结构.md](控制结构.md) — **L2 行为唯一权威**（五层角色 / 派发规则 / 铁律 / 报告格式）— owner: L2
- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构全景（人读）— owner: architect
- [archmap.yaml](archmap.yaml) — 架构全景（机器读）— owner: Guardian
- [SDK_CONTRACT.md](SDK_CONTRACT.md) — 对外 SDK 合约 — owner: core
- [taxonomy.yaml](taxonomy.yaml) — 机器可读词汇表 — owner: Guardian
- [overseer_backlog.md](overseer_backlog.md) — L2 顶班待办 — owner: L2
- [ARCH-CHANGES.jsonl](ARCH-CHANGES.jsonl) — 架构变更日志（append-only） — owner: Guardian

## 一级目录

- [standards/](standards/) — **框架级规则/标准**（强制规范，必要不充分）— owner: architect / L2
- [theory/](theory/) — **跨包理论/愿景**（长期参考，季度复审）— owner: architect
- [reports/](reports/) — **历史回顾报告**（写定即 frozen；含 `progress/` 月度存档）— append-only
- [gaps/](gaps/) — **系统能力缺口清单**（G# 条目，补足即 resolved）— owner: architect
- [plans/](plans/) — **一次性过程记录**（`[YYYY-MM-DD]TOPIC/` 目录，完成归档到 `_archive/`）— author: 作者签
- [tech_debt/](tech_debt/) — **技术债统一登记处**（`REGISTRY.md`，外部 agent 可直接 append，人可直接读）— owner: L2 / Guardian
- [_archive/](_archive/) — 跨类别归档根（`legacy/` 纯历史留存）

## standards/ 子项

- [distributed-docs.md](standards/distributed-docs.md) — 本规范体系的权威
- [code.md](standards/code.md) · [format.md](standards/material.md) · [router.md](standards/worker.md) · [pipeline.md](standards/team.md) — 节点健康标准
- [omni-header.md](standards/omni-header.md) — OmniMark 文件头
- [design_md_template.md](standards/design_md_template.md) — DESIGN.md 七节模板
- [agent_tools.md](standards/agent_tools.md) — Agent Node Loop 工具接口
- [llm_first.md](standards/llm_first.md) — LLM 优先与语境完整性
- [information_sufficiency.md](standards/information_sufficiency.md) — 信息充分性保障
- [standards/_domain_specific/dashboard/team-observability-ui.md](standards/_domain_specific/dashboard/team-observability-ui.md) — Dashboard Team/Material/归因图的人读界面规范

## theory/ 子项

- [大迁移路线图.md](theory/大迁移路线图.md)
- [pain_as_semantic_structure.md](theory/pain_as_semantic_structure.md)
- [用户语义信号需求.md](theory/用户语义信号需求.md)
- [验收与进化路线图.md](theory/验收与进化路线图.md)
- [testing_methodology.md](theory/testing_methodology.md)
- [六元语义/](theory/六元语义/) — 六元语义信号模型 / 接口规范 V1.0 / V1.1 实践桥接

## plans/ 说明

活跃 plans（≥2026-04-10）按 `[YYYY-MM-DD]TOPIC/` 组织；已归档见 [`plans/_archive/`](plans/_archive/)。归档前必须把核心决策回流到对应 `DESIGN.md`，回流看板：[`plans/_archive/_PENDING_DESIGN_MERGE.md`](plans/_archive/_PENDING_DESIGN_MERGE.md)。

## 就近文档（不在 docs/ 内）

- 包/服务设计：`src/omnicompany/**/<pkg>/DESIGN.md`
- 包清单：`src/omnicompany/**/<pkg>/.omni/manifest.yaml`
- Format/Router 定义：`src/.../knowledge/formats|routers/**/*.md`

完整放置规则见 [standards/distributed-docs.md §四](standards/distributed-docs.md)。
