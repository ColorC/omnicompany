# [OMNI] origin=claude-code domain=services/runtime_test_builder/__init__ ts=2026-04-27T00:00:00Z type=config
# [OMNI] material_id="material:utility.runtime_test.builder.package_exports.config.py"
"""runtime_test_builder · 真 meta 层 v2 测试团队构建器 (针对 target 当场生成假设)."""
from __future__ import annotations

from .team import build_team
from .run import build_bindings

__all__ = ["build_team", "build_bindings"]
