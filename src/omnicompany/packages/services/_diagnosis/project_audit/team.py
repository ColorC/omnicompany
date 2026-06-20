# [OMNI] origin=claude-code domain=services/_diagnosis/project_audit ts=2026-06-20T00:00:00Z type=team status=active
# [OMNI] summary="project_audit Team 拓扑:TreeEnumerator→PromptHarvester→CodeReader→PlanCompletionAuditor→ReportValidator;另含 discovery / completeness 两个单节点 team。"
# [OMNI] why="把'发现项目→遍历+据真源(prompt+代码)核实→完整性临界'做成统一可复用可观测的 omnicompany team 群。"
# [OMNI] material_id="material:services._diagnosis.project_audit.team"
"""project_audit Team · 拓扑声明。

三个 team(同 bucket,统一可复用):
- build_team()          : 主管线,对单个项目遍历 + 据真源核实(5 节点)。
- build_discovery_team(): 发现"我真做过的项目"(1 节点 ProjectDiscoverer)。
- build_completeness_team(): 完整性临界,不全打回(1 节点 CompletenessCritic)。
"""
from __future__ import annotations

from omnicompany.protocol.anchor import (
    AnchorSpec, Route, RouteAction, ValidatorKind, ValidatorSpec, VerdictKind,
)
from omnicompany.protocol.team import (
    NodeKind, NodeMaturity, TeamEdge, TeamNode, TeamSpec,
)


def _anchor(node_id, fmt_in, fmt_out, *, vkind, desc, routes, maturity=NodeMaturity.GROWING):
    return TeamNode(
        id=node_id,
        kind=NodeKind.ANCHOR,
        maturity=maturity,
        anchor=AnchorSpec(
            id=f'a_{node_id}',
            name=node_id,
            format_in=fmt_in,
            format_out=fmt_out,
            validator=ValidatorSpec(id=f'v_{node_id}', kind=vkind, description=desc),
            routes=routes,
        ),
    )


def build_team() -> TeamSpec:
    """主管线 — 遍历单个项目 + 据真源(prompt+代码内容)逐项核实完成度。"""
    nodes = [
        _anchor(
            'TreeEnumeratorWorker', 'project_audit.target', 'project_audit.tree',
            vkind=ValidatorKind.HARD,
            desc="os.walk 全量遍历项目文件树(非抽样),统计规模 + 落全部路径 + 挑计划文档。FAIL→重试1次。",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT),
                VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
            },
        ),
        _anchor(
            'PromptHarvester', 'project_audit.tree', 'project_audit.enriched',
            vkind=ValidatorKind.HARD,
            desc="跨 ~/.claude+~/.codex 全部会话,按 cwd/路径/关键词捞我的原始 prompt(A 类真源)。0 命中也 PASS(诚实标注)。",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT),
                VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
            },
        ),
        _anchor(
            'CodeReader', 'project_audit.enriched', 'project_audit.enriched',
            vkind=ValidatorKind.HARD,
            desc="真读关键文件内容(README/入口/配置/核心源码)+按语言统计代码量(B 类真源);修'只看路径'硬伤。",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT),
                VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
            },
        ),
        _anchor(
            'PlanCompletionAuditorWorker', 'project_audit.enriched', 'project_audit.report',
            vkind=ValidatorKind.SOFT,
            desc="据'原始 prompt + 真实代码内容 + 文件树'三类真源逐条计划项判 done/partial/not_done/uncertain——严禁采信复选框。PARTIAL 也下行。",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT),
                VerdictKind.PARTIAL: Route(action=RouteAction.NEXT),
                VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
            },
        ),
        _anchor(
            'ReportValidatorWorker', 'project_audit.report', 'project_audit.report',
            vkind=ValidatorKind.HARD,
            desc="SOFT 审计的紧下游硬校验(P-04):报告须含 project/real_scale/verified。PASS→emit。",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.EMIT),
                VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
            },
        ),
    ]
    edges = [
        TeamEdge(source='TreeEnumeratorWorker', target='PromptHarvester', condition=VerdictKind.PASS),
        TeamEdge(source='PromptHarvester', target='CodeReader', condition=VerdictKind.PASS),
        TeamEdge(source='CodeReader', target='PlanCompletionAuditorWorker', condition=VerdictKind.PASS),
        TeamEdge(source='PlanCompletionAuditorWorker', target='ReportValidatorWorker', condition=VerdictKind.PASS),
        TeamEdge(source='PlanCompletionAuditorWorker', target='ReportValidatorWorker', condition=VerdictKind.PARTIAL),
    ]
    return TeamSpec(
        id='project_audit',
        name='project_audit',
        description='项目遍历 + 据真源(我的原始prompt + 真实代码内容 + 文件树)逐条核实计划完成度,不信报告/复选框。',
        entry='TreeEnumeratorWorker',
        nodes=nodes,
        edges=edges,
        tags=['audit', 'traversal', 'diagnosis', 'completion', 'truth-source'],
    )


def build_discovery_team() -> TeamSpec:
    """发现'我真做过的项目'(归属过滤掉纯开源)。单节点。"""
    nodes = [
        _anchor(
            'ProjectDiscoverer', 'project_audit.discover_seed', 'project_audit.project_list',
            vkind=ValidatorKind.HARD,
            desc="据会话真实 cwd 频次 + 仓库扫描枚举项目,按归属边界标 owned。PASS→emit。",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.EMIT),
                VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
            },
        ),
    ]
    return TeamSpec(
        id='project_discovery',
        name='project_discovery',
        description='据真源(会话 cwd + 仓库扫描)发现我真做过的项目,归属过滤掉纯开源依赖。',
        entry='ProjectDiscoverer',
        nodes=nodes,
        edges=[],
        tags=['discovery', 'traversal', 'truth-source'],
    )


def build_completeness_team() -> TeamSpec:
    """完整性临界:每个 owned 项目都到-bar 才放行,否则打回。单节点。"""
    nodes = [
        _anchor(
            'CompletenessCritic', 'project_audit.completeness_seed', 'project_audit.completeness',
            vkind=ValidatorKind.HARD,
            desc="核对每个 owned 项目是否都有真源报告+到-bar 页;缺一 FAIL 并列 missing。PASS→emit。",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.EMIT),
                VerdictKind.FAIL: Route(action=RouteAction.EMIT),  # FAIL 也产出裁定(列出缺什么),由编排据此打回
            },
        ),
    ]
    return TeamSpec(
        id='audit_completeness',
        name='audit_completeness',
        description='完整性临界:每个 owned 项目都有真源报告+到九维-bar 的页才算完,否则列出缺失打回。',
        entry='CompletenessCritic',
        nodes=nodes,
        edges=[],
        tags=['completeness', 'gate', 'quality'],
    )
