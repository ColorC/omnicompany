# [OMNI] origin=claude-code domain=trace_induction/pipeline.py ts=2026-04-08T03:23:37Z
# [OMNI] material_id="material:learning.trace_induction.pipeline_topology.spec.py"
"""trace_induction pipeline — 轨迹归纳管线拓扑（7 节点）

trace_reader (HARD) → noise_filter (SOFT) → sop_generator (SOFT)
  → req_writer (SOFT) → wf_caller (SOFT/SubPipeline) → registrar (HARD)
"""

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


def build_team() -> TeamSpec:
    """构建 trace-induction 管线。"""

    nodes = [
        # ── [1] trace_reader — 确定性 DB 读取 ──
        TeamNode(
            id="trace_reader",
            kind=NodeKind.ANCHOR,
            anchor=AnchorSpec(
                id="a_trace_reader",
                name="trace_reader",
                format_in="ti.task",
                format_out="ti.trace-data",
                validator=ValidatorSpec(
                    id="v_trace_reader",
                    kind=ValidatorKind.HARD,
                    description="从 intent_steps 表确定性读取 trace 步骤数据",
                ),
                routes={
                    VerdictKind.PASS: Route(action=RouteAction.NEXT, target="noise_filter"),
                    VerdictKind.FAIL: Route(action=RouteAction.HALT),
                },
            ),
        ),

        # ── [2] noise_filter — LLM 标注噪音 ──
        TeamNode(
            id="noise_filter",
            kind=NodeKind.ANCHOR,
            anchor=AnchorSpec(
                id="a_noise_filter",
                name="noise_filter",
                format_in="ti.trace-data",
                format_out="ti.essential",
                validator=ValidatorSpec(
                    id="v_noise_filter",
                    kind=ValidatorKind.SOFT,
                    description="LLM 标注每步为 ESSENTIAL/EXPLORATION/MISTAKE/RETRY，过滤保留核心步骤",
                ),
                routes={
                    VerdictKind.PASS: Route(action=RouteAction.NEXT, target="sop_generator"),
                    VerdictKind.FAIL: Route(action=RouteAction.HALT),
                    VerdictKind.PARTIAL: Route(action=RouteAction.RETRY, max_retries=2),
                },
            ),
        ),

        # ── [3] sop_generator — LLM 生成结构化 SOP ──
        TeamNode(
            id="sop_generator",
            kind=NodeKind.ANCHOR,
            anchor=AnchorSpec(
                id="a_sop_generator",
                name="sop_generator",
                format_in="ti.essential",
                format_out="ti.sop",
                validator=ValidatorSpec(
                    id="v_sop_generator",
                    kind=ValidatorKind.SOFT,
                    description="LLM 将核心步骤合并为结构化 SOP（单 trace 直接转换，多 trace 合并共同模式）",
                ),
                routes={
                    VerdictKind.PASS: Route(action=RouteAction.NEXT, target="req_writer"),
                    VerdictKind.FAIL: Route(action=RouteAction.HALT),
                    VerdictKind.PARTIAL: Route(action=RouteAction.RETRY, max_retries=2),
                },
            ),
        ),

        # ── [4] req_writer — LLM 生成需求文档 ──
        TeamNode(
            id="req_writer",
            kind=NodeKind.ANCHOR,
            anchor=AnchorSpec(
                id="a_req_writer",
                name="req_writer",
                format_in="ti.sop",
                format_out="ti.requirement",
                validator=ValidatorSpec(
                    id="v_req_writer",
                    kind=ValidatorKind.SOFT,
                    description="LLM 将 SOP 转化为 Workflow Factory 可消费的 Markdown 需求文档",
                ),
                routes={
                    VerdictKind.PASS: Route(action=RouteAction.NEXT, target="wf_caller"),
                    VerdictKind.FAIL: Route(action=RouteAction.HALT),
                },
            ),
        ),

        # ── [5] wf_caller — SubTeamWorker 调用 workflow-factory ──
        TeamNode(
            id="wf_caller",
            kind=NodeKind.ANCHOR,
            anchor=AnchorSpec(
                id="a_wf_caller",
                name="wf_caller",
                format_in="ti.requirement",
                format_out="ti.wf-result",
                validator=ValidatorSpec(
                    id="v_wf_caller",
                    kind=ValidatorKind.SOFT,
                    description="通过 SubTeamWorker 调用 workflow-factory，共享 EventBus 保持可观测性",
                ),
                routes={
                    VerdictKind.PASS: Route(action=RouteAction.NEXT, target="registrar"),
                    VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=2),
                },
            ),
        ),

        # ── [6] registrar — 确定性注册 ──
        TeamNode(
            id="registrar",
            kind=NodeKind.ANCHOR,
            anchor=AnchorSpec(
                id="a_registrar",
                name="registrar",
                format_in="ti.wf-result",
                format_out="ti.done",
                validator=ValidatorSpec(
                    id="v_registrar",
                    kind=ValidatorKind.HARD,
                    description="将 WF 产出注册到 pipeline_index 语义索引",
                ),
                routes={
                    VerdictKind.PASS: Route(action=RouteAction.EMIT),
                    VerdictKind.FAIL: Route(action=RouteAction.HALT),
                },
            ),
        ),
    ]

    edges = [
        TeamEdge(source="trace_reader", target="noise_filter", condition=VerdictKind.PASS),
        TeamEdge(source="noise_filter", target="sop_generator", condition=VerdictKind.PASS),
        TeamEdge(source="sop_generator", target="req_writer", condition=VerdictKind.PASS),
        TeamEdge(source="req_writer", target="wf_caller", condition=VerdictKind.PASS),
        TeamEdge(source="wf_caller", target="registrar", condition=VerdictKind.PASS),
    ]

    return TeamSpec(
        id="trace-induction",
        name="trace-induction",
        description=(
            "轨迹归纳：从历史 trace 读取步骤 → 过滤噪音 → 提炼 SOP → "
            "生成需求文档 → 调用 Workflow Factory → 注册产出"
        ),
        entry="trace_reader",
        nodes=nodes,
        edges=edges,
        tags=["meta", "trace_induction"],
    )
