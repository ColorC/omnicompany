# [OMNI] origin=claude-code domain=services/_diagnosis/project_audit ts=2026-06-20T00:00:00Z type=team status=active
# [OMNI] summary="project_audit team 群 · build_bindings(node_id → Worker 实例):主管线 / 发现 / 完整性。"
# [OMNI] material_id="material:services._diagnosis.project_audit.run"
"""project_audit Team 群 · 节点绑定。"""
from __future__ import annotations

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.format import create_builtin_registry

from .formats import register_formats
from .workers.tree_enumerator import TreeEnumeratorWorker
from .workers.prompt_harvester import PromptHarvester
from .workers.code_reader import CodeReader
from .workers.plan_completion_auditor import PlanCompletionAuditorWorker
from .workers.report_validator import ReportValidatorWorker
from .workers.project_discoverer import ProjectDiscoverer
from .workers.completeness_critic import CompletenessCritic


def _registry():
    registry = create_builtin_registry()
    register_formats(registry)
    return registry


def build_bindings(input_dict: dict | None = None) -> dict[str, Worker]:
    """主管线节点绑定。"""
    _registry()
    return {
        "TreeEnumeratorWorker": TreeEnumeratorWorker(),
        "PromptHarvester": PromptHarvester(),
        "CodeReader": CodeReader(),
        "PlanCompletionAuditorWorker": PlanCompletionAuditorWorker(),
        "ReportValidatorWorker": ReportValidatorWorker(),
    }


def build_discovery_bindings(input_dict: dict | None = None) -> dict[str, Worker]:
    _registry()
    return {"ProjectDiscoverer": ProjectDiscoverer()}


def build_completeness_bindings(input_dict: dict | None = None) -> dict[str, Worker]:
    _registry()
    return {"CompletenessCritic": CompletenessCritic()}
