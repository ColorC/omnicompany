# [OMNI] origin=claude-code domain=services/hypothesis ts=2026-04-20T00:00:00Z type=config
# [OMNI] material_id="material:learning.hypothesis.worker_registry.exports.py"
"""hypothesis Team 的 Worker 集合 (Diamond shortcut · Phase D 2026-04-20).

3 个 Pipeline-level Worker:
  - ExperimenterWorker:          主探索 AgentNodeLoop (SOFT)
  - LockstepExperimenterWorker:  双脑 lockstep 主脑 (SOFT)
  - ReflectorWorker:             总结 AgentNodeLoop (SOFT)

Diamond shortcut: Worker + _LegacyRouter 双继承, 业务逻辑在 _archive/routers_legacy.py.
注意: _archive/ 内容已是 Phase C (packages.services.agent.AgentNodeLoop), 非遗留旧代码。
"""
from __future__ import annotations

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.packages.services._learning.hypothesis._archive.routers_legacy import (
    ExperimenterRouter as _Experimenter,
    LockstepExperimenterRouter as _LockstepExperimenter,
    ReflectorRouter as _Reflector,
)


class ExperimenterWorker(Worker, _Experimenter):
    """主探索 AgentNodeLoop：自由探索，输出行为轨迹（hypothesis.store → hypothesis.factlog）。"""


class LockstepExperimenterWorker(Worker, _LockstepExperimenter):
    """双脑 lockstep 主脑：每 turn 末同步等反思脑，注入 context_substitution。"""


class ReflectorWorker(Worker, _Reflector):
    """总结 AgentNodeLoop：读 Experimenter 轨迹 + 假设文档，编辑文档（hypothesis.factlog → hypothesis.store_diff）。"""


ALL_WORKERS = [
    ExperimenterWorker,
    LockstepExperimenterWorker,
    ReflectorWorker,
]

__all__ = [
    "ExperimenterWorker",
    "LockstepExperimenterWorker",
    "ReflectorWorker",
    "ALL_WORKERS",
]
