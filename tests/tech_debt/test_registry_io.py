# [OMNI] origin=claude-code domain=services/tech_debt ts=2026-04-18T00:00:00Z
"""tech_debt.registry_io 单元测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from omnicompany.packages.services.tech_debt.registry_io import (  # noqa: E402
    load_registry,
    list_rows,
    compute_stats,
    resolve_row,
    SECTION_SPECS,
)


_REGISTRY = """<!-- [OMNI] origin=test -->

# REGISTRY

## §活跃违规（Guardian / OMNI 规则产出）

| ID | 规则ID | 路径/目标 | 级别 | 首现 | 持续扫描数 | 状态 |
|---|---|---|---|---|---|---|
| D-001 | OMNI-007 | src/a.json | MEDIUM | 2026-04-18 | 1 | open |
| D-002 | OVERSEER | 手工条目 | HIGH | 2026-04-10 | — | open |
| D-003 | OMNI-030 | src/v1.md | HIGH | 2026-04-18 | 3 | open |

---

## §语义合规待审（SemanticAuditor 产出 / 人工识别）

| ID | 标准来源 | 目标 | 疑似违规描述 | 信心 | 处置 | 状态 |
|---|---|---|---|---|---|---|
| SA-001 | LLM-FIRST | src/r.py | 违规描述 | 0.95 | 迁移 | open |
| SA-002 | ROUTER | src/x.py | low confidence one | 0.5 | review | needs_human_review |

---

## §文档漂移（DESIGN.md / plan.md 未反映现状）

| ID | 类型 | 目标 | 最后代码/原始变更 | 最后文档更新 | 漂移天数 | 状态 |
|---|---|---|---|---|---|---|

---

## §计划回流欠债（archived plan → DESIGN.md 未写）

| ID | 归档 plan | 目标 DESIGN.md | 状态 |
|---|---|---|---|
| P-001 | `[2026-04-02]FOO` | `src/x/DESIGN.md` | pending |
| P-002 | `[2026-04-03]BAR` | `src/y/DESIGN.md` | pending |

---

## §能力缺口（docs/gaps/ 摘要）

| Gap | 一句话描述 | 优先级 | 状态 |
|---|---|---|---|
| G1 | 工具层鲁棒性 | P1 | 部分进展 |

---

## §已解决（最近 30 条）

