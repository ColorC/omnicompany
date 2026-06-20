<!-- [OMNI] origin=claude-code domain=services/workflow_factory ts=2026-05-04T13:30:00Z type=doc status=deprecated belongs_to_service=workflow_factory -->
<!-- [OMNI] material_id="material:core.workflow_factory.shim_deprecation.design_document.md" -->

# workflow_factory · 设计文档 (deprecated shim)

> ⚠ 设计目的请看 [README.md](README.md) (deprecation 背景 + 删除条件). 怎么用请看 [SKILL.md](SKILL.md) (其实是"别用我, 用 team_builder").
>
> **本 service 是 import 路径 shim, 非活跃 service**. 真实逻辑已迁到 [team_builder](../team_builder/DESIGN.md).

## 状态

- **版本**: V1 shim (2026-04-23 A3 改名)
- **成熟度**: deprecated
- **下一步**: Track B3 命名迁移完成时整体删除. 在此之前仅作 import alias 保留老代码可用.

## 核心接口

```python
# 老代码仍可这样 import (本 shim 代劳 alias)
from omnicompany.packages.services.workflow_factory.formats import XxxMaterial
from omnicompany.packages.services.workflow_factory.workers import YyyWorker
```

内部实现: `__init__.py` 预加载 `team_builder` 的子模块并注册到 `sys.modules` 的 `workflow_factory.*` 命名空间.

**被透传的子模块**: `formats`, `routers`, `routers_codegen`, `team`, `pipeline`, `run`, `workers` (见 `__init__.py` `_SUBMODULES`).

## 架构决策

### D1 · 保留 shim 不硬改

**决策**: 改名 `workflow_factory → team_builder` 时**保留** `workflow_factory/` 作 shim, 不一次性硬改所有 import.

**理由**: (2026-04-23 用户) Diamond 归档作参考, 新工作从 team_builder agent-first 开始. 一次性硬改老 import 风险大, shim 让过渡期可控, 命名迁移 (Track B3) 按节奏逐步清理.

### D2 · shim 零业务逻辑

**决策**: 本目录**不允许**任何业务代码 — 只有 `__init__.py` 一个文件做 import alias.

**理由**: 保持 shim 纯粹. 任何有业务逻辑的修改都应该去 `team_builder`. 防止 shim 变成第二个活跃 service 导致双维护.

## 数据流 / 拓扑

无独立数据流. 本 shim 转发所有请求到 team_builder:

```
import workflow_factory.foo      # ← 老代码
         │
         ▼ (sys.modules alias)
import team_builder.foo          # ← 真实位置
```

## 已知局限

| 局限 | 说明 |
|---|---|
| 过渡期双名冲突 | 偶尔有代码同时 import 两个路径, 会拿到同一模块对象 (alias 机制保证); 静态分析工具可能困惑 |
| 没有独立测试 | 本 shim 不单独测, 依赖 team_builder 测试覆盖 |
| 删除时机未定 | Track B3 迁移完成条件: 全仓 grep `workflow_factory` 只剩本 shim 自身和归档引用 |

## 参考资料

- 真实 service: [`../team_builder/DESIGN.md`](../team_builder/DESIGN.md)
- 改名背景: 2026-04-23 A3 会话 (用户明示 "Diamond 归档作参考, 新工作从 team_builder 开始")
- 命名迁移总表: [`docs/standards/terminology.md`](../../../../../../docs/standards/_global/terminology.md) (Track B3)
- 归档代码: `src/omnicompany/packages/services/team_builder/_archive/` (内有 workflow_factory 原 Diamond 实现)
