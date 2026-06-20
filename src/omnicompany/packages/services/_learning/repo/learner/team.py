# [OMNI] origin=claude-code domain=services/repo_learner ts=2026-04-09T12:00:00Z
# [OMNI] material_id="material:learning.repo.learner.team_topology_spec.py"
"""repo_learner pipeline — 6 节点线性主链。

拓扑 (前 4 节点从 repo_architect 复用, 后 2 节点新建):

  input_validator → repo_acquirer → repo_identity_anchor
    → scale_surveyor → learn_dimensions_loader
    → main_learner (EMIT: learning-report)

无 fallback, 无回环门。错误处理全交给 AgentNodeLoop 自身的 retry / compact /
should_force_finish 机制。
"""

from __future__ import annotations

from omnicompany.protocol.anchor import (
    AnchorSpec,
    Route,
    RouteAction,
    ValidatorKind,
    ValidatorSpec,
    VerdictKind,
)
from omnicompany.protocol.team import (
    NodeKind,
    TeamEdge,
    TeamNode,
    TeamSpec,
)


def _anchor(
    node_id: str, fmt_in: str, fmt_out: str,
    *, vkind: ValidatorKind, desc: str,
    routes: dict[VerdictKind, Route],
) -> TeamNode:
    return TeamNode(
        id=node_id,
        kind=NodeKind.ANCHOR,
        anchor=AnchorSpec(
            id=f"a_{node_id}",
            name=node_id,
            format_in=fmt_in,
            format_out=fmt_out,
            validator=ValidatorSpec(
                id=f"v_{node_id}",
                kind=vkind,
                description=desc,
            ),
            routes=routes,
        ),
    )


def build_team() -> TeamSpec:
    nodes: list[TeamNode] = [
        _anchor(
            "input_validator", "repo-architect.input", "repo-architect.input",
            vkind=ValidatorKind.HARD,
            desc="严格校验输入 schema (复用 repo_architect)",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="repo_acquirer"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
        _anchor(
            "repo_acquirer", "repo-architect.input", "repo-architect.acquired-repo",
            vkind=ValidatorKind.HARD,
            desc="mount local_path 或 clone url (复用 repo_architect)",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="repo_identity_anchor"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
        _anchor(
            "repo_identity_anchor",
            "repo-architect.acquired-repo", "repo-architect.repo-identity",
            vkind=ValidatorKind.HARD,
            desc="提取 canonical_name + disambiguation_hint (复用 repo_architect)",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="scale_surveyor"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
        _anchor(
            "scale_surveyor", "repo-architect.repo-identity", "repo-architect.scaled-survey",
            vkind=ValidatorKind.HARD,
            desc="扫出真实 code_modules (复用 repo_architect, 每个带 discovered_via)",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="learn_dimensions_loader"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
        _anchor(
            "learn_dimensions_loader",
            "repo-architect.scaled-survey", "repo-learner.learn-dimensions",
            vkind=ValidatorKind.HARD,
            desc="注入 19 条观察维度参考清单 (不声明 OmniCompany 自画像)",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="main_learner"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
        _anchor(
            "main_learner",
            "repo-learner.learn-dimensions", "repo-learner.learning-report",
            vkind=ValidatorKind.SOFT,
            desc=(
                "AgentNodeLoop 主学习 agent (150 turns max), 自由读 + 维护 ledger + "
                "最多 spawn 3 个子 agent, 产出 Learning Value + Learning Locations"
            ),
            routes={
                VerdictKind.PASS: Route(action=RouteAction.EMIT),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
    ]

    edges = [
        TeamEdge(source="input_validator", target="repo_acquirer", condition=VerdictKind.PASS),
        TeamEdge(source="repo_acquirer", target="repo_identity_anchor", condition=VerdictKind.PASS),
        TeamEdge(source="repo_identity_anchor", target="scale_surveyor", condition=VerdictKind.PASS),
        TeamEdge(source="scale_surveyor", target="learn_dimensions_loader", condition=VerdictKind.PASS),
        TeamEdge(source="learn_dimensions_loader", target="main_learner", condition=VerdictKind.PASS),
    ]

    return TeamSpec(
        id="repo-learner",
        name="repo-learner",
        description=(
            "带目的的 repo 学习支流 — 主 agent 自由读仓库, 最多 spawn 3 个子 agent "
            "深读模块, 产出自由格式 learning report (Learning Value + Learning Locations "
            "两段必含)。与 repo_architect 并列, 共享前 4 个基础节点。"
        ),
        entry="input_validator",
        nodes=nodes,
        edges=edges,
        tags=["domain.repo_learner", "absorption", "purposeful_learning"],
    )
