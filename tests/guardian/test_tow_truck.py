"""OmniTow 单元测试

覆盖：
  1. process()          — ticket 生成、字段、落盘
  2. process_all()      — 批量处置
  3. list_tickets()     — 全部 / 按 status 过滤
  4. get_ticket()       — 按 ticket_id 读详情
  5. resolve_ticket()   — 标记 resolved
  6. whitelist_ticket() — 临时白名单
  7. is_whitelisted()   — 路径白名单判断（当前实现按 ticket_id，路径不匹配→False 验证）
  8. 处置动作 warn      — 仅记录，不改文件
  9. 处置动作 stamp     — 注入 OmniMark 头
  10. 处置动作 tombstone — Phase 1 跳过；Phase 2 插入 UNIDENTIFIED 头
  11. 处置动作 quarantine — Phase 1 跳过；Phase 2 备份 + TOMBSTONE
  12. 处置动作 evolve-signal — 非内部来源写 pending_signals.jsonl
  13. 索引去重
  14. recommended_action 覆盖所有 7 条规则
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.guardian.tow_truck import OmniTow, Ticket


# ─── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def tmp_root(tmp_path):
    """临时项目根目录（含最小骨架）。"""
    (tmp_path / ".omni").mkdir()
    return tmp_path


@pytest.fixture
def tow(tmp_root):
    return OmniTow(project_root=tmp_root)


@pytest.fixture
def tow_p2(tmp_root):
    """Phase 2 实例（tombstone/quarantine 实际执行，pilot_rules=frozenset() = 全量无限制）。"""
    return OmniTow(project_root=tmp_root, phase2=True, pilot_rules=frozenset())


def _make_violation(
    ticket_id: str = "TICKET-2026-04-05-001",
    rule_id: str = "OMNI-006",
    severity: str = "MEDIUM",
    path: str = "src/omnicompany/packages/domains/gameplay_system/scratch_foo.py",
    disposition=None,
    message: str = "临时脚本散落在 src/",
) -> dict:
    return {
        "ticket_id": ticket_id,
        "rule_id": rule_id,
        "severity": severity,
        "path": path,
        "message": message,
        "disposition": disposition if disposition is not None else ["warn"],
        "confidence": 1.0,
    }


def _make_py_file(tmp_root: Path, rel: str, content: str = "import os\n") -> Path:
    """在临时目录中创建一个真实 .py 文件，供 stamp/tombstone/quarantine 测试使用。"""
    abs_p = tmp_root / rel
    abs_p.parent.mkdir(parents=True, exist_ok=True)
    abs_p.write_text(content, encoding="utf-8")
    return abs_p


# ════════════════════════════════════════════════════════════════
# 1. process() — 基础 ticket 生成
# ════════════════════════════════════════════════════════════════

class TestProcess:
    def test_returns_ticket_instance(self, tow):
        v = _make_violation()
        ticket = tow.process(v)
        assert isinstance(ticket, Ticket)

    def test_ticket_fields_match_violation(self, tow):
        v = _make_violation(ticket_id="T-001", rule_id="OMNI-001", severity="HIGH")
        ticket = tow.process(v)
        assert ticket.ticket_id == "T-001"
        assert ticket.rule_violated == "OMNI-001"
        assert ticket.severity == "HIGH"
        assert ticket.original_path == v["path"]

    def test_ticket_status_is_open(self, tow):
        ticket = tow.process(_make_violation())
        assert ticket.status == "open"

    def test_ticket_saved_to_disk(self, tow, tmp_root):
        v = _make_violation(ticket_id="T-SAVE")
        tow.process(v)
        # 文件应出现在 .omni/quarantine/<date>/T-SAVE.json
        matches = list((tmp_root / ".omni" / "quarantine").glob("**/T-SAVE.json"))
        assert len(matches) == 1

    def test_ticket_json_is_valid(self, tow, tmp_root):
        v = _make_violation(ticket_id="T-JSON")
        tow.process(v)
        (ticket_file,) = (tmp_root / ".omni" / "quarantine").glob("**/T-JSON.json")
        data = json.loads(ticket_file.read_text(encoding="utf-8"))
        assert data["ticket_id"] == "T-JSON"

    def test_index_created(self, tow, tmp_root):
        tow.process(_make_violation(ticket_id="T-IDX"))
        index_file = tmp_root / ".omni" / "quarantine" / "index.json"
        assert index_file.exists()
        index = json.loads(index_file.read_text(encoding="utf-8"))
        assert any(e["ticket_id"] == "T-IDX" for e in index)

    def test_fingerprint_unknown_for_missing_file(self, tow):
        """文件不存在时 fingerprint 降级为 sha256:unknown。"""
        v = _make_violation(path="nonexistent/fake.py")
        ticket = tow.process(v)
        assert ticket.file_fingerprint == "sha256:unknown"

    def test_fingerprint_computed_for_real_file(self, tow, tmp_root):
        _make_py_file(tmp_root, "src/foo.py", "import os\n")
        v = _make_violation(path="src/foo.py")
        ticket = tow.process(v)
        assert ticket.file_fingerprint.startswith("sha256:")
        assert ticket.file_fingerprint != "sha256:unknown"


# ════════════════════════════════════════════════════════════════
# 2. process_all() — 批量
# ════════════════════════════════════════════════════════════════

class TestProcessAll:
    def test_returns_list_of_tickets(self, tow):
        violations = [
            _make_violation(ticket_id="T-A"),
            _make_violation(ticket_id="T-B"),
            _make_violation(ticket_id="T-C"),
        ]
        tickets = tow.process_all(violations)
        assert len(tickets) == 3
        assert all(isinstance(t, Ticket) for t in tickets)

    def test_all_tickets_in_index(self, tow, tmp_root):
        violations = [_make_violation(ticket_id=f"T-{i}") for i in range(3)]
        tow.process_all(violations)
        index_file = tmp_root / ".omni" / "quarantine" / "index.json"
        index = json.loads(index_file.read_text(encoding="utf-8"))
        ids = {e["ticket_id"] for e in index}
        assert {"T-0", "T-1", "T-2"} == ids

    def test_empty_list_returns_empty(self, tow):
        assert tow.process_all([]) == []


# ════════════════════════════════════════════════════════════════
# 3. list_tickets()
# ════════════════════════════════════════════════════════════════

class TestListTickets:
    def test_returns_all_tickets(self, tow):
        tow.process(_make_violation(ticket_id="TL-A"))
        tow.process(_make_violation(ticket_id="TL-B"))
        tickets = tow.list_tickets()
        assert len(tickets) >= 2

    def test_filter_by_status_open(self, tow):
        tow.process(_make_violation(ticket_id="TL-OPEN"))
        open_tickets = tow.list_tickets(status="open")
        assert all(t["status"] == "open" for t in open_tickets)

    def test_filter_by_status_resolved_empty_before_resolve(self, tow):
        tow.process(_make_violation(ticket_id="TL-RES"))
        resolved = tow.list_tickets(status="resolved")
        # 还没有 resolve，应该为空（或不包含 TL-RES）
        assert not any(t["ticket_id"] == "TL-RES" for t in resolved)

    def test_empty_when_no_tickets(self, tow):
        assert tow.list_tickets() == []


# ════════════════════════════════════════════════════════════════
# 4. get_ticket()
# ════════════════════════════════════════════════════════════════

class TestGetTicket:
    def test_returns_dict_for_existing_ticket(self, tow):
        tow.process(_make_violation(ticket_id="TG-001"))
        data = tow.get_ticket("TG-001")
        assert data is not None
        assert data["ticket_id"] == "TG-001"

    def test_returns_none_for_nonexistent(self, tow):
        assert tow.get_ticket("NONEXISTENT") is None

    def test_full_fields_present(self, tow):
        v = _make_violation(ticket_id="TG-FULL", rule_id="OMNI-003", severity="CRITICAL")
        tow.process(v)
        data = tow.get_ticket("TG-FULL")
        assert "rule_violated" in data
        assert "severity" in data
        assert "original_path" in data
        assert "disposition" in data


# ════════════════════════════════════════════════════════════════
# 5. resolve_ticket()
# ════════════════════════════════════════════════════════════════

class TestResolveTicket:
    def test_resolve_changes_status(self, tow):
        tow.process(_make_violation(ticket_id="TR-001"))
        ok = tow.resolve_ticket("TR-001")
        assert ok
        data = tow.get_ticket("TR-001")
        assert data["status"] == "resolved"

    def test_resolve_sets_resolved_at(self, tow):
        tow.process(_make_violation(ticket_id="TR-002"))
        tow.resolve_ticket("TR-002")
        data = tow.get_ticket("TR-002")
        assert data["resolved_at"] is not None

    def test_resolve_sets_resolved_by(self, tow):
        tow.process(_make_violation(ticket_id="TR-003"))
        tow.resolve_ticket("TR-003", resolved_by="test-runner")
        data = tow.get_ticket("TR-003")
        assert data["resolved_by"] == "test-runner"

    def test_resolve_updates_index_status(self, tow, tmp_root):
        tow.process(_make_violation(ticket_id="TR-IDX"))
        tow.resolve_ticket("TR-IDX")
        index = json.loads(
            (tmp_root / ".omni" / "quarantine" / "index.json").read_text(encoding="utf-8")
        )
        entry = next(e for e in index if e["ticket_id"] == "TR-IDX")
        assert entry["status"] == "resolved"

    def test_resolve_nonexistent_returns_false(self, tow):
        assert not tow.resolve_ticket("NONEXISTENT")


# ════════════════════════════════════════════════════════════════
# 6. whitelist_ticket()
# ════════════════════════════════════════════════════════════════

class TestWhitelistTicket:
    def test_whitelist_changes_status(self, tow):
        tow.process(_make_violation(ticket_id="TW-001"))
        ok = tow.whitelist_ticket("TW-001", hours=24, reason="紧急豁免")
        assert ok
        data = tow.get_ticket("TW-001")
        assert data["status"] == "whitelisted"

    def test_whitelist_sets_expires(self, tow):
        tow.process(_make_violation(ticket_id="TW-002"))
        tow.whitelist_ticket("TW-002", hours=48)
        data = tow.get_ticket("TW-002")
        assert data["whitelist_expires"] is not None

    def test_whitelist_nonexistent_returns_false(self, tow):
        assert not tow.whitelist_ticket("NONEXISTENT")

    def test_whitelist_file_created(self, tow, tmp_root):
        tow.process(_make_violation(ticket_id="TW-FILE"))
        tow.whitelist_ticket("TW-FILE", hours=1)
        wl_file = tmp_root / ".omni" / "whitelist" / "whitelist.json"
        assert wl_file.exists()
        wl = json.loads(wl_file.read_text(encoding="utf-8"))
        assert any(e["ticket_id"] == "TW-FILE" for e in wl)

    def test_whitelist_list_shows_whitelisted(self, tow):
        tow.process(_make_violation(ticket_id="TW-LIST"))
        tow.whitelist_ticket("TW-LIST")
        wl_tickets = tow.list_tickets(status="whitelisted")
        assert any(t["ticket_id"] == "TW-LIST" for t in wl_tickets)


# ════════════════════════════════════════════════════════════════
# 7. is_whitelisted() — 当前实现按 path 字段，通过 whitelist.json
# ════════════════════════════════════════════════════════════════

class TestIsWhitelisted:
    def test_not_whitelisted_by_default(self, tow):
        assert not tow.is_whitelisted("src/omnicompany/packages/domains/gameplay_system/foo.py")

    def test_is_whitelisted_after_adding_entry_directly(self, tow, tmp_root):
        """直接写白名单 JSON 验证 is_whitelisted 逻辑。"""
        from datetime import datetime, timezone, timedelta
        wl_dir = tmp_root / ".omni" / "whitelist"
        wl_dir.mkdir(parents=True, exist_ok=True)
        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        wl_file = wl_dir / "whitelist.json"
        wl_file.write_text(
            json.dumps([{"path": "src/gameplay_system/foo.py", "expires": expires, "ticket_id": "T-WL"}]),
            encoding="utf-8",
        )
        assert tow.is_whitelisted("src/gameplay_system/foo.py")

    def test_expired_entry_not_whitelisted(self, tow, tmp_root):
        from datetime import datetime, timezone, timedelta
        wl_dir = tmp_root / ".omni" / "whitelist"
        wl_dir.mkdir(parents=True, exist_ok=True)
        expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        wl_file = wl_dir / "whitelist.json"
        wl_file.write_text(
            json.dumps([{"path": "src/gameplay_system/foo.py", "expires": expired, "ticket_id": "T-EXP"}]),
            encoding="utf-8",
        )
        assert not tow.is_whitelisted("src/gameplay_system/foo.py")


# ════════════════════════════════════════════════════════════════
# 8. 处置动作: warn
# ════════════════════════════════════════════════════════════════

class TestActionWarn:
    def test_warn_does_not_modify_file(self, tow, tmp_root):
        _make_py_file(tmp_root, "src/foo.py", "import os\n")
        v = _make_violation(path="src/foo.py", disposition=["warn"])
        tow.process(v)
        assert (tmp_root / "src/foo.py").read_text(encoding="utf-8") == "import os\n"

    def test_warn_ticket_status_is_open(self, tow):
        ticket = tow.process(_make_violation(disposition=["warn"]))
        assert ticket.status == "open"


# ════════════════════════════════════════════════════════════════
# 9. 处置动作: stamp
# ════════════════════════════════════════════════════════════════

class TestActionStamp:
    def test_stamp_injects_omnimark(self, tow, tmp_root):
        _make_py_file(tmp_root, "src/foo.py", "import os\n")
        v = _make_violation(path="src/foo.py", disposition=["stamp"])
        tow.process(v)
        content = (tmp_root / "src/foo.py").read_text(encoding="utf-8")
        assert "# [OMNI]" in content
        assert "origin=unknown" in content
        assert "pending-review" in content

    def test_stamp_nonexistent_file_does_not_crash(self, tow):
        """文件不存在时 stamp 应安静失败，不抛异常。"""
        v = _make_violation(path="nonexistent/file.py", disposition=["stamp"])
        ticket = tow.process(v)  # should not raise
        assert ticket is not None


# ════════════════════════════════════════════════════════════════
# 10. 处置动作: tombstone
# ════════════════════════════════════════════════════════════════

class TestActionTombstone:
    def test_phase1_tombstone_does_not_modify_file(self, tow, tmp_root):
        """Phase 1：tombstone 跳过，文件不变。"""
        _make_py_file(tmp_root, "src/foo.py", "import os\n")
        v = _make_violation(path="src/foo.py", disposition=["tombstone"])
        tow.process(v)
        assert (tmp_root / "src/foo.py").read_text(encoding="utf-8") == "import os\n"

    def test_phase2_tombstone_inserts_header(self, tow_p2, tmp_root):
        """Phase 2：文件头部插入 UNIDENTIFIED 告示。"""
        _make_py_file(tmp_root, "src/foo.py", "import os\n")
        v = _make_violation(path="src/foo.py", disposition=["tombstone"])
        tow_p2.process(v)
        content = (tmp_root / "src/foo.py").read_text(encoding="utf-8")
        assert "OMNI-UNIDENTIFIED" in content
        # 原始内容仍在
        assert "import os" in content

    def test_phase2_tombstone_creates_watchlist_entry(self, tow_p2, tmp_root):
        _make_py_file(tmp_root, "src/bar.py", "x = 1\n")
        v = _make_violation(path="src/bar.py", disposition=["tombstone"])
        tow_p2.process(v)
        watch_files = list((tmp_root / ".omni" / "watchlist").glob("*.watch.json"))
        assert len(watch_files) == 1

    def test_phase2_tombstone_nonexistent_file_safe(self, tow_p2):
        """文件不存在时 tombstone 安静跳过。"""
        v = _make_violation(path="nonexistent/missing.py", disposition=["tombstone"])
        tow_p2.process(v)  # should not raise


# ════════════════════════════════════════════════════════════════
# 11. 处置动作: quarantine
# ════════════════════════════════════════════════════════════════

class TestActionQuarantine:
    def test_phase1_quarantine_does_not_move_file(self, tow, tmp_root):
        """Phase 1：quarantine 跳过，文件不变。"""
        _make_py_file(tmp_root, "src/foo.py", "import os\n")
        v = _make_violation(path="src/foo.py", disposition=["quarantine"])
        tow.process(v)
        assert (tmp_root / "src/foo.py").read_text(encoding="utf-8") == "import os\n"

    def test_phase2_quarantine_backs_up_file(self, tow_p2, tmp_root):
        """Phase 2：原始文件备份到 .omni/quarantine/<date>/。"""
        _make_py_file(tmp_root, "src/foo.py", "import os\n")
        v = _make_violation(path="src/foo.py", disposition=["quarantine"])
        tow_p2.process(v)
        backups = list((tmp_root / ".omni" / "quarantine").glob("**/foo.py"))
        assert len(backups) >= 1

    def test_phase2_quarantine_replaces_with_tombstone(self, tow_p2, tmp_root):
        """Phase 2：原始位置替换为 TOMBSTONE 告示牌。"""
        _make_py_file(tmp_root, "src/foo.py", "import os\n")
        v = _make_violation(path="src/foo.py", disposition=["quarantine"])
        tow_p2.process(v)
        content = (tmp_root / "src/foo.py").read_text(encoding="utf-8")
        assert "OMNI-TOMBSTONE" in content

    def test_phase2_quarantine_ticket_has_quarantine_path(self, tow_p2, tmp_root):
        _make_py_file(tmp_root, "src/foo.py", "import os\n")
        v = _make_violation(path="src/foo.py", disposition=["quarantine"])
        ticket = tow_p2.process(v)
        assert ticket.quarantine_path != ""

    def test_phase2_quarantine_backup_has_original_content(self, tow_p2, tmp_root):
        """备份文件内容 = 原始内容（未被污染）。"""
        _make_py_file(tmp_root, "src/foo.py", "ORIGINAL_MARKER = True\n")
        v = _make_violation(path="src/foo.py", disposition=["quarantine"])
        tow_p2.process(v)
        backups = list((tmp_root / ".omni" / "quarantine").glob("**/foo.py"))
        content = backups[0].read_text(encoding="utf-8")
        assert "ORIGINAL_MARKER" in content

    def test_phase2_quarantine_nonexistent_file_safe(self, tow_p2):
        v = _make_violation(path="nonexistent/missing.py", disposition=["quarantine"])
        tow_p2.process(v)  # should not raise


# ════════════════════════════════════════════════════════════════
# 12b. Phase 2 试点区（pilot_rules）
# ════════════════════════════════════════════════════════════════

class TestPhase2PilotRules:
    def test_pilot_rule_in_set_executes_tombstone(self, tmp_root):
        """pilot_rules={"OMNI-007"} + phase2=True → OMNI-007 触发 tombstone。"""
        _make_py_file(tmp_root, "src/notes.md", "# some notes\n")
        tow = OmniTow(project_root=tmp_root, phase2=True, pilot_rules=frozenset({"OMNI-007"}))
        v = _make_violation(
            rule_id="OMNI-007",
            path="src/notes.md",
            disposition=["tombstone"],
        )
        tow.process(v)
        content = (tmp_root / "src/notes.md").read_text(encoding="utf-8")
        assert "OMNI-UNIDENTIFIED" in content

    def test_non_pilot_rule_skips_tombstone(self, tmp_root):
        """pilot_rules={"OMNI-007"} + phase2=True → OMNI-006 不触发 tombstone。"""
        _make_py_file(tmp_root, "src/scratch.py", "x = 1\n")
        tow = OmniTow(project_root=tmp_root, phase2=True, pilot_rules=frozenset({"OMNI-007"}))
        v = _make_violation(
            rule_id="OMNI-006",
            path="src/scratch.py",
            disposition=["tombstone"],
        )
        tow.process(v)
        # 文件内容不应被修改
        assert (tmp_root / "src/scratch.py").read_text(encoding="utf-8") == "x = 1\n"

    def test_empty_pilot_rules_allows_all(self, tmp_root):
        """pilot_rules=frozenset() → 视为全量 Phase 2，所有规则都执行。"""
        _make_py_file(tmp_root, "src/scratch.py", "x = 1\n")
        tow = OmniTow(project_root=tmp_root, phase2=True, pilot_rules=frozenset())
        v = _make_violation(
            rule_id="OMNI-006",
            path="src/scratch.py",
            disposition=["tombstone"],
        )
        tow.process(v)
        content = (tmp_root / "src/scratch.py").read_text(encoding="utf-8")
        assert "OMNI-UNIDENTIFIED" in content

    def test_default_pilot_rules_is_omni007(self, tmp_root):
        """默认试点集合包含 OMNI-007。"""
        assert "OMNI-007" in OmniTow._DEFAULT_PILOT_RULES


# ════════════════════════════════════════════════════════════════
# 12. 处置动作: evolve-signal
# ════════════════════════════════════════════════════════════════

class TestActionEvolveSignal:
    def test_external_origin_writes_pending_signals_jsonl(self, tow, tmp_root):
        """非内部管线来源 → 不触发 OmniEvolve，写 pending_signals.jsonl。"""
        v = _make_violation(ticket_id="EVS-EXT", disposition=["evolve-signal"])
        tow.process(v)
        log_file = tmp_root / ".omni" / "evolution" / "pending_signals.jsonl"
        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1
        entry = json.loads(lines[0])
        assert entry["source_ticket"] == "EVS-EXT"

    def test_evolve_signal_does_not_crash_on_exception(self, tow):
        """即使 OmniEvolve 内部出错，处置流程不崩溃。"""
        v = _make_violation(disposition=["evolve-signal"])
        ticket = tow.process(v)  # should not raise
        assert ticket is not None


# ════════════════════════════════════════════════════════════════
# 13. 索引去重
# ════════════════════════════════════════════════════════════════

class TestIndexDedup:
    def test_same_ticket_id_not_duplicated(self, tow, tmp_root):
        """相同 ticket_id 处置两次，索引中只有一条。"""
        v = _make_violation(ticket_id="T-DUP")
        tow.process(v)
        tow.process(v)  # 再处置一次
        index = json.loads(
            (tmp_root / ".omni" / "quarantine" / "index.json").read_text(encoding="utf-8")
        )
        dup_count = sum(1 for e in index if e["ticket_id"] == "T-DUP")
        assert dup_count == 1


# ════════════════════════════════════════════════════════════════
# 14. recommended_action 覆盖
# ════════════════════════════════════════════════════════════════

class TestRecommendedAction:
    @pytest.mark.parametrize("rule_id,keyword", [
        ("OMNI-001", "stamp"),
        ("OMNI-002", "packages"),
        ("OMNI-003", "LLMClient"),
        ("OMNI-004", "run"),
        ("OMNI-005", "data/"),
        ("OMNI-006", "scripts/"),
        ("OMNI-007", "docs/"),
    ])
    def test_recommended_action_contains_keyword(self, tow, rule_id, keyword):
        v = _make_violation(rule_id=rule_id)
        ticket = tow.process(v)
        assert keyword in ticket.recommended_action, \
            f"{rule_id} 的 recommended_action 应包含 '{keyword}'"

    def test_unknown_rule_has_fallback_action(self, tow):
        v = _make_violation(rule_id="OMNI-999")
        ticket = tow.process(v)
        assert ticket.recommended_action != ""
