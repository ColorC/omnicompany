# [OMNI] origin=claude-code domain=services/repo_architect ts=2026-04-20T00:00:00Z type=config
# [OMNI] material_id="material:learning.repo.architect.router_compatibility_shim.py"
"""repo_architect routers — 兼容垫片 (Phase D Diamond shortcut 2026-04-20).

业务实现已迁到 workers/ (Diamond shortcut 模式). 本文件保留旧名称以兼容调用方.
"""
from __future__ import annotations

from .workers import (
    InputValidatorWorker as InputValidatorRouter,
    RepoAcquirerWorker as RepoAcquirerRouter,
    RepoIdentityAnchorWorker as RepoIdentityAnchorRouter,
    ScaleSurveyorWorker as ScaleSurveyorRouter,
    ModeSelectorWorker as ModeSelectorRouter,
    DefaultModeWorker as DefaultModeRouter,
    RepoIntrospectionWorker as RepoIntrospectionRouter,
    ResearchDegradedWorker as ResearchDegradedRouter,
    DocsReaderWorker as DocsReaderRouter,
    DocsFallbackWorker as DocsFallbackRouter,
    AdaptiveInterviewerWorker as AdaptiveInterviewerRouter,
    InterviewDefaultsWorker as InterviewDefaultsRouter,
    ReportDesignerWorker as ReportDesignerRouter,
    ModuleDrafterLeafWorker as ModuleDrafterLeafRouter,
    DraftCollectorWorker as DraftCollectorRouter,
    CoverageGaterWorker as CoverageGaterRouter,
    ValidatedDraftsWorker as ValidatedDraftsRouter,
    CrossValidatorWorker as CrossValidatorRouter,
    ReportFuserWorker as ReportFuserRouter,
    CoverageReporterWorker as CoverageReporterRouter,
    KBIngesterWorker as KBIngesterRouter,
)

__all__ = [
    "InputValidatorRouter",
    "RepoAcquirerRouter",
    "RepoIdentityAnchorRouter",
    "ScaleSurveyorRouter",
    "ModeSelectorRouter",
    "DefaultModeRouter",
    "RepoIntrospectionRouter",
    "ResearchDegradedRouter",
    "DocsReaderRouter",
    "DocsFallbackRouter",
    "AdaptiveInterviewerRouter",
    "InterviewDefaultsRouter",
    "ReportDesignerRouter",
    "ModuleDrafterLeafRouter",
    "DraftCollectorRouter",
    "CoverageGaterRouter",
    "ValidatedDraftsRouter",
    "CrossValidatorRouter",
    "ReportFuserRouter",
    "CoverageReporterRouter",
    "KBIngesterRouter",
]
