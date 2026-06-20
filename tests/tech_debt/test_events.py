# [OMNI] origin=claude-code domain=services/tech_debt ts=2026-04-18T00:00:00Z
"""tech_debt.events 单元测试 + debt scan CLI smoke。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from omnicompany.packages.services.tech_debt.events import (  # noqa: E402
    append_event,
    read_events,
    KNOWN_EVENT_TYPES,
    ARCHEvent,
)


# ═══ append_event ════════════════════════════════════════════════

class TestAppendEvent:
    def test_first_event_id_001(self, tmp_path):
        ev = append_event(
            tmp_path,
            event_type="scan-started",
            initiator="tech_debt",
            drawer="services/tech_debt",
            change="test",
        )
        assert ev is not None
        assert ev.change_id.endswith("-001")
        assert ev.event_type == "scan-started"
        # ARCH-CHANGES.jsonl 实际写入
        arch = tmp_path / "docs" / "ARCH-CHANGES.jsonl"
        assert arch.exists()
        events = [json.loads(ln) for ln in arch.read_text(encoding="utf-8").strip().splitlines()]
        assert len(events) == 1
        assert events[0]["change_id"] == ev.change_id

    def test_id_auto_increments(self, tmp_path):
        ev1 = append_event(tmp_path, event_type="scan-started", initiator="tech_debt", change="1")
        ev2 = append_event(tmp_path, event_type="scan-completed", initiator="tech_debt", change="2")
        assert ev1.change_id.endswith("-001")
        assert ev2.change_id.endswith("-002")

    def test_payload_written_when_nonempty(self, tmp_path):
        ev = append_event(
            tmp_path, event_type="scan-started", initiator="tech_debt",
            change="with payload",
            payload={"mode": "fast", "limit": 20},
        )
        arch = tmp_path / "docs" / "ARCH-CHANGES.jsonl"
        events = [json.loads(ln) for ln in arch.read_text(encoding="utf-8").strip().splitlines()]
        assert events[0]["payload"] == {"mode": "fast", "limit": 20}

    def test_empty_payload_omitted(self, tmp_path):
        append_event(tmp_path, event_type="scan-started", initiator="tech_debt", change="x")
        arch = tmp_path / "docs" / "ARCH-CHANGES.jsonl"
        events = [json.loads(ln) for ln in arch.read_text(encoding="utf-8").strip().splitlines()]
        assert "payload" not in events[0]

    def test_respects_existing_same_day(self, tmp_path):
        # 预置同日 5 条
        (tmp_path / "docs").mkdir()
        arch = tmp_path / "docs" / "ARCH-CHANGES.jsonl"
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pre = "\n".join(
            json.dumps({"change_id": f"ARCH-{today}-{i:03d}",
                        "ts": "x", "initiator": "human", "event_type": "violation-found"})
            for i in range(1, 6)
        )
        arch.write_text(pre + "\n", encoding="utf-8")
        ev = append_event(tmp_path, event_type="scan-started", initiator="tech_debt", change="x")
        assert ev.change_id.endswith("-006")

    def test_known_types_covered(self):
        # 自查：新增事件类型时别忘了在这里更新 KNOWN_EVENT_TYPES
        assert "violation-found" in KNOWN_EVENT_TYPES
        assert "violation-resolved" in KNOWN_EVENT_TYPES
        assert "finding-generated" in KNOWN_EVENT_TYPES
        assert "scan-started" in KNOWN_EVENT_TYPES
        assert "scan-completed" in KNOWN_EVENT_TYPES


class TestReadEvents:
    def _setup(self, tmp_path) -> Path:
        append_event(tmp_path, event_type="scan-started", initiator="tech_debt", change="s1")
        append_event(tmp_path, event_type="scan-completed", initiator="tech_debt", change="e1")
        append_event(tmp_path, event_type="scan-started", initiator="tech_debt", change="s2")
        return tmp_path

    def test_read_all(self, tmp_path):
        root = self._setup(tmp_path)
        all_ev = read_events(root)
        assert len(all_ev) == 3

    def test_filter_by_type(self, tmp_path):
        root = self._setup(tmp_path)
        started = read_events(root, event_type="scan-started")
        assert len(started) == 2
        assert all(e["event_type"] == "scan-started" for e in started)

    def test_empty_file(self, tmp_path):
        assert read_events(tmp_path) == []


class TestARCHEventSerialization:
    def test_to_jsonl_line_is_valid_json(self):
        ev = ARCHEvent(
            change_id="ARCH-2026-04-18-001",
            ts="2026-04-18T00:00:00+00:00",
            initiator="tech_debt",
            event_type="scan-started",
            drawer="services/tech_debt",
            change="x",
        )
        line = ev.to_jsonl_line()
        parsed = json.loads(line)
        assert parsed["change_id"] == "ARCH-2026-04-18-001"
        assert "payload" not in parsed  # 空 payload 被省略


# ═══ omni debt scan CLI smoke =====================================


def _make_registry(root: Path, extra: str = "") -> None:
    """准备一个最小可工作的 REGISTRY.md（供 CLI smoke 用）。"""
    d = root / "docs" / "tech_debt"
    d.mkdir(parents=True, exist_ok=True)
    (d / "REGISTRY.md").write_text(
        "# REGISTRY\n\n"
        "## §活跃违规（...）\n\n"
        "| ID | 规则ID | 路径/目标 | 级别 | 首现 | 持续扫描数 | 状态 |\n"
        "|---|---|---|---|---|---|---|\n\n"
        "---\n\n"
        "## §语义合规待审（...）\n\n"
        "| ID | 标准来源 | 目标 | 疑似违规描述 | 信心 | 处置 | 状态 |\n"
        "|---|---|---|---|---|---|---|\n\n"
        "---\n\n"
        "## §DESIGN.md 漂移\n\n"
        "| ID | DESIGN.md | 最后代码变更 | 最后文档更新 | 漂移天数 | 状态 |\n"
        "|---|---|---|---|---|---|\n\n"
        "---\n\n"
        "## §计划回流欠债\n\n"
        "| ID | 归档 plan | 目标 DESIGN.md | 状态 |\n"
        "|---|---|---|---|\n\n"
        "---\n\n"
        "## §能力缺口\n\n"
        "| Gap | 一句话描述 | 优先级 | 状态 |\n"
        "|---|---|---|---|\n\n"
        "---\n\n"
        "## §已解决\n\n"
        "| ID | 类型 | 解决日期 | 解决方式 |\n"
        "|---|---|---|---|\n" + extra,
        encoding="utf-8",
    )


class TestDebtScanCLI:
    def test_scan_dry_run_fast(self, tmp_path):
        """dry-run + --fast 不应做任何真实扫描，只写 scan-started/completed 事件。"""
        from click.testing import CliRunner
        from omnicompany.cli.commands.debt import cmd_debt

        _make_registry(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cmd_debt, ["scan", "--dry-run", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output

        events = read_events(tmp_path)
        types = [e["event_type"] for e in events]
        assert "scan-started" in types
        assert "scan-completed" in types
        # dry_run payload 对齐
        started = next(e for e in events if e["event_type"] == "scan-started")
        assert started["payload"]["dry_run"] is True
        assert started["payload"]["mode"] == "fast"

    def test_scan_fast_full_conflict_exits_2(self, tmp_path):
        from click.testing import CliRunner
        from omnicompany.cli.commands.debt import cmd_debt
        _make_registry(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cmd_debt,
            ["scan", "--fast", "--full", "--root", str(tmp_path)],
        )
        assert result.exit_code == 2

    def test_scan_dry_full_requires_standards_index(self, tmp_path):
        """dry-run --full 会调 ArtifactSelector，需要 standards-index.yaml。
        没准备时应 FAIL 在 semantic 节，但不应该 crash 整个命令。"""
        from click.testing import CliRunner
        from omnicompany.cli.commands.debt import cmd_debt
        _make_registry(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cmd_debt,
            ["scan", "--full", "--dry-run", "--root", str(tmp_path)],
        )
        # 即便 semantic 部分 FAIL，整体命令应 exit 0 + summary 里记录 error
        assert result.exit_code == 0
        events = read_events(tmp_path)
        assert any(e["event_type"] == "scan-completed" for e in events)
