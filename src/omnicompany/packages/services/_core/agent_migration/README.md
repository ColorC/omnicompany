<!-- [OMNI] origin=ai-ide domain=services/agent_migration ts=2026-05-04T16:05:00Z type=doc status=active agent=ai-ide belongs_to_service=agent_migration -->
<!-- [OMNI] summary="agent_migration service 自我叙事 README — 单 agent dogfood 自动迁旧 runtime.agent.AgentNodeLoop 子类到新 packages.services._core.agent. 一次性工作, 11 P1 子类跑完归档" -->
<!-- [OMNI] why="按 self_narrative_three_files.md §四 模板严格写. 注意: DESIGN 用非标 YAML frontmatter + 中文数字节, 不强改" -->
<!-- [OMNI] tags=readme,agent_migration,core,dogfood,self-narrative,one-shot -->
<!-- [OMNI] material_id="material:services._core.agent_migration.readme.self_narrative.md"-->

# agent_migration · 旧 AgentNodeLoop 自动迁移

> 单 agent (`LegacyAgnlMigrationAgent`) **dogfood 自动迁** 旧 `runtime.agent.AgentNodeLoop` 子类 → 新 `packages.services._core.agent.AgentNodeLoop`. 11 个 P1 子类跑完后**本 service 归档** (一次性工作).

## 这是什么

agent_migration 是 omnicompany 的**一次性迁移 agent service**. 跟 [batch_work_use_omnicompany_agent](../../../../) memory 对齐: N>10 套路相同的机械工作用 omnicompany agent 跑, 不 AI IDE 手干.

形态: 单 agent (LegacyAgnlMigrationAgent), ConfigurableAgent 子类, 工具池 5 个 (read_file / grep / write_file / bash / finish).

## 解决什么 / 不解决什么

**解决**: 11 个 P1 子类 (扣已迁的 LLMJudgeAgent) 自动迁 → 估 5-15 小时手工降到 1-2 小时 agent + AI IDE 监督.

**不解决**: 旧 AgentNodeLoop 子类内业务逻辑 (只迁框架, 业务保留); 非 agent 类代码迁移; 11 个 P1 之外的 agent 迁移 (一次性范围).

## 设计目的与最终目标

**设计目的**: AGENT-NODE-LOOP-ROUTERIZATION plan 阶段 C 要把 13 个旧 AgentNodeLoop 子类迁到新接口. 手工干工作量大且机械. 让 omnicompany 自己的 agent 干这事.

**最终目标**: 跑完 11 个 P1 子类全 smoke 通过 → 本 service 归档 (一次性 service, 无远景).

观察点 (round 1 全程监督): 工具调用合理性 / write 一次写完 vs 多次 patch / smoke 真跑 / 错误处理.

不稳信号 → 升级多 agent: agent 没 read 模板就 write / write 后不 smoke / 同一文件 write 5+ 次仍修不好.

## 规划

- **当前 active, round 1** (2026-05-02): dogfood judge_agent.py (299 行 / GuardianAgent 单 class) 看实际行为
- **下一步**: round 2+ 跑 11 个 P1 子类, 监督强度按难度调
- **远景**: 跑完 11 个 P1 后归档 (本 service 一次性, 无后续)

## 构成

- agent 类: `LegacyAgnlMigrationAgent` (`ConfigurableAgent` 子类)
- 工具池: read_file / grep / write_file / bash + finish (自动加)
- prompt material: `migration_prompt.md` (人类可读, 跟 dashboard/native_agent_prompt.md 同形态)
- bus: 必传 (新 AgentNodeLoop 强校验)
- LLM 配置: `llm_max_turns=50` / `llm_temperature=0.2` / `llm_max_tokens=8000`

## 想了解更多

- [DESIGN.md](DESIGN.md) (非标结构 YAML frontmatter + 中文数字节, 是该 service 自选)
- [SKILL.md](SKILL.md)
- 上游 plan AGENT-NODE-LOOP-ROUTERIZATION → [docs/plans/[2026-04-18]AGENT-NODE-LOOP-ROUTERIZATION/plan.md](../../../../../docs/plans/%5B2026-04-18%5DAGENT-NODE-LOOP-ROUTERIZATION/plan.md)
- 新 AgentNodeLoop → [../agent/README.md](../agent/README.md)
- 旧 runtime/agent → [../../../runtime/agent/](../../../../runtime/agent/)
- batch_work_use_omnicompany_agent memory → MEMORY.md 对应条
