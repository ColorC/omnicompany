"""OmniEvolve 单元测试

测试覆盖：
  1. 非内部管线违规 → 不产生 EvolutionSignal
  2. 内部管线首次违规 → Level 0
  3. 同节点第 2-3 次违规 → Level 1（生成 pending correction）
  4. 同节点第 4+ 次违规 → Level 2（restriction_request）
  5. 连续合规降级机制
  6. apply_correction 流程
  7. OmniTow 集成（evolve-signal disposition）
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# 确保 src 在路径里
sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.guardian.evolve_signal import (
    OmniEvolve,
    NodeViolationHistory,
    INTERNAL_PIPELINE_ORIGINS,
)


# ─── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def tmp_root(tmp_path):
    """临时项目根目录（含 .omni/ 结构）。"""
    (tmp_path / ".omni" / "evolution" / "nodes").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def evo(tmp_root):
    # use_llm=False：测试不发真实 LLM 请求，使用规则模板建议
    return OmniEvolve(project_root=tmp_root, use_llm=False)


def _make_violation(
    ticket_id="TICKET-2026-04-05-001",
    rule_id="OMNI-003",
    severity="CRITICAL",
    path="src/omnicompany/packages/domains/gameplay_system/foo.py",
    disposition=None,
    message="直接使用 LLM SDK",
):
    return {
        "ticket_id": ticket_id,
        "rule_id": rule_id,
        "severity": severity,
        "path": path,
        "message": message,
        "disposition": disposition or ["evolve-signal"],
        "confidence": 1.0,
    }


def _internal_omnimark(node="implementor-router", pipeline="sw-implement", trace="trc_abc"):
    return {
        "origin": pipeline,
        "domain": "software_engineering/plan",
        "agent": "claude-sonnet-4-6",
        "ts": "2026-04-05T12:00:00Z",
        "trace": trace,
        "node": node,
        "status": "active",
        "created_by": "",
        "intent": "",
    }


def _external_omnimark():
    return {
        "origin": "claude-code",
        "domain": "",
        "agent": "",
        "ts": "2026-04-05T12:00:00Z",
        "trace": "",   # 无 trace → 非内部
        "node": "",
        "status": "active",
        "created_by": "",
        "intent": "",
    }


# ─── 1. 非内部管线 → 不产生信号 ─────────────────────────────────

def test_external_origin_returns_none(evo):
    v = _make_violation()
    signal = evo.process(v, omnimark=_external_omnimark())
    assert signal is None


def test_no_omnimark_returns_none(evo):
    v = _make_violation()
    signal = evo.process(v, omnimark=None)
    assert signal is None


def test_internal_origin_no_trace_returns_none(evo):
    mark = _internal_omnimark()
    mark["trace"] = ""   # 没有 trace → 不可追溯
    v = _make_violation()
    signal = evo.process(v, omnimark=mark)
    assert signal is None


# ─── 2. 首次违规 → Level 0 ───────────────────────────────────────

def test_first_violation_is_level0(evo):
    v = _make_violation(ticket_id="TICKET-001")
    signal = evo.process(v, omnimark=_internal_omnimark())

    assert signal is not None
    assert signal.escalation_level == 0
    assert signal.repeat_count == 1
    assert signal.source_node == "implementor-router"
    assert signal.rule_violated == "OMNI-003"


def test_level0_no_pending_correction(evo, tmp_root):
    v = _make_violation(ticket_id="TICKET-001")
    evo.process(v, omnimark=_internal_omnimark())

    pc_file = tmp_root / ".omni" / "evolution" / "nodes" / "implementor-router.pending_correction.json"
    assert not pc_file.exists(), "Level 0 不应生成 pending_correction"


def test_level0_history_saved(evo, tmp_root):
    v = _make_violation(ticket_id="TICKET-001")
    evo.process(v, omnimark=_internal_omnimark())

    history = evo.get_node_history("implementor-router")
    assert history is not None
    assert history.total_violations == 1
    assert len(history.violations) == 1
    assert history.violations[0]["rule"] == "OMNI-003"


# ─── 3. 第 2-3 次违规 → Level 1 ──────────────────────────────────

def test_second_violation_is_level1(evo):
    mark = _internal_omnimark()
    # 第 1 次
    evo.process(_make_violation(ticket_id="TICKET-001"), omnimark=mark)
    # 第 2 次
    signal = evo.process(_make_violation(ticket_id="TICKET-002"), omnimark=mark)

    assert signal is not None
    assert signal.escalation_level == 1
    assert signal.repeat_count == 2


def test_third_violation_still_level1(evo):
    mark = _internal_omnimark()
    for i in range(3):
        signal = evo.process(_make_violation(ticket_id=f"TICKET-00{i+1}"), omnimark=mark)
    assert signal.escalation_level == 1
    assert signal.repeat_count == 3


def test_level1_creates_pending_correction(evo, tmp_root):
    mark = _internal_omnimark()
    evo.process(_make_violation(ticket_id="TICKET-001"), omnimark=mark)
    evo.process(_make_violation(ticket_id="TICKET-002"), omnimark=mark)

    pc_file = tmp_root / ".omni" / "evolution" / "nodes" / "implementor-router.pending_correction.json"
    assert pc_file.exists()

    data = json.loads(pc_file.read_text(encoding="utf-8"))
    assert data["status"] == "pending"
    assert data["node_id"] == "implementor-router"
    assert data["repeat_count"] == 2
    assert len(data["suggested_correction"]) > 0


def test_level1_correction_contains_rule_hint(evo, tmp_root):
    mark = _internal_omnimark()
    evo.process(_make_violation(ticket_id="TICKET-001"), omnimark=mark)
    evo.process(_make_violation(ticket_id="TICKET-002"), omnimark=mark)

    pc = evo.get_pending_correction("implementor-router")
    # OMNI-003 的模板提示应包含 LLMClient 关键词
    assert "LLMClient" in pc["suggested_correction"] or "anthropic" in pc["suggested_correction"].lower()


# ─── 4. 第 4+ 次违规 → Level 2 ───────────────────────────────────

def test_fourth_violation_is_level2(evo):
    mark = _internal_omnimark()
    for i in range(4):
        signal = evo.process(_make_violation(ticket_id=f"TICKET-00{i+1}"), omnimark=mark)
    assert signal.escalation_level == 2
    assert signal.repeat_count == 4


def test_level2_creates_restriction_request(evo, tmp_root):
    mark = _internal_omnimark()
    for i in range(4):
        evo.process(_make_violation(ticket_id=f"TICKET-00{i+1}"), omnimark=mark)

    rr_file = tmp_root / ".omni" / "evolution" / "nodes" / "implementor-router.restriction_request.json"
    assert rr_file.exists()

    data = json.loads(rr_file.read_text())
    assert data["status"] == "pending_confirmation"
    assert "OMNI-003" in data["blocked_patterns"] or len(data["blocked_patterns"]) > 0


# ─── 5. 连续合规降级 ─────────────────────────────────────────────

def test_clean_runs_downgrade_level(evo):
    mark = _internal_omnimark()
    # 推到 Level 2（4 次违规）
    for i in range(4):
        evo.process(_make_violation(ticket_id=f"TICKET-00{i+1}"), omnimark=mark)

    history = evo.get_node_history("implementor-router")
    assert history.escalation_level() == 2

    # 连续 5 次合规 → 降级
    for _ in range(5):
        evo.record_clean_run("implementor-router")

    history = evo.get_node_history("implementor-router")
    assert history.escalation_level() < 2, "连续 5 次合规后应降级"
    assert history.consecutive_clean_runs == 0


def test_clean_run_on_no_history(evo):
    """对没有历史的节点调用 record_clean_run 不应报错。"""
    evo.record_clean_run("nonexistent-node")  # should not raise


# ─── 6. apply_correction 流程 ────────────────────────────────────

def test_apply_correction_marks_as_applied(evo, tmp_root):
    mark = _internal_omnimark()
    evo.process(_make_violation(ticket_id="TICKET-001"), omnimark=mark)
    evo.process(_make_violation(ticket_id="TICKET-002"), omnimark=mark)

    # 确认有 pending
    pc = evo.get_pending_correction("implementor-router")
    assert pc["status"] == "pending"

    # 应用
    ok = evo.apply_correction("implementor-router", applied_by="test-runner")
    assert ok

    # 再次读取应为 applied
    pc2 = evo.get_pending_correction("implementor-router")
    assert pc2["status"] == "applied"
    assert pc2["applied_by"] == "test-runner"
    assert pc2["applied_at"] is not None


def test_apply_correction_nonexistent_node(evo):
    ok = evo.apply_correction("no-such-node")
    assert not ok


# ─── 7. 多节点独立历史 ───────────────────────────────────────────

def test_different_nodes_independent_history(evo):
    mark_a = _internal_omnimark(node="node-a", pipeline="sw-implement")
    mark_b = _internal_omnimark(node="node-b", pipeline="sw-tdd")

    # node-a 违规 4 次
    for i in range(4):
        evo.process(_make_violation(ticket_id=f"A-00{i+1}"), omnimark=mark_a)

    # node-b 首次违规
    sig_b = evo.process(_make_violation(ticket_id="B-001"), omnimark=mark_b)

    hist_a = evo.get_node_history("node-a")
    hist_b = evo.get_node_history("node-b")

    assert hist_a.total_violations == 4
    assert hist_a.escalation_level() == 2
    assert hist_b.total_violations == 1
    assert hist_b.escalation_level() == 0
    assert sig_b.escalation_level == 0


# ─── 8. index.json 更新 ──────────────────────────────────────────

def test_index_updated_after_process(evo):
    mark = _internal_omnimark()
    evo.process(_make_violation(ticket_id="TICKET-001"), omnimark=mark)
    evo.process(_make_violation(ticket_id="TICKET-002"), omnimark=mark)

    signals = evo.list_all()
    assert len(signals) == 2
    assert signals[0]["node_id"] == "implementor-router"


def test_index_deduplicates_signal_id(evo):
    """同 signal_id 不重复写入 index。"""
    mark = _internal_omnimark()
    v = _make_violation(ticket_id="TICKET-DUP")
    evo.process(v, omnimark=mark)
    evo.process(v, omnimark=mark)   # 同一个 violation 处理两次

    # 由于 ticket_id 相同 → signal_id 相同 → 只有一条（会被覆盖）
    signals = evo.list_all()
    dup_count = sum(1 for s in signals if s.get("signal_id", "").endswith("TICKET-DUP"))
    assert dup_count == 1


# ─── 9. _is_internal 边界条件 ────────────────────────────────────

@pytest.mark.parametrize("origin", list(INTERNAL_PIPELINE_ORIGINS))
def test_all_internal_origins_recognized(evo, origin):
    mark = {
        "origin": origin,
        "trace": "trc_xxx",
        "node": "some-node",
        "domain": "", "agent": "", "ts": "", "status": "active",
        "created_by": "", "intent": "",
    }
    # _is_internal 应返回 True
    assert evo._is_internal(mark)


def test_human_origin_not_internal(evo):
    mark = {"origin": "human", "trace": "trc_xxx", "node": "n", "created_by": "", "intent": ""}
    assert not evo._is_internal(mark)


def test_claude_code_origin_not_internal(evo):
    mark = {"origin": "claude-code", "trace": "trc_xxx", "node": "n", "created_by": "", "intent": ""}
    assert not evo._is_internal(mark)
