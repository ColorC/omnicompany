# [OMNI] origin=team_builder domain=services/repo_absorption/team ts=2026-04-25T00:00:00Z type=team
# [OMNI] material_id="material:learning.repo.absorption.team_topology_spec.py"
"""repo_absorption Team · 拓扑声明 (team_builder 自动产出)."""
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
    """构建 repo_absorption Team."""
    nodes = []
    nodes.append(_anchor(
        'RepoScannerWorker', 'repo_absorption.scan_config', 'repo_absorption.file_inventory',
        vkind=ValidatorKind.HARD,
        desc="HARD · 规则驱动确定性遍历 · 无 LLM\n\n1. 从 input_data['repo_absorption.scan_config'] 提取 repo_path (str) 与 top_n (int)；若任一缺失 → Verdict(FAIL, diagnosis='scan_config 缺 repo_path 或 top_n')\n2. BashBus.run(['test', '-d', repo_path]) 校验目录存在；若不存在 → Verdict(FAIL, diagnosis=f'repo_path {repo_path} 不存在')\n3. BashBus.run(['",
        routes={
            VerdictKind.PASS: Route(action=RouteAction.NEXT),
            VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
        },
    ))
    nodes.append(_anchor(
        'ModuleSelectorWorker', ['repo_absorption.file_inventory', 'repo_absorption.scan_config'], 'repo_absorption.selected_modules',
        vkind=ValidatorKind.SOFT,
        desc="你是 repo_absorption pipeline 的 ModuleSelectorWorker — 一个基于 LLM 的模块选择 Agent。\n\n职责: 接收文件索引 (file_inventory) 与扫描配置 (scan_config), 通过评估每个 .py 文件的复杂度、结构特征 (行数、体积、命名模式) 来智能筛选 top_n 关键模块, 供下游 SourceReaderWorker 读取源码后做模式提取。\n\n判定维度:\n1. **体积权重**: 行数/体积显著高于中位数的文件往往承载核心逻辑 (但排除巨型测试/fixture 文件)\n2. **命名启发**: 含 'core'",
        routes={
            VerdictKind.PASS: Route(action=RouteAction.NEXT),
            VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
        },
    ))
    nodes.append(_anchor(
        'SourceReaderWorker', 'repo_absorption.selected_modules', 'repo_absorption.module_sources',
        vkind=ValidatorKind.SOFT,
        desc='你是 OmniCompany repo_absorption 管线的源码读取专家。你的职责是对选中的 Python 模块执行全量读取，严格遵守铁律 A：无预防性截断，>1MB 文件按需分片。\n\n规则：\n1. 对每个选中的模块，通过 FileBus.read(path=...) 读取完整源码，禁止任何预防性截断。\n2. 仅当单文件 >1,048,576 字节（1MB）时，在自然边界（class/def 定义行、三引号 docstring 边界）进行分片。\n3. 绝对禁止在行中间、字符串内部、注释内部截断。\n4. 为每个模块输出结构化数据，包含：file_path、source_content（≤',
        routes={
            VerdictKind.PASS: Route(action=RouteAction.NEXT),
            VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
        },
    ))
    nodes.append(_anchor(
        'PatternExtractorWorker', 'repo_absorption.module_sources', 'repo_absorption.extraction_results',
        vkind=ValidatorKind.SOFT,
        desc='你是 PatternExtractor · AGENT 模式下的源码深度分析专家。职责: 读取完整模块源码, 提取真实存在的代码模式(设计模式、架构范式、数据流特征、错误处理策略等), 生成带 PRO-NNN 唯一标识的结构化提案数组。每条提案必须附带逐字级 reference_code 锚点(从源码中精确引用的代码片段)。严格遵守 F-15 诚实原则: 只报告源码中真实存在的模式, 不推断、不脑补、不编造参考锚点。若某模块无法提取有意义模式, 明确声明而非强行捏造。',
        routes={
            VerdictKind.PASS: Route(action=RouteAction.NEXT),
            VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
        },
    ))
    nodes.append(_anchor(
        'ReportAssemblerWorker', ['repo_absorption.extraction_results', 'repo_absorption.module_sources'], 'repo_absorption.sink_report',
        vkind=ValidatorKind.HARD,
        desc='HARD 规则驱动 · 无 LLM · 使用 DiskBus 读写。\n步骤 1: 从 repo_absorption.extraction_results 读取 proposals 数组 (每项含 PRO-NNN 标识 + reference_code 锚点 + risk_rating)。\n步骤 2: JSON Schema 校验 — 检查 proposals 数组非空、每项必有 {proposal_id: str, title: str, reference_code: str, description: str, risk_rating: str}，缺失任一字段 → FAIL。\n步骤 3:',
        routes={
            VerdictKind.PASS: Route(action=RouteAction.NEXT),
            VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),
        },
    ))
    edges = []
    edges.append(TeamEdge(source="RepoScannerWorker", target="ModuleSelectorWorker", condition=VerdictKind.PASS))
    edges.append(TeamEdge(source="ModuleSelectorWorker", target="SourceReaderWorker", condition=VerdictKind.PASS))
    edges.append(TeamEdge(source="SourceReaderWorker", target="PatternExtractorWorker", condition=VerdictKind.PASS))
    edges.append(TeamEdge(source="SourceReaderWorker", target="PatternExtractorWorker", condition=VerdictKind.PARTIAL))
    edges.append(TeamEdge(source="PatternExtractorWorker", target="ReportAssemblerWorker", condition=VerdictKind.PASS))
    edges.append(TeamEdge(source="PatternExtractorWorker", target="ReportAssemblerWorker", condition=VerdictKind.PARTIAL))
    # 2026-04-25 fix · ReportAssembler.FORMAT_IN = fan-in [extraction_results, module_sources]
    # 之前 boilerplate 只建 PatternExtractor 一条入边 · SourceReader 的 modules 没传到
    edges.append(TeamEdge(source="SourceReaderWorker", target="ReportAssemblerWorker", condition=VerdictKind.PASS))
    edges.append(TeamEdge(source="SourceReaderWorker", target="ReportAssemblerWorker", condition=VerdictKind.PARTIAL))
    return TeamSpec(
        id='repo_absorption',
        name='repo_absorption',
        description='repo_absorption team',
        entry='RepoScannerWorker',
        nodes=nodes,
        edges=edges,
        tags=['repo_absorption', 'generated'],
    )
