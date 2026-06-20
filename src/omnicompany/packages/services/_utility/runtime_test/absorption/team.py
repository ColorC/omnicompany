# [OMNI] origin=claude-code domain=services/absorption_runtime_test/team ts=2026-04-27T00:00:00Z type=team
# [OMNI] material_id="material:utility.runtime_test.absorption.team_topology.config.py"
"""absorption_runtime_test Team · 拓扑.

6 节点 (1 入口 + 1 取样 + 3 验证并行 + 1 装配):
  TargetIngressWorker (HARD)
    ↓
  SampleRunsExecutorWorker (HARD · subprocess 隔离)
    ↓
    ├──→ CrossRunStabilityVerifierWorker (SOFT · 路 1 通用)
    ├──→ SpotImplVerifierWorker (AGENT · 路 3 absorption 特化)
    └──→ SourceCoverageVerifierWorker (AGENT · 路 4 absorbing 特化)
              ↓ 3 路 fan-in
         PortraitAssemblerWorker (HARD · sink)

2026-04-27 改名 (旧: knowledge_runtime_test 7 节点) + 删 IndependentReevalVerifier (路 2).
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


def _anchor(node_id, fmt_in, fmt_out, *, vkind, desc, routes, maturity=NodeMaturity.GROWING):
    return TeamNode(
        id=node_id,
        kind=NodeKind.ANCHOR,
        maturity=maturity,
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

    nodes.append(_anchor(
        "TargetIngressWorker",
        "absorption_runtime_test.target_spec",
        "absorption_runtime_test.target_metadata",
        vkind=ValidatorKind.HARD,
        desc="装入 · 校 target_team_id 在 PipelineRegistry 注册 · 推 target 包目录 · 透传 sample_input/run_count/spot_impl_count.",
        routes={
            VerdictKind.PASS: Route(action=RouteAction.NEXT),
            VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
        },
    ))

    nodes.append(_anchor(
        "SampleRunsExecutorWorker",
        "absorption_runtime_test.target_metadata",
        "absorption_runtime_test.sample_runs",
        vkind=ValidatorKind.HARD,
        desc="真跑目标团队 N 次取样 · subprocess 隔离避嵌套 dispatch async loop 冲突 · 收齐 N 条 (含失败).",
        routes={
            VerdictKind.PASS: Route(action=RouteAction.NEXT),
            VerdictKind.PARTIAL: Route(action=RouteAction.NEXT),
            VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
        },
    ))

    nodes.append(_anchor(
        "CrossRunStabilityVerifierWorker",
        ["absorption_runtime_test.sample_runs", "absorption_runtime_test.target_metadata"],
        "absorption_runtime_test.cross_run_evidence",
        vkind=ValidatorKind.SOFT,
        desc="路 1 跨次稳定性 (通用假设) · 算文件层重叠 + LLM 判主题层重叠 · 输出自然语言 stability_observation 句子.",
        routes={
            VerdictKind.PASS: Route(action=RouteAction.NEXT),
            VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
        },
    ))

    nodes.append(_anchor(
        "SpotImplVerifierWorker",
        ["absorption_runtime_test.sample_runs", "absorption_runtime_test.target_metadata"],
        "absorption_runtime_test.spot_impl_evidence",
        vkind=ValidatorKind.SOFT,
        desc="路 3 抽样落地 (absorption 特化) · 让 LLM 真写实施代码 + 二轮 LLM 判是否解决 · 输出 groundedness_observation 句子.",
        routes={
            VerdictKind.PASS: Route(action=RouteAction.NEXT),
            VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
        },
    ))

    nodes.append(_anchor(
        "SourceCoverageVerifierWorker",
        ["absorption_runtime_test.sample_runs", "absorption_runtime_test.target_metadata"],
        "absorption_runtime_test.source_coverage_evidence",
        vkind=ValidatorKind.SOFT,
        desc="路 4 源覆盖 (absorbing 特化) · 程序化排名 top-K 候选 + LLM 在候选里选语义关键模块 · 看目标漏没 · 输出 coverage_observation 句子.",
        routes={
            VerdictKind.PASS: Route(action=RouteAction.NEXT),
            VerdictKind.PARTIAL: Route(action=RouteAction.NEXT),
            VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
        },
    ))

    nodes.append(_anchor(
        "PortraitAssemblerWorker",
        [
            "absorption_runtime_test.cross_run_evidence",
            "absorption_runtime_test.spot_impl_evidence",
            "absorption_runtime_test.source_coverage_evidence",
            "absorption_runtime_test.target_metadata",
        ],
        "absorption_runtime_test.portrait",
        vkind=ValidatorKind.HARD,
        desc="装画像 sink · HARD · 不调 LLM · 3 路证据汇总 + 派生 verdict + 自然语言段落 + 做得好/漏 句子列表.",
        routes={
            VerdictKind.PASS: Route(action=RouteAction.NEXT),
            VerdictKind.PARTIAL: Route(action=RouteAction.NEXT),
            VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
        },
    ))

    edges = []

    # Ingress → SampleRuns
    edges.append(TeamEdge(
        source="TargetIngressWorker",
        target="SampleRunsExecutorWorker",
        condition=VerdictKind.PASS,
    ))

    # SampleRuns + TargetMetadata → 3 验证器 (composite fan-in)
    for verifier in [
        "CrossRunStabilityVerifierWorker",
        "SpotImplVerifierWorker",
        "SourceCoverageVerifierWorker",
    ]:
        edges.append(TeamEdge(
            source="SampleRunsExecutorWorker",
            target=verifier,
            condition=VerdictKind.PASS,
        ))
        edges.append(TeamEdge(
            source="SampleRunsExecutorWorker",
            target=verifier,
            condition=VerdictKind.PARTIAL,
        ))
        edges.append(TeamEdge(
            source="TargetIngressWorker",
            target=verifier,
            condition=VerdictKind.PASS,
        ))

    # 3 验证器 + TargetMetadata → PortraitAssembler (composite fan-in)
    for verifier in [
        "CrossRunStabilityVerifierWorker",
        "SpotImplVerifierWorker",
        "SourceCoverageVerifierWorker",
    ]:
        edges.append(TeamEdge(
            source=verifier,
            target="PortraitAssemblerWorker",
            condition=VerdictKind.PASS,
        ))
        edges.append(TeamEdge(
            source=verifier,
            target="PortraitAssemblerWorker",
            condition=VerdictKind.PARTIAL,
        ))
    edges.append(TeamEdge(
        source="TargetIngressWorker",
        target="PortraitAssemblerWorker",
        condition=VerdictKind.PASS,
    ))

    return TeamSpec(
        id="absorption_runtime_test",
        name="absorption_runtime_test",
        description="absorption 类工作的特化测试团队 · 真跑 + 3 路多源验证 + 画像 (非通用模板, 非契约扫)",
        entry="TargetIngressWorker",
        nodes=nodes,
        edges=edges,
        tags=["absorption_runtime_test", "verification", "absorption"],
    )
