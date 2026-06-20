# [OMNI] origin=claude-code domain=services/workflow_factory ts=2026-04-23T00:00:00Z type=shim
# [OMNI] material_id="material:core.workflow_factory.import_shim.compatibility_layer.py"
"""workflow_factory · 已改名为 team_builder (2026-04-23 A3).

本目录仅作 **import 路径 shim**, 通过 sys.modules alias 让老 import 路径继续可用.
新代码**请直接** import `omnicompany.packages.services.team_builder`.

原因 (用户 2026-04-23):
  - Diamond 归档作参考, 新工作从 team_builder agent-first 开始
  - 保留本 shim 让老代码 `from workflow_factory.xxx import ...` 仍能 import (过渡期)

后续清理计划: Track B3 命名迁移里一并删除.
"""
from __future__ import annotations

import importlib
import sys

# 预加载 team_builder 及所有子模块, 注册 sys.modules alias.
_SUBMODULES = (
    "formats",
    "team",
    "pipeline",
    "run",
    "routers",
    "routers_codegen",
    "workers",
    "knowledge",
    "_archive",
)

_tb = importlib.import_module("omnicompany.packages.services.team_builder")
# 顶层 alias
sys.modules[__name__] = _tb  # 让 `import workflow_factory` 返回 team_builder 本体

# 子模块 alias (按需加载, 失败不报错 — 让真正使用时报更明确的错)
for _sub in _SUBMODULES:
    try:
        _mod = importlib.import_module(f"omnicompany.packages.services._core.team_builder.{_sub}")
        sys.modules[f"{__name__}.{_sub}"] = _mod
    except ImportError:
        pass
