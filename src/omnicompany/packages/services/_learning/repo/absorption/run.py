# [OMNI] origin=team_builder domain=services/repo_absorption/run ts=2026-04-25T00:00:00Z type=config
# [OMNI] material_id="material:learning.repo.absorption.pipeline_bindings_builder.py"
"""repo_absorption Team · build_bindings (team_builder 自动产出)."""
from __future__ import annotations

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.format import create_builtin_registry

from .formats import register_formats  # 相对 import · 支持 tmp smoke + 正式部署两场景

from .workers.repo_scanner import RepoScannerWorker
from .workers.module_selector import ModuleSelectorWorker
from .workers.source_reader import SourceReaderWorker
from .workers.pattern_extractor import PatternExtractorWorker
from .workers.report_assembler import ReportAssemblerWorker


def build_bindings(input_dict: dict | None = None) -> dict[str, Worker]:
    """构建 repo_absorption 节点绑定."""
    registry = create_builtin_registry()
    register_formats(registry)
    return {
        "RepoScannerWorker": RepoScannerWorker(),
        "ModuleSelectorWorker": ModuleSelectorWorker(),
        "SourceReaderWorker": SourceReaderWorker(),
        "PatternExtractorWorker": PatternExtractorWorker(),
        "ReportAssemblerWorker": ReportAssemblerWorker(),
    }
