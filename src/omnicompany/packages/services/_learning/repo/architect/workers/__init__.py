# [OMNI] origin=claude-code domain=services/repo_architect ts=2026-04-20T00:00:00Z type=config
# [OMNI] material_id="material:learning.repo.architect.worker.package_exports.py"
"""repo_architect Team 的 Worker 集合 (Diamond shortcut · Phase D 2026-04-20).

21 个 Worker (6 阶段):
  阶段 1 准备:
  - InputValidatorWorker:        校验输入参数 (HARD)
  - RepoAcquirerWorker:          Clone/Mount 仓库 (HARD)
  - RepoIdentityAnchorWorker:    从真实文件提取项目身份 (HARD)
  - ScaleSurveyorWorker:         LLM 规模评估 + 模块拓扑 (SOFT)
  - ModeSelectorWorker:          规模→模式决策 (HARD)
  - DefaultModeWorker:           默认模式回落 (HARD)

  阶段 2 信息收集 (三条并行分支):
  - RepoIntrospectionWorker:     LLM 调研笔记 (SOFT)
  - ResearchDegradedWorker:      降级研究回落 (HARD)
  - DocsReaderWorker:            LLM 文档摘要 (SOFT)
  - DocsFallbackWorker:          无文档时回落 (HARD)
  - AdaptiveInterviewerWorker:   UserInquiry 焦点问卷 (SOFT)
  - InterviewDefaultsWorker:     默认焦点回落 (HARD)

  阶段 3 报告骨架:
  - ReportDesignerWorker:        LLM 报告结构设计 (SOFT)

  阶段 4 并行深度分析:
  - ModuleDrafterLeafWorker:     LLM 单模块深度分析 (SOFT, Scatter Leaf)
  - DraftCollectorWorker:        收集 scatter 产物 (HARD)

  阶段 5 质量门:
  - CoverageGaterWorker:         覆盖率门控 (HARD)
  - ValidatedDraftsWorker:       通过门控的草稿汇合 (HARD)
  - CrossValidatorWorker:        LLM 模块间一致性检查 (SOFT)

  阶段 6 融合发布:
  - ReportFuserWorker:           LLM 融合成架构报告 (SOFT)
  - CoverageReporterWorker:      生成覆盖率报告 (HARD)
  - KBIngesterWorker:            写入 OmniKB 知识库 (HARD)

Diamond shortcut: Worker + _LegacyRouter 双继承, 业务逻辑在 _archive/routers_legacy.py.
"""
from __future__ import annotations

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.packages.services._learning.repo.architect._archive.routers_legacy import (
    InputValidatorRouter as _InputValidator,
    RepoAcquirerRouter as _RepoAcquirer,
    RepoIdentityAnchorRouter as _RepoIdentityAnchor,
    ScaleSurveyorRouter as _ScaleSurveyor,
    ModeSelectorRouter as _ModeSelector,
    DefaultModeRouter as _DefaultMode,
    RepoIntrospectionRouter as _RepoIntrospection,
    ResearchDegradedRouter as _ResearchDegraded,
    DocsReaderRouter as _DocsReader,
    DocsFallbackRouter as _DocsFallback,
    AdaptiveInterviewerRouter as _AdaptiveInterviewer,
    InterviewDefaultsRouter as _InterviewDefaults,
    ReportDesignerRouter as _ReportDesigner,
    ModuleDrafterLeafRouter as _ModuleDrafterLeaf,
    DraftCollectorRouter as _DraftCollector,
    CoverageGaterRouter as _CoverageGater,
    ValidatedDraftsRouter as _ValidatedDrafts,
    CrossValidatorRouter as _CrossValidator,
    ReportFuserRouter as _ReportFuser,
    CoverageReporterRouter as _CoverageReporter,
    KBIngesterRouter as _KBIngester,
)


class InputValidatorWorker(Worker, _InputValidator):
    """校验用户输入：url/local_path 互斥，schema 合法性检查。"""


class RepoAcquirerWorker(Worker, _RepoAcquirer):
    """Clone GitHub URL 或 Mount 本地路径，产出已获取仓库元数据。"""


class RepoIdentityAnchorWorker(Worker, _RepoIdentityAnchor):
    """从真实文件（pyproject.toml/README等）提取项目官方身份，防 LLM 幻觉。"""


