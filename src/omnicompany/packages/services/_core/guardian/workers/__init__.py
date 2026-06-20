# [OMNI] origin=claude-code domain=omnicompany/guardian ts=2026-04-20T00:00:00Z type=config
# [OMNI] material_id="material:core.guardian.workers.package_aggregate.exports.py"
"""Guardian worker exports.

The active patrol chain is GitDiffScanWorker -> RuleEngineWorker. The former
audit/tow placeholder was retired because it advertised audit persistence and
tow delegation without performing either action.
"""
from __future__ import annotations

from .git_diff_scan_worker import GitDiffScanWorker
from .rule_engine_worker import RuleEngineWorker
from .fs_scanner_worker import FsScannerWorker
from .arch_auditor_worker import ArchAuditorWorker
from .hygiene_scan_worker import HygieneScanWorker
from .report_writer import GuardianReportWorker


ALL_WORKERS = [
    GitDiffScanWorker,
    RuleEngineWorker,
    FsScannerWorker,
    ArchAuditorWorker,
    HygieneScanWorker,
    GuardianReportWorker,
]


__all__ = [
    "GitDiffScanWorker",
    "RuleEngineWorker",
    "FsScannerWorker",
    "ArchAuditorWorker",
    "GuardianReportWorker",
    "HygieneScanWorker",
    "ALL_WORKERS",
]
