---
name: agent_migration
description: omnicompany 旧 AgentNodeLoop 自动迁移 agent - dogfood 把 runtime.agent.AgentNodeLoop 子类迁到 packages.services._core.agent. 11 P1 子类跑完归档.
user-invocable: false
disable-model-invocation: false
---


# agent_migration · 操作手册

> 设计目的请看 [README.md](README.md). 内部架构请看 [DESIGN.md](DESIGN.md).

## 适用范围

**用我**: 11 个 P1 旧 AgentNodeLoop 子类自动迁移 (dogfood, AI IDE 监督).
**不用我**: 非 agent 类迁移 / 业务逻辑修改 / 11 P1 范围外的 agent (本 service 一次性).

## 前置条件

- omnicompany 已装 + `THE_COMPANY_API_KEY` 配 + bus 必传
- AGENT-NODE-LOOP-ROUTERIZATION plan 阶段 A/B 完成 (新 AgentNodeLoop 接口可用)

## 操作步骤

### 场景 A · 跑单文件迁移 (round 1 用 judge_agent.py 试)

```python
from omnicompany.packages.services._core.agent_migration import LegacyAgnlMigrationAgent
from omnicompany.bus import SQLiteBus

bus = SQLiteBus("data/agent_migration_runs.db")
agent = LegacyAgnlMigrationAgent(bus=bus)
result = agent.run({"task": "迁移 src/omnicompany/packages/services/_core/guardian/judge_agent.py"})
print(result)
```

**验证**: Verdict.output.text 应是 `MIGRATED:` 或 `PARTIAL:` 开头 + 文件路径 + Classes / smoke 状态 + Tools dropped + Notes.

### 场景 B · AI IDE 全程监督 (round 1)

监督点:
- agent 第一步是否 read 模板 / read 旧文件
- write_file 是不是一次写完
- bash 是不是真跑了 smoke
- 第一次 smoke 失败 agent 怎么修

不稳信号 → 升级多 agent 模式.

### 场景 C · 跑完后归档

跑完 11 个 P1 子类 + 全 smoke 通过 → 本 service 归档 (`_archive/agent_migration_2026-05-XX/`), 不留活跃 service.

## 入口清单

| 入口 | 用途 |
|---|---|
| `LegacyAgnlMigrationAgent` (Python) | 库调用迁单文件 |
| dashboard native session | 选 agent_migration 跑 |

(无 omni run 入口 — round 1 阶段 AI IDE 手工监督, dashboard 跑.)

## 故障排查

| 现象 | 修 |
|---|---|
| agent 没 read 模板就 write | 注意力散, 升级多 agent (DESIGN 七节"不稳信号") |
| write 后不 smoke 直接 finish | 跳验证, 同上 |
| 同一文件 write 5+ 次还修不好 | 能力不足, 同上 |
| 跑去改不相关文件 | 注意力散到爆, 同上 |
| smoke 真失败 | 业务逻辑迁错, AI IDE 手工修那一个, 其他继续 agent 跑 |

## 想了解更多

- [README.md](README.md) / [DESIGN.md](DESIGN.md)
- 新 AgentNodeLoop → [../agent/SKILL.md](../agent/SKILL.md)
- 上游 plan → [docs/plans/[2026-04-18]AGENT-NODE-LOOP-ROUTERIZATION/plan.md](../../../../../docs/plans/%5B2026-04-18%5DAGENT-NODE-LOOP-ROUTERIZATION/plan.md)
