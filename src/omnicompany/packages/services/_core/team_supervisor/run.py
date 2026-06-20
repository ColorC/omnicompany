# [OMNI] origin=claude-code domain=services/team_supervisor/run ts=2026-04-26T00:00:00Z type=config
# [OMNI] material_id="material:core.team_supervisor.worker_bindings.builder.py"
"""team_supervisor Team · build_bindings."""
from __future__ import annotations

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.format import create_builtin_registry

from .formats import register_formats

from .workers.target_ingress import TargetIngressWorker
from .workers.product_form_analyzer import ProductFormAnalyzerWorker
from .workers.purpose_interpreter import PurposeInterpreterWorker
from .workers.health_criteria_designer import HealthCriteriaDesignerWorker
from .workers.hypothesis_generator import HypothesisGeneratorWorker
from .workers.test_executor import TestExecutorWorker
from .workers.health_report_assembler import HealthReportAssemblerWorker


def build_bindings(input_dict: dict | None = None) -> dict[str, Worker]:
    """构建 team_supervisor 节点绑定."""
    registry = create_builtin_registry()
    register_formats(registry)
    return {
        "TargetIngressWorker": TargetIngressWorker(),
        "ProductFormAnalyzerWorker": ProductFormAnalyzerWorker(),
        "PurposeInterpreterWorker": PurposeInterpreterWorker(),
        "HealthCriteriaDesignerWorker": HealthCriteriaDesignerWorker(),
        "HypothesisGeneratorWorker": HypothesisGeneratorWorker(),
        "TestExecutorWorker": TestExecutorWorker(),
        "HealthReportAssemblerWorker": HealthReportAssemblerWorker(),
    }
