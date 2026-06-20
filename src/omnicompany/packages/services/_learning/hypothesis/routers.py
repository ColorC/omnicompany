# [OMNI] origin=claude-code domain=services/hypothesis ts=2026-04-20T00:00:00Z type=config
# [OMNI] material_id="material:services.learning.hypothesis.router.compatibility_shim.py"
"""hypothesis routers — 兼容垫片 (Phase D Diamond shortcut 2026-04-20).

业务实现已迁到 workers/ (Diamond shortcut 模式). 本文件保留旧名称以兼容调用方.
内部 tool Routers (BashRouter / EditRouter / ...) 仍从 _archive/routers_legacy.py 可导入.
"""
from __future__ import annotations

from .workers import (
    ExperimenterWorker as ExperimenterRouter,
    LockstepExperimenterWorker as LockstepExperimenterRouter,
    ReflectorWorker as ReflectorRouter,
)
from ._archive.routers_legacy import (
    BashRouter,
    EditRouter,
    WriteFileRouter,
    FindSimilarFormatsRouter,
    ValidateHypothesisDocRouter,
)

__all__ = [
    "ExperimenterRouter",
    "LockstepExperimenterRouter",
    "ReflectorRouter",
    "BashRouter",
    "EditRouter",
    "WriteFileRouter",
    "FindSimilarFormatsRouter",
    "ValidateHypothesisDocRouter",
]
