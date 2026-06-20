<!-- [OMNI] origin=ai-ide domain=services/workflow_factory ts=2026-05-04T13:30:00Z type=doc status=deprecated agent=ai-ide belongs_to_service=workflow_factory -->
<!-- [OMNI] summary="workflow_factory service 自我叙事 README — DEPRECATED shim, 真实逻辑已迁到 team_builder. 仅保过渡期 import 路径兼容, Track B3 命名迁移完成时整体删" -->
<!-- [OMNI] why="按 self_narrative_three_files.md §四 模板严格写. 验证 deprecated service 三件套形态 — README 警示+指向真实位置, 不写新功能远景" -->
<!-- [OMNI] tags=readme,workflow_factory,deprecated,shim,self-narrative -->
<!-- [OMNI] material_id="material:services._core.workflow_factory.readme.deprecation_notice.md"-->

# workflow_factory · DEPRECATED Import Path Shim

> ⚠ **本 service 已 deprecated, 是 import 路径 shim, 非活跃 service**. 真实业务逻辑已迁到 [team_builder](../team_builder/). 老代码 `from omnicompany.packages.services.workflow_factory.xxx import ...` 仍可用 (本 shim 代劳 alias), 新代码请直接 import team_builder.

---

## 这是什么

workflow_factory 是 omnicompany 的**过渡期 import 路径兼容 shim**. 它**不含任何业务逻辑** — `__init__.py` 通过 `sys.modules` alias 把子模块指向 [`team_builder`](../team_builder/).

历史背景: 2026-04-23 用户拍板把 workflow_factory 改名为 team_builder ("新工作从 team_builder agent-first 开始, 旧 Diamond 实现归档作参考"). 一次性硬改所有老 import 风险大, 留 shim 让过渡期可控. Track B3 命名迁移完成时本 shim 整体删除.

## 解决什么 / 不解决什么

**解决**:
- 老代码 `from omnicompany.packages.services.workflow_factory.<sub>` import 不破

**不解决**:
- 任何新功能需求 — 全归 [team_builder](../team_builder/)
- 新代码不应该用 workflow_factory 路径 (用了也能跑, 但建议直接 import team_builder)

## 设计目的与最终目标

**设计目的**: 命名迁移期老代码不破. 仅此一件.

**最终目标** (当下能认知的): **整体删除**. Track B3 ([terminology.md](../../../../../../docs/standards/_global/terminology.md)) 命名迁移完成 (全仓 grep `workflow_factory` 只剩本 shim 自身和归档引用) → 本 shim 删.

无"远景扩展" — 这是 deprecated service, 不增不改, 只等删.

## 规划

- **当前**: V1 shim (2026-04-23 A3 改名), 仅作 import alias
- **下一步**: 等 Track B3 命名迁移完成
- **远景**: 删除

## 构成

只有一个文件: [`__init__.py`](__init__.py) — 用 `sys.modules` alias 把 7 个子模块 (`formats` / `routers` / `routers_codegen` / `team` / `pipeline` / `run` / `workers`) 指向 team_builder 同名子模块.

无独立 Material / Worker / Team / 测试. 全部依赖 team_builder.

## 想了解更多

- 真实 service → [team_builder/README.md](../team_builder/README.md) (待建) / [team_builder/DESIGN.md](../team_builder/DESIGN.md)
- 改名背景 → 2026-04-23 A3 用户会话 (Diamond 归档作参考, 新工作从 team_builder 开始)
- 命名迁移总表 → [docs/standards/terminology.md](../../../../../../docs/standards/_global/terminology.md) (Track B3)
- 归档代码 → [team_builder/_archive/](../team_builder/_archive/) (workflow_factory 原 Diamond 实现归档在那)
