# [OMNI] origin=ai-ide domain=research ts=2026-06-14T00:00:00Z type=team status=active
# [OMNI] summary="research domain 的 Team。公开调研管线声明成 6 节点图(SOTA parity)。"
# [OMNI] why="框架级统一:管线只能是 Team。research.run = 入题→规划(真拆题)→编排(并行子研究+反思迭代)→综合→核源→落库。迭代循环塞在 orchestrator 节点内(DAG 不支持循环)。"
# [OMNI] tags=research,team,pipeline,sota
"""research domain Teams。"""

from __future__ import annotations

from omnicompany.protocol.anchor import TransformerSpec, TransformMethod
from omnicompany.protocol.team import (
    NodeKind,
    NodeMaturity,
    TeamEdge,
    TeamNode,
    TeamSpec,
)


def _node(nid: str, name: str, fmt_in: str, fmt_out: str, method: TransformMethod, desc: str) -> TeamNode:
    return TeamNode(
        id=nid,
        kind=NodeKind.TRANSFORMER,
        transformer=TransformerSpec(
            id=f"research-{nid}", name=name, from_format=fmt_in, to_format=fmt_out,
            method=method, description=desc,
        ),
        maturity=NodeMaturity.GROWING,
    )


def build_research_pipeline() -> TeamSpec:
    """公开调研主管线(SOTA parity): 入题→规划→编排(并行子研究+反思迭代)→综合→核源→落库。"""
    nodes = [
        _node("intake", "TopicIntake", "research.request", "research.intake",
              TransformMethod.RULE, "归一化题目 + 查重门(同题带出增量),建 run_dir。"),
        _node("planner", "Planner", "research.intake", "research.plan",
              TransformMethod.LLM, "先搜后拆: 拿原题搜背景→中端模型产互不重叠多视角子主题。"),
        _node("orchestrate", "Orchestrator", "research.plan", "research.gathered",
              TransformMethod.LLM, "并行派子研究员(隔离上下文)+ 反思看覆盖账本指缺口 + 有界迭代深挖。"),
        _node("synthesize", "Synthesize", "research.gathered", "research.synthesis",
              TransformMethod.LLM, "据带来源发现综合成接地、带引用、不打分的结论(便宜档,失败降级)。"),
        _node("claim_verify", "ClaimVerify", "research.synthesis", "research.verified",
              TransformMethod.LLM, "对抗式逐条断言抓原始来源判 supported/unsupported(中端,并行)。"),
        _node("library_write", "LibraryWrite", "research.verified", "research.record",
              TransformMethod.RULE, "组装 record,去重累积 upsert 进统一研究库,渲 report.md。"),
    ]
    edges = [
        TeamEdge(source="intake", target="planner"),
        TeamEdge(source="planner", target="orchestrate"),
        TeamEdge(source="orchestrate", target="synthesize"),
        TeamEdge(source="synthesize", target="claim_verify"),
        TeamEdge(source="claim_verify", target="library_write"),
    ]
    return TeamSpec(
        id="research.run",
        name="公开调研管线",
        description="通用公开调研(SOTA): 入题查重→真拆题→并行子研究+反思迭代→接地综合→对抗核源→落统一库(累积/不重复)。",
        nodes=nodes,
        edges=edges,
        entry="intake",
        tags=["domain.research", "stage.research"],
    )
