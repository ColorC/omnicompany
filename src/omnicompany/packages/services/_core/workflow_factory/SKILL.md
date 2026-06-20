---
name: workflow_factory
description: DEPRECATED shim. 真实逻辑在 team_builder, 这里只是 import 路径兼容 alias. 老代码 import 仍可用, 新代码用 team_builder.
user-invocable: false
disable-model-invocation: false
---

<!-- [OMNI] origin=ai-ide domain=services/workflow_factory ts=2026-05-04T13:35:00Z type=doc status=deprecated agent=ai-ide belongs_to_service=workflow_factory -->
<!-- [OMNI] summary="workflow_factory 操作手册 — 实际是'别用我, 用 team_builder' 的 deprecated 提示" -->
<!-- [OMNI] why="按 self_narrative_three_files.md §六 模板严格写. 验证 deprecated service 的 SKILL 形态 (大部分内容是'别用'+'去哪')" -->
<!-- [OMNI] tags=skill,workflow_factory,deprecated,shim -->
<!-- [OMNI] material_id="material:services._core.workflow_factory.skill.deprecation_redirect.md"-->

# workflow_factory · 操作手册 (deprecated)

> ⚠ 设计目的请看 [README.md](README.md). 内部架构请看 [DESIGN.md](DESIGN.md).
>
> **本 service 已 deprecated. 真实在 [team_builder](../team_builder/), 用那个**.

---

## 适用范围

**用我** (仅过渡期):
- 你有老代码用 `from omnicompany.packages.services.workflow_factory.<sub> import ...` 还没迁过来
- 暂时不能改 import 路径

**不用我**:
- 新代码 — 直接 `from omnicompany.packages.services.team_builder.<sub> import ...`
- 任何新功能 — 都加在 team_builder, 不要加在这里
- 任何业务逻辑 — 这 shim 只有 1 个 `__init__.py`, 不允许任何业务代码

## 前置条件

无.

## 操作步骤

### 场景 A · 我有老代码 import 了 workflow_factory, 怎么办

**短期 (过渡期 OK)**: 不改, 让 shim 代劳. 例如:

```python
from omnicompany.packages.services.workflow_factory.formats import XxxMaterial   # ✓ 仍可用
from omnicompany.packages.services.workflow_factory.workers import YyyWorker     # ✓ 仍可用
```

**长期 (推荐迁移)**: 改成 team_builder 路径:

```python
from omnicompany.packages.services.team_builder.formats import XxxMaterial       # ✓ 新代码
from omnicompany.packages.services.team_builder.workers import YyyWorker         # ✓ 新代码
```

### 场景 B · 我想给 workflow_factory 加个新 Worker / 改 logic

**别加**. 去 team_builder. 本 shim 不允许业务代码 (D2 决策).

### 场景 C · 我想知道 workflow_factory 什么时候删

看 [docs/standards/terminology.md](../../../../../../docs/standards/_global/terminology.md) Track B3 进度. 全仓 grep `workflow_factory` 只剩本 shim 自身和归档引用 → 本 shim 整体删除.

## 入口清单

| 入口 | 用途 | 备注 |
|---|---|---|
| `from omnicompany.packages.services.workflow_factory.<sub>` | 过渡期 import 兼容 | 7 个子模块 (formats/routers/routers_codegen/team/pipeline/run/workers) 全可用 |
| (无 CLI 命令) | — | shim 不暴露 CLI, 真实功能在 [team_builder SKILL](../team_builder/SKILL.md) (待建) |

## 故障排查

| 现象 | 可能原因 | 怎么修 |
|---|---|---|
| `import workflow_factory.xxx` 报 ModuleNotFoundError | sys.modules alias 失败 (理论不应该) | 看 `__init__.py` 是否被改; 直接用 team_builder 路径绕过 |
| 静态分析工具警告 workflow_factory 同时也是 team_builder | alias 机制让两路径指向同一对象, 工具可能困惑 | 改用 team_builder 路径让工具识别 |
| 我加了 workflow_factory 内代码改动但跑不到 | shim 不允许业务代码, 子模块全转发到 team_builder, 你的改动如果在 workflow_factory 子模块里被忽略 | 把改动挪到 team_builder 对应位置 |

## 想了解更多

- 真实 service → [team_builder/](../team_builder/) (DESIGN.md / SKILL.md 待建)
- deprecation 背景 → [README.md](README.md)
- 命名迁移 → [docs/standards/terminology.md](../../../../../../docs/standards/_global/terminology.md) Track B3
