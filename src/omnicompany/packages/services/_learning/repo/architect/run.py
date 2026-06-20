# [OMNI] origin=claude-code domain=repo_architect/run.py ts=2026-04-09T00:00:00Z
# [OMNI] material_id="material:learning.repo.architect.pipeline_bindings_builder.py"
"""repo_architect run — bindings 与 pipeline 构造入口, 供 core/pipelines.py 引用。

router/pipeline 用延迟 import, 避免 CLI 启动拉重依赖。
"""

from __future__ import annotations

from typing import Any


def build_repo_architect_pipeline():
    from omnicompany.packages.services._learning.repo.architect.pipeline import build_pipeline
    return build_pipeline()


def build_repo_architect_bindings(input_dict: dict[str, Any] | None = None):
    from omnicompany.packages.services._learning.repo.architect.routers import (
        InputValidatorRouter,
        RepoAcquirerRouter,
        RepoIdentityAnchorRouter,
        ScaleSurveyorRouter,
        ModeSelectorRouter,
        DefaultModeRouter,
        ExternalResearcherRouter,
        ResearchDegradedRouter,
        DocsReaderRouter,
        DocsFallbackRouter,
        AdaptiveInterviewerRouter,
        InterviewDefaultsRouter,
        ReportDesignerRouter,
        ModuleDrafterLeafRouter,
        DraftCollectorRouter,
        CoverageGaterRouter,
        ValidatedDraftsRouter,
        CrossValidatorRouter,
        ReportFuserRouter,
        CoverageReporterRouter,
        KBIngesterRouter,
    )

    return {
        "input_validator": InputValidatorRouter(),
        "repo_acquirer": RepoAcquirerRouter(),
        "repo_identity_anchor": RepoIdentityAnchorRouter(),
        "scale_surveyor": ScaleSurveyorRouter(),
        "mode_selector": ModeSelectorRouter(),
        "default_mode": DefaultModeRouter(),
        "external_researcher": ExternalResearcherRouter(),
        "research_degraded": ResearchDegradedRouter(),
        "docs_reader": DocsReaderRouter(),
        "docs_fallback": DocsFallbackRouter(),
        "adaptive_interviewer": AdaptiveInterviewerRouter(),
        "interview_defaults": InterviewDefaultsRouter(),
        "report_designer": ReportDesignerRouter(),
        "module_drafter": ModuleDrafterLeafRouter(),
        "draft_collector": DraftCollectorRouter(),
        "coverage_gater": CoverageGaterRouter(),
        "validated_drafts_producer": ValidatedDraftsRouter(),
        "cross_validator": CrossValidatorRouter(),
        "report_fuser": ReportFuserRouter(),
        "coverage_reporter": CoverageReporterRouter(),
        "kb_ingester": KBIngesterRouter(),
    }
