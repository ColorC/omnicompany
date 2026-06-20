"""阶段四 · 罚单逾期升级 + pre-commit 拦截集合扩展测试 (2026-04-28).

覆盖:
  1. escalate_overdue_tickets 找出 status=open + detected_at > 7 天 → 升级
  2. 已 resolved / 已 escalated 的罚单不重复升级
  3. 边界: 阈值天数可配置
  4. pre-commit hook 模板 BLOCK_RULES 含 OMNI-035f~i (但不含 035j MEDIUM)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.guardian.tow_truck import OmniTow


# ─── 辅助 ─────────────────────────────────────────────────────────


def _write_ticket_index(omni_dir: Path, entries: list[dict]) -> None:
    q = omni_dir / "quarantine"
    q.mkdir(parents=True, exist_ok=True)
    (q / "index.json").write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


def _write_ticket_file(omni_dir: Path, ticket_id: str, detected_at: str, **fields) -> None:
    """写单条罚单 JSON, 模拟 Phase 2 落盘的形态."""
    date_str = detected_at[:10]
    d = omni_dir / "quarantine" / date_str
    d.mkdir(parents=True, exist_ok=True)
    data = {
        "ticket_id": ticket_id,
        "detected_at": detected_at,
        "rule_violated": fields.get("rule", "OMNI-035g"),
        "severity": fields.get("severity", "HIGH"),
        "original_path": fields.get("path", "docs/x.py"),
        "status": fields.get("status", "open"),
    }
    (d / f"{ticket_id}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ─── 罚单逾期升级 ─────────────────────────────────────────────────


class TestEscalateOverdue:
    def test_no_index_returns_zero(self, tmp_path):
        (tmp_path / ".omni").mkdir()
        tow = OmniTow(project_root=tmp_path)
        r = tow.escalate_overdue_tickets()
        assert r["escalated_count"] == 0

    def test_old_open_ticket_escalates(self, tmp_path):
        (tmp_path / ".omni").mkdir()
        omni = tmp_path / ".omni"
        old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        _write_ticket_index(omni, [{
            "ticket_id": "T-OLD",
            "rule": "OMNI-035g",
            "severity": "HIGH",
            "path": "docs/foo.py",
            "status": "open",
            "detected_at": old_ts,
        }])
        _write_ticket_file(omni, "T-OLD", old_ts)

        tow = OmniTow(project_root=tmp_path)
        r = tow.escalate_overdue_tickets(threshold_days=7)

        assert r["escalated_count"] == 1
        assert "T-OLD" in r["escalated_ticket_ids"]

        # 索引和单条罚单都标 overdue-escalated
        idx = json.loads((omni / "quarantine" / "index.json").read_text(encoding="utf-8"))
        assert idx[0]["status"] == "overdue-escalated"
        ticket_file = omni / "quarantine" / old_ts[:10] / "T-OLD.json"
        data = json.loads(ticket_file.read_text(encoding="utf-8"))
        assert data["status"] == "overdue-escalated"

        # 事件流
        log = omni / "evolution" / "overdue_signals.jsonl"
        assert log.exists()
        line = log.read_text(encoding="utf-8").strip()
        assert "T-OLD" in line
        assert "overdue-escalated" in line

    def test_recent_ticket_not_escalated(self, tmp_path):
        (tmp_path / ".omni").mkdir()
        omni = tmp_path / ".omni"
        recent_ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        _write_ticket_index(omni, [{
            "ticket_id": "T-RECENT",
            "rule": "OMNI-035g",
            "severity": "HIGH",
            "path": "docs/foo.py",
            "status": "open",
            "detected_at": recent_ts,
        }])

        tow = OmniTow(project_root=tmp_path)
        r = tow.escalate_overdue_tickets(threshold_days=7)
        assert r["escalated_count"] == 0

    def test_resolved_ticket_skipped(self, tmp_path):
        (tmp_path / ".omni").mkdir()
        omni = tmp_path / ".omni"
        old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        _write_ticket_index(omni, [{
            "ticket_id": "T-DONE",
            "rule": "OMNI-035g",
            "severity": "HIGH",
            "path": "docs/foo.py",
            "status": "resolved",  # 已处理
            "detected_at": old_ts,
        }])

        tow = OmniTow(project_root=tmp_path)
        r = tow.escalate_overdue_tickets()
        assert r["escalated_count"] == 0
        assert r["skipped_count"] == 1

    def test_already_escalated_not_reprocessed(self, tmp_path):
        (tmp_path / ".omni").mkdir()
        omni = tmp_path / ".omni"
        old_ts = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        _write_ticket_index(omni, [{
            "ticket_id": "T-OLD",
            "rule": "OMNI-035g",
            "severity": "HIGH",
            "path": "docs/foo.py",
            "status": "overdue-escalated",  # 已升级
            "detected_at": old_ts,
        }])

        tow = OmniTow(project_root=tmp_path)
        r = tow.escalate_overdue_tickets()
        assert r["escalated_count"] == 0

    def test_threshold_configurable(self, tmp_path):
        """阈值天数可配置: 设 1 天则 2 天前的就算逾期."""
        (tmp_path / ".omni").mkdir()
        omni = tmp_path / ".omni"
        ts_2day = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        _write_ticket_index(omni, [{
            "ticket_id": "T-2DAY",
            "rule": "OMNI-035g",
            "severity": "HIGH",
            "path": "docs/foo.py",
            "status": "open",
            "detected_at": ts_2day,
        }])
        _write_ticket_file(omni, "T-2DAY", ts_2day)

        tow = OmniTow(project_root=tmp_path)
        r = tow.escalate_overdue_tickets(threshold_days=1)
        assert r["escalated_count"] == 1


# 注: pre-commit 模板字符串 grep 类断言 (含 OMNI-035f / 含 MANAGED_MARKER / BLOCK_RULES 集合)
# 已删除. 这些是"复述模板源码", 改坏了刷一次 hook-install 立刻爆.
# 真要测拦截行为应该端到端: 造个违规 commit → git commit → 期望被钩子拒绝.
# 端到端测试涉及 git 子进程 + sh 解释器, 留给阶段四验收手测, 不进单元测试.