class ScaleSurveyorWorker(Worker, _ScaleSurveyor):
    """LLM 评估仓库规模 + 识别代码模块拓扑，产出 scaled-survey。"""


class ModeSelectorWorker(Worker, _ModeSelector):
    """根据规模和用户指定选择分析模式（quick/standard/deep）。"""


class DefaultModeWorker(Worker, _DefaultMode):
    """无用户输入时按规模自动选择默认模式的回落节点。"""


class RepoIntrospectionWorker(Worker, _RepoIntrospection):
    """LLM 读仓库真实文件做调研笔记，产出 research-notes。"""


class ResearchDegradedWorker(Worker, _ResearchDegraded):
    """研究降级回落：无法访问时产出 degraded status 的 research-notes。"""


class DocsReaderWorker(Worker, _DocsReader):
    """LLM 读文档文件产出设计决策证据清单，产出 docs-summary。"""


class DocsFallbackWorker(Worker, _DocsFallback):
    """无文档时回落：产出 no_docs status 的 docs-summary。"""


class AdaptiveInterviewerWorker(Worker, _AdaptiveInterviewer):
    """UserInquiry 1-3 轮交互提炼用户关注焦点，产出 user-focus-profile。"""


class InterviewDefaultsWorker(Worker, _InterviewDefaults):
    """无用户输入时按默认值生成 user-focus-profile 的回落节点。"""


class ReportDesignerWorker(Worker, _ReportDesigner):
    """LLM 综合三路信息设计报告骨架 + focus_modules 列表。"""


class ModuleDrafterLeafWorker(Worker, _ModuleDrafterLeaf):
    """LLM 单模块深度分析（Scatter Leaf），产出带证据链的 module-draft。"""


class DraftCollectorWorker(Worker, _DraftCollector):
    """收集所有 scatter leaf 产出，汇总成 draft-set。"""


class CoverageGaterWorker(Worker, _CoverageGater):
    """基于 coverage_status 语义决定 pass/retry/fail，产出 coverage-feedback。"""


class ValidatedDraftsWorker(Worker, _ValidatedDrafts):
    """通过覆盖率门控后汇合草稿，产出 validated-drafts。"""


class CrossValidatorWorker(Worker, _CrossValidator):
    """LLM 模块间一致性检查，产出 cross-validation（带 evidence_upstream）。"""


class ReportFuserWorker(Worker, _ReportFuser):
    """LLM 融合所有分析产出最终架构报告，落盘到 data/absorption/reports/。"""


class CoverageReporterWorker(Worker, _CoverageReporter):
    """生成覆盖率汇总报告（语义状态而非百分比），落盘到 data/absorption/coverage/。"""


class KBIngesterWorker(Worker, _KBIngester):
    """把架构报告 + 覆盖率报告写入 OmniKB，产出 kb-entry（管线终点）。"""


ALL_WORKERS = [
    InputValidatorWorker,
    RepoAcquirerWorker,
    RepoIdentityAnchorWorker,
    ScaleSurveyorWorker,
    ModeSelectorWorker,
    DefaultModeWorker,
    RepoIntrospectionWorker,
    ResearchDegradedWorker,
    DocsReaderWorker,
    DocsFallbackWorker,
    AdaptiveInterviewerWorker,
    InterviewDefaultsWorker,
    ReportDesignerWorker,
    ModuleDrafterLeafWorker,
    DraftCollectorWorker,
    CoverageGaterWorker,
    ValidatedDraftsWorker,
    CrossValidatorWorker,
    ReportFuserWorker,
    CoverageReporterWorker,
    KBIngesterWorker,
]

__all__ = [
    "InputValidatorWorker",
    "RepoAcquirerWorker",
    "RepoIdentityAnchorWorker",
    "ScaleSurveyorWorker",
    "ModeSelectorWorker",
    "DefaultModeWorker",
    "RepoIntrospectionWorker",
    "ResearchDegradedWorker",
    "DocsReaderWorker",
    "DocsFallbackWorker",
    "AdaptiveInterviewerWorker",
    "InterviewDefaultsWorker",
    "ReportDesignerWorker",
    "ModuleDrafterLeafWorker",
    "DraftCollectorWorker",
    "CoverageGaterWorker",
    "ValidatedDraftsWorker",
    "CrossValidatorWorker",
    "ReportFuserWorker",
    "CoverageReporterWorker",
    "KBIngesterWorker",
    "ALL_WORKERS",
]
