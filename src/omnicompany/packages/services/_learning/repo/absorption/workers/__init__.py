# [OMNI] origin=team_builder domain=services/repo_absorption/workers/__init__ ts=2026-04-25T00:00:00Z type=config
# [OMNI] material_id="material:learning.repo.absorption.worker.package_exports.py"
"""repo_absorption Team · workers 子包导出."""
from __future__ import annotations

from omnicompany.packages.services._core.omnicompany import Worker

from .repo_scanner import RepoScannerWorker
from .module_selector import ModuleSelectorWorker
from .source_reader import SourceReaderWorker
from .pattern_extractor import PatternExtractorWorker
from .report_assembler import ReportAssemblerWorker

ALL_WORKERS: list[type[Worker]] = [RepoScannerWorker, ModuleSelectorWorker, SourceReaderWorker, PatternExtractorWorker, ReportAssemblerWorker]

__all__ = ["RepoScannerWorker", "ModuleSelectorWorker", "SourceReaderWorker", "PatternExtractorWorker", "ReportAssemblerWorker", "ALL_WORKERS"]
