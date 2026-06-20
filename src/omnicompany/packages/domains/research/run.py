# [OMNI] origin=ai-ide domain=research ts=2026-06-14T00:00:00Z type=cli_entry status=active
# [OMNI] summary="research domain 的 bindings 工厂: 节点 ID → Router 实例。供 dispatch 调度。"
# [OMNI] why="框架级统一:Team 的节点要绑到具体 Worker。run.py 出 bindings,与 team.py 的节点 id 对齐。"
# [OMNI] tags=research,run,bindings

from __future__ import annotations

from typing import Any

from omnicompany.runtime.routing.router import Router


def build_research_bindings(input_dict: dict[str, Any] | None = None) -> dict[str, Router]:
    """research.run 的节点 ID → Router 绑定(6 节点 SOTA 管线)。"""
    from omnicompany.packages.domains.research.routers.deep import Orchestrator, Planner
    from omnicompany.packages.domains.research.routers.pipeline import LibraryWrite, TopicIntake
    from omnicompany.packages.domains.research.routers.synth import ClaimVerify, Synthesize

    return {
        "intake": TopicIntake(),
        "planner": Planner(),
        "orchestrate": Orchestrator(),
        "synthesize": Synthesize(),
        "claim_verify": ClaimVerify(),
        "library_write": LibraryWrite(),
    }
