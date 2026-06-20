# [OMNI] origin=claude-code domain=repo_architect/__init__.py ts=2026-04-09T00:00:00Z
# [OMNI] material_id="material:learning.repo.architect.package_exports.py"
"""omnicompany.packages.services._learning.repo.architect.

仓库架构深度分析管线 — 翻译自 yzddmr6/repo-analyzer SOTA Claude Code Skill。

18 节点 DAG 覆盖 16 Format 的完整链路:
  阶段 1: input_validator → repo_acquirer → scale_surveyor → mode_selector (+ default_mode)
  阶段 2: external_researcher / docs_reader / adaptive_interviewer (+ 3 fallback)
  阶段 3: report_designer
  阶段 4: module_scatter
  阶段 5: coverage_gater → validated_drafts → cross_validator
  阶段 6: report_fuser → coverage_reporter → kb_ingester (EMIT)

2026-04-09 人工补齐: workflow-factory 首次运行在 node_planner 阶段被 10k 硬截断,
只生成 5/16 Format + 11/18 节点。补齐本包作为可执行骨架, 并借此诊断修复 workflow-factory。
"""

from omnicompany.packages.services._learning.repo.architect.formats import (
    ALL_FORMATS,
    register_formats,
)
from omnicompany.packages.services._learning.repo.architect.pipeline import build_pipeline
from omnicompany.packages.services._learning.repo.architect.run import (
    build_repo_architect_bindings,
    build_repo_architect_pipeline,
)

__all__ = [
    "ALL_FORMATS",
    "register_formats",
    "build_pipeline",
    "build_repo_architect_pipeline",
    "build_repo_architect_bindings",
]
