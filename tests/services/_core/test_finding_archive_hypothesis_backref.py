# [OMNI] origin=ai-ide domain=tests/services/_core ts=2026-05-07T09:00:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest FindingArchive.find_findings_referencing_hypothesis — 反向查 applied_hypotheses 含某 hid 的全部 finding_id"
# [OMNI] why="V1 留议第四项 — FindingArchive 接通自动填 related_finding_ids. 修 hypothesis_v1_upgrade_report 7.4 第一项"
# [OMNI] tags=test,pytest,finding-archive,hypothesis-backref,V1
# [OMNI] material_id="material:tests.services.core.test_finding_archive_hypothesis_backref.py"
"""pytest FindingArchive.find_findings_referencing_hypothesis (反向查).

测 case:
- 边界: archive 不存在 / 空 hid / 无匹 finding
- 真用: 多 finding 引同假设 → 返多 finding_id (按 ts 升序)
- 跨 entity_kind: 不同 kind 下 finding 都查到
- 去重: 同 finding_id 不重复返
"""
from __future__ import annotations

import pytest

from omnicompany.packages.services._core.registry.finding_archive import FindingArchive


@pytest.fixture
def archive(tmp_path):
    return FindingArchive(tmp_path / "findings_archive")


def _mk_finding(finding_id, entity_kind, entity_id, applied_hypotheses, ts):
    return {
        "finding_id": finding_id,
        "entity_kind": entity_kind,
        "entity_id": entity_id,
        "finding_kind": "hypothesis",
        "evidence": "x",
        "commentary": "y",
        "concern": "z",
        "applied_hypotheses": applied_hypotheses,
        "ts": ts,
    }


# ── 边界 ──

def test_find_in_nonexistent_archive_returns_empty(tmp_path):
    """archive_dir 不存在返空 list."""
    a = FindingArchive(tmp_path / "no_such_dir")
    assert a.find_findings_referencing_hypothesis("H-001") == []


def test_find_with_empty_hid_returns_empty(archive):
    """空 hid 返空 list."""
    archive.append_finding(_mk_finding("F-001", "worker", "w1", ["H-001"], "2026-05-07T01:00:00Z"))
    assert archive.find_findings_referencing_hypothesis("") == []
    assert archive.find_findings_referencing_hypothesis(None) == []


def test_find_no_match_returns_empty(archive):
    archive.append_finding(_mk_finding("F-001", "worker", "w1", ["H-002"], "2026-05-07T01:00:00Z"))
    assert archive.find_findings_referencing_hypothesis("H-001") == []


# ── 真用 ──

def test_find_returns_finding_ids_referencing_hypothesis(archive):
    """多 finding 引同假设 → 返多 finding_id."""
    archive.append_finding(_mk_finding("F-001", "worker", "w1", ["H-target"], "2026-05-07T01:00:00Z"))
    archive.append_finding(_mk_finding("F-002", "worker", "w1", ["H-other"], "2026-05-07T02:00:00Z"))
    archive.append_finding(_mk_finding("F-003", "worker", "w2", ["H-target", "H-other"], "2026-05-07T03:00:00Z"))
    fids = archive.find_findings_referencing_hypothesis("H-target")
    assert "F-001" in fids
    assert "F-003" in fids
    assert "F-002" not in fids
    assert len(fids) == 2


def test_find_returns_in_ts_ascending_order(archive):
    """返按 ts 升序."""
    archive.append_finding(_mk_finding("F-late", "worker", "w1", ["H-x"], "2026-05-07T05:00:00Z"))
    archive.append_finding(_mk_finding("F-early", "worker", "w2", ["H-x"], "2026-05-07T01:00:00Z"))
    archive.append_finding(_mk_finding("F-mid", "worker", "w3", ["H-x"], "2026-05-07T03:00:00Z"))
    fids = archive.find_findings_referencing_hypothesis("H-x")
    assert fids == ["F-early", "F-mid", "F-late"]


def test_find_across_entity_kinds(archive):
    """不同 entity_kind 下 finding 都查到."""
    archive.append_finding(_mk_finding("F-w", "worker", "w1", ["H-cross"], "2026-05-07T01:00:00Z"))
    archive.append_finding(_mk_finding("F-m", "material", "m1", ["H-cross"], "2026-05-07T02:00:00Z"))
    archive.append_finding(_mk_finding("F-t", "team", "t1", ["H-cross"], "2026-05-07T03:00:00Z"))
    fids = archive.find_findings_referencing_hypothesis("H-cross")
    assert set(fids) == {"F-w", "F-m", "F-t"}


def test_find_dedupes_finding_ids(archive):
    """同 finding_id 不重复 — append 同 finding_id 两次也返 1 个 (按 finding_id dedupe)."""
    archive.append_finding(_mk_finding("F-dup", "worker", "w1", ["H-y"], "2026-05-07T01:00:00Z"))
    archive.append_finding(_mk_finding("F-dup", "worker", "w1", ["H-y"], "2026-05-07T02:00:00Z"))
    fids = archive.find_findings_referencing_hypothesis("H-y")
    assert fids == ["F-dup"]
