# [OMNI] origin=claude-code domain=services/hypothesis ts=2026-04-18T00:00:00Z type=bindings status=active
# [OMNI] material_id="material:services.learning.hypothesis.team.bindings_builder.py"
"""hypothesis.run — 构建 TeamSpec 的 bindings。

注意：hypothesis 真实执行入口是 hypothesis.pipeline.run_session()，
它外部驱动 N 轮 Experimenter→Reflector 循环。

这里的 bindings 用于 `omni describe hypothesis` 可视化，
以及未来把 run_session 迁入 TeamRunner 时直接复用。
"""

from __future__ import annotations

from omnicompany.runtime.routing.router import Router


def build_bindings(input_dict: dict | None = None) -> dict[str, Router]:
    from omnicompany.packages.services._learning.hypothesis.routers import (
        ExperimenterRouter,
        ReflectorRouter,
    )
    return {
        "experimenter": ExperimenterRouter(),
        "reflector": ReflectorRouter(),
    }
