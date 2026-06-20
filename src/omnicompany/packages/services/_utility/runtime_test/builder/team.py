# [OMNI] origin=claude-code domain=services/runtime_test_builder/team ts=2026-04-27T00:00:00Z type=team
# [OMNI] material_id="material:utility.runtime_test.builder.team_topology.config.py"
"""runtime_test_builder Team · 真 meta 层 v2 拓扑 (Phase C 重构).

4 节点 (旧版 3 节点伪 meta 已替):
  TargetExplorerWorker (AGENT)
    ↓
  HypothesisProposerWorker (AGENT · 核心创新 · 综合 hypothesis_library 当场针对生成)
    ↓
  HypothesisVerifierDispatcherWorker (HARD · catalog 调度执行)
    ↓ + target_profile fan-in
  PortraitAssemblerWorker (HARD · sink)

旧 3 节点 (TargetAnalyzer / TestTeamDispatcher / PortraitForwarder · 二选一固定模板) 已删.
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
    NodeMaturity,
    TeamEdge,
    TeamNode,
    TeamSpec,
)


def _anchor(node_id, fmt_in, fmt_out, *, vkind, desc, routes):
    return TeamNode(
        id=node_id,
        kind=NodeKind.ANCHOR,
        maturity=NodeMaturity.GROWING,
        anchor=AnchorSpec(
            id=f"a_{node_id}",
            name=node_id,
            format_in=fmt_in,
            format_out=fmt_out,
            validator=ValidatorSpec(id=f"v_{node_id}", kind=vkind, description=desc),
            routes=routes,
        ),
    )


def build_team() -> TeamSpec:
    nodes = []
    common_routes = {
        VerdictKind.PASS: Route(action=RouteAction.NEXT),
        VerdictKind.PARTIAL: Route(action=RouteAction.NEXT),
        VerdictKind.FAIL: Route(action=RouteAction.NEXT),  # FAIL 也 forward 让 sink 始终产出
    }

    nodes.append(_anchor(
        "TargetExplorerWorker",
        "runtime_test_builder.build_request",
        "runtime_test_builder.target_profile",
        vkind=ValidatorKind.SOFT,
        desc="深探 target 包产 target_profile (多维度自然语言描述, 非二选一)",
        routes=common_routes,
    ))

    nodes.append(_anchor(
        "HypothesisProposerWorker",
        "runtime_test_builder.target_profile",
        "runtime_test_builder.hypothesis_set",
        vkind=ValidatorKind.SOFT,
        desc="综合 hypothesis_library 针对 target 当场产假设清单 (核心创新)",
        routes=common_routes,
    ))

    nodes.append(_anchor(
        "HypothesisVerifierDispatcherWorker",
        ["runtime_test_builder.hypothesis_set", "runtime_test_builder.target_profile"],
        "runtime_test_builder.hypothesis_evidence",
        vkind=ValidatorKind.HARD,
        desc="对每条假设 catalog 调度执行 · 未支持标 pending_manual",
        routes=common_routes,
    ))

    nodes.append(_anchor(
        "PortraitAssemblerWorker",
        [
            "runtime_test_builder.hypothesis_evidence",
            "runtime_test_builder.hypothesis_set",
            "runtime_test_builder.target_profile",
        ],
        "runtime_test_builder.portrait_with_meta",
        vkind=ValidatorKind.HARD,
        desc="装终态 portrait_with_meta · 综合 profile + hypotheses + evidence · sink",
        routes=common_routes,
    ))

    edges = [
        # 主链: Explorer → Proposer → Dispatcher → Assembler
        TeamEdge(
            source="TargetExplorerWorker",
            target="HypothesisProposerWorker",
            condition=VerdictKind.PASS,
        ),
        TeamEdge(
            source="HypothesisProposerWorker",
            target="HypothesisVerifierDispatcherWorker",
            condition=VerdictKind.PASS,
        ),
        # Dispatcher 需要 target_profile (composite fan-in)
        TeamEdge(
            source="TargetExplorerWorker",
            target="HypothesisVerifierDispatcherWorker",
            condition=VerdictKind.PASS,
        ),
        TeamEdge(
            source="HypothesisVerifierDispatcherWorker",
            target="PortraitAssemblerWorker",
            condition=VerdictKind.PASS,
        ),
        # Assembler 同时收 hypothesis_set 和 target_profile (composite fan-in)
        TeamEdge(
            source="HypothesisProposerWorker",
            target="PortraitAssemblerWorker",
            condition=VerdictKind.PASS,
        ),
        TeamEdge(
            source="TargetExplorerWorker",
            target="PortraitAssemblerWorker",
            condition=VerdictKind.PASS,
        ),
    ]

    return TeamSpec(
        id="runtime_test_builder",
        name="runtime_test_builder",
        description=(
            "真 meta 层 v2 测试团队构建器 · 针对 target 当场生成假设 + 调度验证 + 装画像 · "
            "非二选一固定模板"
        ),
        entry="TargetExplorerWorker",
        nodes=nodes,
        edges=edges,
        tags=["runtime_test_builder", "meta", "verification", "hypothesis_method"],
    )
