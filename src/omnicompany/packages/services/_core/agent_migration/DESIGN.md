---
title: agent_migration
date: 2026-05-04
project: agent-framework
work_type: dogfood-agent
standards:
  - feedback_batch_work_use_omnicompany_agent
  - feedback_high_autonomy_with_guardrails
  - Agent_Node_Loop_Router化铁律
status: active
phase: round-1
exit_criteria:
  - 跑 1 个 P1 子类 (judge_agent.py) 真迁完, smoke 测过, 0 回归
  - 表现观察: 稳/不稳决定后续 (用户 5-2 立: 不稳就升级多 agent)
  - 跑完 11 个 P1 子类 (含 LLMJudgeAgent 已手干 baseline) 全 smoke 通过
---


# agent_migration · 服务设计

> 设计目的请看 [README.md](README.md). 怎么用请看 [SKILL.md](SKILL.md). 本文档专管**架构内部**.
>
> 注: 本 DESIGN 用**非标结构** (YAML frontmatter + 中文数字节"## 一/二/三/四/五/六/七"), 是该 service 自选. 不强改回标准七节.

## 一、服务概要

单 agent (LegacyAgnlMigrationAgent) dogfood 自动迁移旧 `runtime.agent.agent_node_loop.AgentNodeLoop`
继承的子类到新 `packages.services._core.agent.AgentNodeLoop` (router 化基础设施).

跟 batch_work_use_omnicompany_agent memory 对齐: N>10 套路相同的机械工作用 omnicompany agent
跑, 不 AI IDE 手干. 当前 11 个 P1 子类 (扣已迁的 LLMJudgeAgent) = 10 个待迁, 估 5-15 小时 AI IDE 手工,
agent 跑预计 1-2 小时 (每个 5-15 min agent + AI IDE 监督).

## 二、输入输出

**输入** (run 调用):
```python
agent.run({"task": "迁移 src/omnicompany/packages/services/_core/guardian/judge_agent.py"})
```

**输出** (Verdict.output.text — 来自 finish 工具的 result):
```
MIGRATED: src/omnicompany/.../judge_agent.py
Classes:
  - GuardianAgent: smoke OK
Tools dropped: ["think"]
Notes: ...
```

或失败:
```
PARTIAL: src/omnicompany/.../judge_agent.py
Classes:
  - GuardianAgent: FAILED smoke after 3 attempts. Last error: ImportError: ...
Tools dropped: [...]
```

## 三、接口

- 公开类: `LegacyAgnlMigrationAgent` (ConfigurableAgent 子类)
- 工具集: read_file / grep / write_file / bash + finish (自动加)
- prompt material: migration_prompt.md (人类可读, 跟 dashboard/native_agent_prompt.md 同形态)
- bus: 必传 (新 AgentNodeLoop 强校验)
- cwd: 默认 os.getcwd(), 实例可覆盖

## 四、依赖

- `packages.services._core.agent.ConfigurableAgent` (基类)
- `packages.services._core.agent.routers.{ReadFile, Grep, WriteFile, DevBash, Finish}Router` (工具)
- `runtime.agent.agent_loop_config.{LoopConfig, CompactConfig, RetryConfig, PermissionConfig}` (配置, 仍有效未 deprecate)
- `runtime.llm.llm.ModelRegistry` (经 `role="ide_agent"` 拿 qwen3.6-max-preview)

## 五、配置

- `llm_max_turns=50` (单文件迁移够: read ~3 次 + write 1 次 + bash 1-3 次 + finish)
- `llm_temperature=0.2` (机械迁移要稳, 不要 LLM 加戏)
- `llm_max_tokens=8000` (一次 write_file 写整个新文件, 大输出)
- `permission.mode="default"` (write_file / bash 需用户 approval, 但 dashboard 跑时是 dangerously-skip-permissions)

## 六、测试

**Round 1 (本次)**: dogfood judge_agent.py (299 行, GuardianAgent 单 class) 看 agent 实际行为.

观察点:
- 工具调用是否合理 (先 read 模板再 write, 不绕圈)
- write_file 一次写完还是多次 patch (一次写完更稳)
- bash smoke 真跑了还是跳过
- 错误处理: 第一次 smoke 失败, agent 怎么修

不稳信号 → 升级多 agent:
- agent 没 read 模板就 write (注意力散)
- write 后不 smoke 直接 finish (跳验证)
- 同一文件 write 5+ 次还修不好 (能力不足)
- 跑去改不相关文件 (注意力散到爆)

## 七、运维

- 调用方: AI IDE 手工调 / dashboard native session 选这个 agent
- 监督: AI IDE round 1 全程监督, round 2+ 看具体 P1 子类难度决定监督强度
- 失败回退: 单文件失败不阻塞, AI IDE 手干那一个, 其他继续 agent 跑
- 跑完 11 个 P1 后, 这个 service 可以归档 (一次性工作)
