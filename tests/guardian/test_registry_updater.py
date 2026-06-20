# [OMNI] origin=claude-code domain=omnicompany/guardian ts=2026-04-18T00:00:00Z
"""registry_updater.py 单元测试 — 验证去重 / 累计 / ARCH-CHANGES 写入。"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from omnicompany.packages.services._core.guardian.registry_updater import (  # noqa: E402
    append_violations_to_registry,
    append_violation_found_events,
    sync_patrol_result_to_registry,
    _next_id,
    _parse_row,
    _find_active_violations_table,
)


_REGISTRY_TEMPLATE = """<!-- [OMNI] origin=test domain=test ts=2026-04-18T00:00:00Z -->

# REGISTRY

## §活跃违规（Guardian / OMNI 规则产出）

| ID | 规则ID | 路径/目标 | 级别 | 首现 | 持续扫描数 | 状态 |
|---|---|---|---|---|---|---|
| D-001 | OMNI-007 | src/foo.md | MEDIUM | 2026-04-18 | 1 | open |
| D-002 | OVERSEER | 手工条目 | HIGH | 2026-04-10 | — | open |

---

## §已解决

| ID | 类型 | 解决日期 | 解决方式 |
|---|---|---|---|
"""


class TestParsing:
    def test_parse_row_valid(self):
        row = _parse_row("| D-001 | OMNI-007 | src/foo.md | MEDIUM | 2026-04-18 | 1 | open |")
        assert row["id"] == "D-001"
        assert row["rule_id"] == "OMNI-007"
        assert row["scan_count"] == "1"

    def test_parse_row_invalid(self):
        assert _parse_row("not a table row") is None
        assert _parse_row("| only | three | cells |") is None

    def test_next_id(self):
        assert _next_id([]) == "D-001"
        assert _next_id(["D-001", "D-002"]) == "D-003"
        assert _next_id(["D-001", "D-010", "D-003"]) == "D-011"
        assert _next_id(["OVERSEER", "D-005"]) == "D-006"


class TestTableDetection:
    def test_find_active_violations_table(self, tmp_path):
        lines = _REGISTRY_TEMPLATE.splitlines()
        span = _find_active_violations_table(lines)
        assert span is not None
        start, end = span
        # 表头应该是含 "| ID |" 那行
        assert lines[start].startswith("| ID |")
        # end 后第一行应该是空行或 ---
        # 数据行就是 D-001 + D-002 两行
        assert end - start == 4  # 表头+分隔+2数据


class TestAppendViolations:
    def _setup(self, tmp_path):
        registry = tmp_path / "docs" / "tech_debt" / "REGISTRY.md"
        registry.parent.mkdir(parents=True)
        registry.write_text(_REGISTRY_TEMPLATE, encoding="utf-8")
        return tmp_path

    def test_new_violation_appended(self, tmp_path):
        root = self._setup(tmp_path)
        violations = [
            {"rule_id": "OMNI-015", "path": "scratch_x.log", "severity": "HIGH"},
        ]
        result = append_violations_to_registry(violations, root)
        assert result["added"] == 1
        assert result["bumped"] == 0
        content = (root / "docs/tech_debt/REGISTRY.md").read_text(encoding="utf-8")
        assert "D-003" in content
        assert "OMNI-015" in content
        assert "scratch_x.log" in content

    def test_duplicate_bumps_scan_count(self, tmp_path):
        root = self._setup(tmp_path)
        violations = [
            {"rule_id": "OMNI-007", "path": "src/foo.md", "severity": "MEDIUM"},
        ]
        result = append_violations_to_registry(violations, root)
        assert result["added"] == 0
        assert result["bumped"] == 1
        content = (root / "docs/tech_debt/REGISTRY.md").read_text(encoding="utf-8")
        # D-001 持续扫描数从 1 → 2
        assert "| D-001 | OMNI-007 | src/foo.md | MEDIUM | 2026-04-18 | 2 | open |" in content

    def test_non_omni_rules_skipped(self, tmp_path):
        root = self._setup(tmp_path)
        violations = [
            {"rule_id": "CUSTOM-123", "path": "x.py", "severity": "HIGH"},
            {"rule_id": "OVERSEER", "path": "y", "severity": "HIGH"},
        ]
        result = append_violations_to_registry(violations, root)
        assert result["added"] == 0
        assert result["skipped"] == 2

    def test_manually_added_OVERSEER_row_preserved(self, tmp_path):
        root = self._setup(tmp_path)
        violations = [
            {"rule_id": "OMNI-007", "path": "src/new.md", "severity": "MEDIUM"},
        ]
        append_violations_to_registry(violations, root)
        content = (root / "docs/tech_debt/REGISTRY.md").read_text(encoding="utf-8")
        # OVERSEER 手工条目不应被动
        assert "| D-002 | OVERSEER | 手工条目" in content

    def test_mixed_new_and_duplicate(self, tmp_path):
        root = self._setup(tmp_path)
        violations = [
            {"rule_id": "OMNI-007", "path": "src/foo.md", "severity": "MEDIUM"},    # bump
            {"rule_id": "OMNI-015", "path": "new_file.log", "severity": "HIGH"},   # new
            {"rule_id": "OMNI-007", "path": "src/foo.md", "severity": "MEDIUM"},    # bump again (same scan)
        ]
        result = append_violations_to_registry(violations, root)
        assert result["added"] == 1
        assert result["bumped"] == 2
        content = (root / "docs/tech_debt/REGISTRY.md").read_text(encoding="utf-8")
        assert "| D-001 | OMNI-007 | src/foo.md | MEDIUM | 2026-04-18 | 3 | open |" in content

    def test_empty_violations(self, tmp_path):
        root = self._setup(tmp_path)
        original = (root / "docs/tech_debt/REGISTRY.md").read_text(encoding="utf-8")
        result = append_violations_to_registry([], root)
        assert result["added"] == 0
        assert result["bumped"] == 0
        # 内容不变
        assert (root / "docs/tech_debt/REGISTRY.md").read_text(encoding="utf-8") == original

    def test_missing_registry_graceful(self, tmp_path):
        result = append_violations_to_registry([{"rule_id": "OMNI-007", "path": "x"}], tmp_path)
        assert result["added"] == 0
        assert result["skipped"] == 1


class TestArchChangesEvents:
    def test_appends_jsonl_lines(self, tmp_path):
        new_rows = [
            {"id": "D-003", "rule_id": "OMNI-015", "path": "scratch.log", "severity": "HIGH"},
            {"id": "D-004", "rule_id": "OMNI-007", "path": "src/new.md", "severity": "MEDIUM"},
        ]
        count = append_violation_found_events(new_rows, tmp_path)
        assert count == 2
        arch_path = tmp_path / "docs" / "ARCH-CHANGES.jsonl"
        assert arch_path.exists()
        lines = arch_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        events = [json.loads(line) for line in lines]
        assert events[0]["event_type"] == "violation-found"
        assert events[0]["initiator"] == "guardian"
        assert "D-003" in events[0]["change"]
        assert events[0]["change_id"] != events[1]["change_id"]

    def test_empty_rows_no_write(self, tmp_path):
        count = append_violation_found_events([], tmp_path)
        assert count == 0
        arch_path = tmp_path / "docs" / "ARCH-CHANGES.jsonl"
        assert not arch_path.exists()

    def test_change_id_increments_within_day(self, tmp_path):
        arch_path = tmp_path / "docs" / "ARCH-CHANGES.jsonl"
        arch_path.parent.mkdir(parents=True)
        # 预置同日的 5 条事件
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pre_lines = []
        for i in range(1, 6):
            pre_lines.append(json.dumps({
                "change_id": f"ARCH-{today}-{i:03d}",
                "ts": "2026-04-18T00:00:00+00:00",
                "initiator": "human",
                "change": f"pre-{i}",
            }))
        arch_path.write_text("\n".join(pre_lines) + "\n", encoding="utf-8")

        # 再追加 2 条 → 应该是 006/007
        append_violation_found_events(
            [{"id": "D-100", "rule_id": "OMNI-007", "path": "x", "severity": "LOW"}],
            tmp_path,
        )
        content = arch_path.read_text(encoding="utf-8").strip().splitlines()
        last = json.loads(content[-1])
        assert last["change_id"] == f"ARCH-{today}-006"


class TestE2EPatrolResult:
    def _setup(self, tmp_path):
        registry = tmp_path / "docs" / "tech_debt" / "REGISTRY.md"
        registry.parent.mkdir(parents=True)
        registry.write_text(_REGISTRY_TEMPLATE, encoding="utf-8")
        return tmp_path

    def test_sync_adds_both_registry_and_arch(self, tmp_path):
        root = self._setup(tmp_path)
        fake_result = {
            "violations": [
                {"rule_id": "OMNI-015", "path": "scratch.log", "severity": "HIGH"},
                {"rule_id": "OMNI-007", "path": "src/foo.md", "severity": "MEDIUM"},  # dup
            ],
        }
        sync = sync_patrol_result_to_registry(fake_result, root)
        assert sync["added"] == 1
        assert sync["bumped"] == 1
        assert sync["arch_events"] == 1  # 只有 added 的才产 event

    def test_sync_handles_empty(self, tmp_path):
        root = self._setup(tmp_path)
        sync = sync_patrol_result_to_registry({"violations": []}, root)
        assert sync["added"] == 0
        assert sync["arch_events"] == 0

    def test_sync_swallows_errors(self, tmp_path):
        # 不 setup REGISTRY 文件，同步应不抛异常
        sync = sync_patrol_result_to_registry(
            {"violations": [{"rule_id": "OMNI-007", "path": "x"}]},
            tmp_path,
        )
        assert sync["added"] == 0
