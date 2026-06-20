# [OMNI] origin=claude-code domain=services/absorption_runtime_test/__init__ ts=2026-04-27T00:00:00Z type=config
# [OMNI] material_id="material:utility.runtime_test.absorption.package_exports.config.py"
"""absorption_runtime_test Team · absorption 类工作的特化测试团队 · 真跑 + 3 路多源验证 + 画像."""
from __future__ import annotations

from .team import build_team
from .run import build_bindings

__all__ = ["build_team", "build_bindings"]
