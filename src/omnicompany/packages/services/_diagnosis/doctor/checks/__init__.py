# [OMNI] origin=claude-code domain=services/doctor/checks ts=2026-04-19T00:00:00Z
# [OMNI] material_id="material:diagnosis.doctor.checks.package.exports.py"
"""doctor/checks — 可复用的静态分析 checker 集合。

这些 check 是**纯函数**, 不依赖 pipeline / runner。既可以被 doctor 管线
里的 Router 调用（与 Verdict / EventBus 集成）, 也可以被 workflow_factory
LAPVerifier 等独立 Router 直接调用, 避免两处漂移。
"""
from __future__ import annotations

from omnicompany.packages.services._diagnosis.doctor.checks.format_in_consumption import (
    check_format_in_consumption,
)

__all__ = ["check_format_in_consumption"]
