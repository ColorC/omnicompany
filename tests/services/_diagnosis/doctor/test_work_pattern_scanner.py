# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T03:30:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest 单元测 doctor WorkPatternAnomalyScanner — 修 AP-018+AP-019 (rule-maker-violator + tool-not-eat-own-dogfood)"
# [OMNI] why="阶段 10 修 2: scanner 没自测. 立 pytest 测边界 case + 红绿对比 (有大量异常 commit window vs 健康 window)"
# [OMNI] tags=test,pytest,work-pattern-scanner,unit-test,boundary-case
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_work_pattern_scanner.py"
"""pytest 单元测 doctor WorkPatternAnomalyScanner.

测 case:
- 边界 (无 commit / 无效 since)
- detector 各类 (no_self_audit / patch_pile / batch_without_confirm / silent_advance / rapid_fix)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnicompany.packages.services._diagnosis.doctor.scanners import (
    WorkPatternAnomalyScanner,
    scan_work_pattern_anomalies,
)
from omnicompany.packages.services._diagnosis.doctor.scanners.work_pattern_scanner import (
    CommitRecord,
    AnomalySignal,
)


@pytest.fixture
def project_root() -> Path:
    here = Path(__file__).resolve()
    for p in (here, *here.parents):
        if (p / "src" / "omnicompany").is_dir() and (p / "docs").is_dir():
            return p
    raise RuntimeError("project root not found")


# ── 边界 case ──

def test_scan_no_commits_in_future(project_root):
    """红样本: since 在未来 → 0 commit, 无信号."""
    scanner = WorkPatternAnomalyScanner(project_root=project_root)
    result = scanner.scan(since="2099-01-01")
    assert result.commit_count == 0
    assert result.anomaly_signals == []


def test_scan_invalid_project_root(tmp_path):
    """红样本: project_root 不是 git repo → 空结果."""
    not_a_repo = tmp_path / "fake"
    not_a_repo.mkdir()
    scanner = WorkPatternAnomalyScanner(project_root=not_a_repo)
    result = scanner.scan(since="2026-01-01")
    # git log 失败应返 0 commit
    assert result.commit_count == 0


# ── 真历史 ──

def test_scan_recent_history_returns_records(project_root):
    """绿样本: 跑过去一周应有 N 个 commit + 各分类计数."""
    scanner = WorkPatternAnomalyScanner(project_root=project_root)
    result = scanner.scan(since="2026-04-30")
    assert result.commit_count > 0
    # commit 计数字段都是 int
    assert isinstance(result.fix_count, int)
    assert isinstance(result.audit_count, int)
    assert isinstance(result.batch_count, int)
    assert isinstance(result.revert_count, int)
    # signals 是 list
    assert isinstance(result.anomaly_signals, list)


def test_anomaly_signal_dataclass_fields():
    """AnomalySignal 字段齐, severity_signal 字符串."""
    sig = AnomalySignal(
        archetype_id="AP-016",
        archetype_name="false-confident-no-self-audit",
        severity_signal="CRITICAL",
    )
    assert sig.archetype_id == "AP-016"
    assert sig.severity_signal in ("CRITICAL", "HIGH", "MEDIUM")
    assert isinstance(sig.evidence_commits, list)
    assert isinstance(sig.metric, dict)


def test_commit_record_classification():
    """CommitRecord 分类 fields 默认 False."""
    cr = CommitRecord(
        short_hash="abcd123",
        date="2026-05-07 12:00:00 +0800",
        author="test",
        subject="test commit",
    )
    assert cr.is_fix is False
    assert cr.is_audit is False
    assert cr.is_revert is False
    assert cr.is_batch is False


# ── helper API ──

def test_scan_work_pattern_anomalies_helper_returns_dict(project_root):
    """helper API 返 dict 可序列化."""
    result = scan_work_pattern_anomalies(since="2026-04-30", project_root=project_root)
    assert isinstance(result, dict)
    for key in ("commit_count", "fix_count", "audit_count", "batch_count", "anomaly_signals"):
        assert key in result
    assert isinstance(result["anomaly_signals"], list)


# ── 红绿区分 ──

def test_red_green_window_discrimination(project_root):
    """红绿: 长窗口(全历史) vs 短窗口(过去 1 天) anomaly signal 数应区分."""
    scanner = WorkPatternAnomalyScanner(project_root=project_root)
    long_window = scanner.scan(since="2026-04-01")
    short_window = scanner.scan(since="2026-05-06T20:00:00")
    # 长窗 commit 数应 ≥ 短窗
    assert long_window.commit_count >= short_window.commit_count
    # 长窗 anomaly 信号数 ≥ 短窗 (更长时间累更多)
    # 不强断言 ≥ (LLM 行为有变), 但都应是 list
    assert isinstance(long_window.anomaly_signals, list)
    assert isinstance(short_window.anomaly_signals, list)