| ID | 类型 | 解决日期 | 解决方式 |
|---|---|---|---|
"""


@pytest.fixture
def fake_root(tmp_path):
    d = tmp_path / "docs" / "tech_debt"
    d.mkdir(parents=True)
    (d / "REGISTRY.md").write_text(_REGISTRY, encoding="utf-8")
    return tmp_path


# ═══ load_registry ════════════════════════════════════════════

class TestLoad:
    def test_load_all_sections(self, fake_root):
        s = load_registry(fake_root)
        assert len(s.sections["activity"]) == 3
        assert len(s.sections["semantic_pending"]) == 2
        assert len(s.sections["doc_drift"]) == 0
        assert len(s.sections["plan_merge"]) == 2
        assert len(s.sections["capability_gap"]) == 1
        assert s.resolved_rows == []

    def test_load_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_registry(tmp_path)

    def test_row_status_and_fields(self, fake_root):
        s = load_registry(fake_root)
        d001 = next(r for r in s.sections["activity"] if r.id == "D-001")
        assert d001.status == "open"
        assert d001.fields["rule_id"] == "OMNI-007"
        assert d001.fields["severity"] == "MEDIUM"


# ═══ list_rows ═════════════════════════════════════════════════

class TestListRows:
    def test_default_open_across_sections(self, fake_root):
        s = load_registry(fake_root)
        rows = list_rows(s, status="open")
        ids = [r.id for r in rows]
        # 三个活跃 + 一个语义 open + 两个 plan pending（pending != open）
        assert "D-001" in ids
        assert "D-002" in ids
        assert "D-003" in ids
        assert "SA-001" in ids
        assert "SA-002" not in ids  # needs_human_review ≠ open
        assert "P-001" not in ids    # pending ≠ open

    def test_status_all(self, fake_root):
        s = load_registry(fake_root)
        rows = list_rows(s, status="all")
        # 不 filter → 所有 section 的条目
        assert len(rows) >= 6

    def test_section_filter(self, fake_root):
        s = load_registry(fake_root)
        rows = list_rows(s, section="semantic_pending", status="all")
        assert {r.id for r in rows} == {"SA-001", "SA-002"}

    def test_resolved_section(self, fake_root):
        s = load_registry(fake_root)
        rows = list_rows(s, section="resolved")
        assert rows == []


# ═══ compute_stats ═════════════════════════════════════════════

class TestStats:
    def test_counts(self, fake_root):
        s = load_registry(fake_root)
        st = compute_stats(s)
        # activity=3, semantic_pending=2, design_drift=0, plan_merge=2, capability_gap=1 → 8
        assert st["total_rows"] == 8
        assert st["by_section"]["activity"] == 3
        assert st["by_section"]["semantic_pending"] == 2
        assert st["by_severity"]["MEDIUM"] == 1
        assert st["by_severity"]["HIGH"] == 2
        assert "OMNI-007" in st["by_rule_id"]
        assert st["resolved_count"] == 0


# ═══ resolve_row ═══════════════════════════════════════════════

class TestResolve:
    def test_resolve_activity(self, fake_root):
        result = resolve_row(fake_root, "D-001", reason="fixed by cleanup")
        assert result.ok
        assert result.section_from == "activity"

        content = (fake_root / "docs/tech_debt/REGISTRY.md").read_text(encoding="utf-8")
        # D-001 应已从 §活跃违规 删除
        activity_idx = content.index("§活跃违规")
        resolved_idx = content.index("§已解决")
        # D-001 不应出现在 §活跃违规 表格内（之后的 §已解决 区段才允许）
        activity_section = content[activity_idx:resolved_idx]
        assert "D-001" not in activity_section
        # §已解决 表格应含 D-001
        resolved_section = content[resolved_idx:]
        assert "D-001" in resolved_section
        assert "fixed by cleanup" in resolved_section

    def test_resolve_unknown_prefix(self, fake_root):
        result = resolve_row(fake_root, "ZZ-001", reason="x")
        assert not result.ok
        assert "未知" in result.error

    def test_resolve_nonexistent(self, fake_root):
        result = resolve_row(fake_root, "D-999", reason="x")
        assert not result.ok
        assert "未找到" in result.error

    def test_resolve_empty_reason(self, fake_root):
        result = resolve_row(fake_root, "D-001", reason="")
        assert not result.ok
        assert "reason" in result.error

    def test_resolve_writes_arch_event(self, fake_root):
        result = resolve_row(fake_root, "SA-001", reason="migrated")
        assert result.ok
        assert result.arch_event_id.startswith("ARCH-")
        arch_path = fake_root / "docs/ARCH-CHANGES.jsonl"
        assert arch_path.exists()
        events = [json.loads(ln) for ln in arch_path.read_text(encoding="utf-8").strip().splitlines()]
        assert any(
            e["event_type"] == "violation-resolved" and "SA-001" in e["change"]
            for e in events
        )

    def test_resolve_double_not_allowed(self, fake_root):
        # 第一次 resolve 成功，第二次应失败（已从原 section 删除）
        r1 = resolve_row(fake_root, "D-001", reason="first")
        assert r1.ok
        r2 = resolve_row(fake_root, "D-001", reason="second")
        assert not r2.ok

    def test_resolve_by_agent(self, fake_root):
        result = resolve_row(fake_root, "P-001", reason="merged to DESIGN.md", resolved_by="claude-code")
        assert result.ok
        arch_path = fake_root / "docs/ARCH-CHANGES.jsonl"
        events = [json.loads(ln) for ln in arch_path.read_text(encoding="utf-8").strip().splitlines()]
        claude_events = [e for e in events if e.get("initiator") == "claude-code"]
        assert len(claude_events) >= 1

    def test_preserves_other_rows(self, fake_root):
        resolve_row(fake_root, "D-001", reason="x")
        content = (fake_root / "docs/tech_debt/REGISTRY.md").read_text(encoding="utf-8")
        # D-002、D-003 仍在
        assert "D-002" in content
        assert "D-003" in content
        # SA-001 未被碰
        assert "SA-001" in content


class TestSectionSpecs:
    def test_all_prefixes_unique(self):
        prefixes = [s.id_prefix for s in SECTION_SPECS]
        assert len(prefixes) == len(set(prefixes))

    def test_all_names_unique(self):
        names = [s.name for s in SECTION_SPECS]
        assert len(names) == len(set(names))
