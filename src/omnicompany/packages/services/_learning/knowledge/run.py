# [OMNI] origin=claude-code domain=services/knowledge/run.py ts=2026-04-09T00:00:00Z
# [OMNI] material_id="material:learning.knowledge.pipeline_registry.run.py"
"""omnikb.run — 管线入口, 被 core/pipelines.py 通过 _lazy 引用。

Router 和 pipeline 的 import 都延迟到调用时, 避免 CLI 启动时拉重依赖。
"""

from __future__ import annotations

from typing import Any

from omnicompany.runtime.routing.router import Router


def build_audit_pipeline():
    """返回 omnikb-audit 的 TeamSpec。"""
    from omnicompany.packages.services._learning.knowledge.pipeline import build_audit_pipeline as _build
    return _build()


def build_audit_bindings(
    input_dict: dict[str, Any] | None = None,
) -> dict[str, Router]:
    """omnikb-audit 的 Router bindings。"""
    from omnicompany.packages.services._learning.knowledge.routers import KBAuditRouter

    return {
        "audit_all": KBAuditRouter(),
    }
