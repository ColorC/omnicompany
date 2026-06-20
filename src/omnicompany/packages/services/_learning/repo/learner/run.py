# [OMNI] origin=claude-code domain=services/repo_learner ts=2026-04-09T12:00:00Z
# [OMNI] material_id="material:learning.repo.learner.pipeline_bindings_builder.py"
"""repo_learner run — pipeline + bindings 入口。

bindings 的关键是前 4 个节点直接 import 自 repo_architect, 不 copy 不 fork。
这就是 '多条工作流共享节点池' 的落地形态 — 代码层面复用, 两条管线天然共享这些节点
的所有后续修复。
"""

from __future__ import annotations

from typing import Any


def build_repo_learner_pipeline():
    from omnicompany.packages.services._learning.repo.learner.pipeline import build_pipeline
    return build_pipeline()


def build_repo_learner_bindings(input_dict: dict[str, Any] | None = None):
    # ── 前 4 个共享节点: 直接 import 自 repo_architect ──────
    from omnicompany.packages.services._learning.repo.architect.routers import (
        InputValidatorRouter,
        RepoAcquirerRouter,
        RepoIdentityAnchorRouter,
        ScaleSurveyorRouter,
    )
    # ── repo_learner 自己的 2 个新节点 ─────────────────────
    from omnicompany.packages.services._learning.repo.learner.routers import (
        LearnDimensionsLoaderRouter,
        MainLearnerAgent,
    )

    inp = input_dict or {}
    canonical_name = (
        inp.get("canonical_name")
        or inp.get("name")
        or inp.get("local_path", "").rstrip("/").rsplit("/", 1)[-1]
        or "unknown"
    )
    working_path = inp.get("local_path", "") or inp.get("working_path", "")

    return {
        "input_validator": InputValidatorRouter(),
        "repo_acquirer": RepoAcquirerRouter(),
        "repo_identity_anchor": RepoIdentityAnchorRouter(),
        "scale_surveyor": ScaleSurveyorRouter(),
        "learn_dimensions_loader": LearnDimensionsLoaderRouter(),
        "main_learner": MainLearnerAgent(
            canonical_name=canonical_name,
            working_path=working_path,
        ),
    }
