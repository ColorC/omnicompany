# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T09:35:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest HypothesisChallengeQueue — 验 schema §三步骤 1-2 优先怀疑顺序 (a > b > c)"
# [OMNI] why="V2 第二项. 红绿对比 + 边界 + 真用排序 + focus_count 截断"
# [OMNI] tags=test,pytest,challenge-queue,hypothesis-priority,V2
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_hypothesis_challenge_queue.py"
"""pytest HypothesisChallengeQueue — schema §三步骤 1-2 排序逻辑.

测 case:
- 边界 (空 list / 非 dict / 缺 id)
- a 类触发 (confidence=low + risk=high)
- b 类触发 (untested + applies_to 命中 problem_context)
- c 类触发 (被 ≥3 条假设依赖)
- 优先级顺序 a > b > c (score 权重)
- focus_count 截断
- summary
"""
from __future__ import annotations

import pytest

from omnicompany.packages.services._diagnosis.doctor.builders import (
    HypothesisChallengeQueue,
    rank_hypothesis_challenge_queue,
)


@pytest.fixture
def queue():
    return HypothesisChallengeQueue()


# ── 边界 ──

def test_rank_empty_list(queue):
    result = queue.rank([])
    assert result.ranked == []
    assert result.total_input == 0


def test_rank_skip_non_dict(queue):
    result = queue.rank(["string", 42, None])
    assert result.ranked == []
    assert len(result.skipped) == 3


def test_rank_skip_no_id(queue):
    result = queue.rank([{"statement": "no id"}])
    assert result.ranked == []
    assert result.skipped == [("<no-id>", "缺 id")]


# ── a 类: confidence=low + risk=high ──

def test_a_class_triggers_score_1000(queue):
    result = queue.rank([{
        "id": "H-a", "confidence_level": "low", "risk_if_wrong": "high",
        "verification_status": "untested",
    }])
    assert len(result.ranked) == 1
    e = result.ranked[0]
    assert e.priority_score >= 1000
    assert any("a:" in r for r in e.priority_reasons)


def test_a_class_not_triggered_when_confidence_high(queue):
    """confidence=high → a 不触发, score 应不含 1000 段."""
    result = queue.rank([{
        "id": "H-not-a", "confidence_level": "high", "risk_if_wrong": "high",
    }])
    assert result.ranked[0].priority_score < 1000


def test_a_class_not_triggered_when_risk_low(queue):
    """risk=low → a 不触发."""
    result = queue.rank([{
        "id": "H-not-a", "confidence_level": "low", "risk_if_wrong": "low",
    }])
    assert result.ranked[0].priority_score < 1000


# ── b 类: untested + applies_to 命中 ──

def test_b_class_triggers_when_applies_to_matches(queue):
    """untested + applies_to=worker + ctx applies_to=worker → b 触发."""
    result = queue.rank(
        [{"id": "H-b", "verification_status": "untested", "applies_to": "worker",
          "confidence_level": "medium", "risk_if_wrong": "medium"}],
        problem_context={"applies_to": "worker"},
    )
    e = result.ranked[0]
    assert 100 <= e.priority_score < 1000  # b 类但不是 a
    assert any("b:" in r for r in e.priority_reasons)


def test_b_class_not_triggered_without_context(queue):
    """untested 但没传 problem_context → b 不触发."""
    result = queue.rank(
        [{"id": "H-no-ctx", "verification_status": "untested", "applies_to": "worker"}],
    )
    assert result.ranked[0].priority_score < 100


def test_b_class_not_triggered_when_applies_to_mismatches(queue):
    """untested + applies_to=worker + ctx applies_to=team → b 不触发."""
    result = queue.rank(
        [{"id": "H-mis", "verification_status": "untested", "applies_to": "worker"}],
        problem_context={"applies_to": "team"},
    )
    assert result.ranked[0].priority_score < 100


# ── c 类: depended_by ≥ 阈值 ──

def test_c_class_triggers_when_depended_by_3(queue):
    """3 条假设依赖 H-base → H-base 触发 c 类."""
    hyps = [
        {"id": "H-base"},
        {"id": "H-d1", "dependent_hypotheses": ["H-base"]},
        {"id": "H-d2", "dependent_hypotheses": ["H-base"]},
        {"id": "H-d3", "dependent_hypotheses": ["H-base"]},
    ]
    result = queue.rank(hyps)
    by_id = {e.hypothesis_id: e for e in result.ranked}
    base_e = by_id["H-base"]
    # c 类: 30 (3 × 10)
    assert base_e.priority_score >= 30
    assert any("c:" in r for r in base_e.priority_reasons)
    # 其他依赖者 score=0 (没触发任何类)
    assert by_id["H-d1"].priority_score == 0


def test_c_class_not_triggered_below_threshold(queue):
    """只 2 条依赖, 默认阈值 3 → c 不触发."""
    hyps = [
        {"id": "H-base"},
        {"id": "H-d1", "dependent_hypotheses": ["H-base"]},
        {"id": "H-d2", "dependent_hypotheses": ["H-base"]},
    ]
    result = queue.rank(hyps)
    by_id = {e.hypothesis_id: e for e in result.ranked}
    assert by_id["H-base"].priority_score == 0


def test_c_class_custom_threshold(queue):
    """自定义阈值 = 2 → 2 条依赖也触发."""
    hyps = [
        {"id": "H-base"},
        {"id": "H-d1", "dependent_hypotheses": ["H-base"]},
        {"id": "H-d2", "dependent_hypotheses": ["H-base"]},
    ]
    result = queue.rank(hyps, depended_by_threshold=2)
    by_id = {e.hypothesis_id: e for e in result.ranked}
    assert by_id["H-base"].priority_score >= 20


# ── 优先级顺序 a > b > c ──

def test_priority_order_a_beats_b_beats_c(queue):
    """三条假设各触发 a/b/c 类, 排序应当是 a > b > c."""
    hyps = [
        # a 类: confidence=low + risk=high
        {"id": "H-A", "confidence_level": "low", "risk_if_wrong": "high"},
        # b 类: untested + applies_to 命中
        {"id": "H-B", "verification_status": "untested", "applies_to": "worker",
         "confidence_level": "medium", "risk_if_wrong": "medium"},
        # c 类: 3 条依赖 (但本身不带 a/b 触发)
        {"id": "H-C"},
        {"id": "H-d1", "dependent_hypotheses": ["H-C"]},
        {"id": "H-d2", "dependent_hypotheses": ["H-C"]},
        {"id": "H-d3", "dependent_hypotheses": ["H-C"]},
    ]
    result = queue.rank(hyps, problem_context={"applies_to": "worker"})
    # H-A 应排第 1 (score=1000)
    # H-B 应排第 2 (score=100)
    # H-C 应排第 3 (score=30)
    # H-d1/d2/d3 score=0
    top3_ids = [e.hypothesis_id for e in result.ranked[:3]]
    assert top3_ids == ["H-A", "H-B", "H-C"]


def test_a_and_b_cumulative(queue):
    """假设同时触发 a + b 累计 score = 1100."""
    result = queue.rank(
        [{"id": "H-AB", "confidence_level": "low", "risk_if_wrong": "high",
          "verification_status": "untested", "applies_to": "worker"}],
        problem_context={"applies_to": "worker"},
    )
    e = result.ranked[0]
    assert e.priority_score >= 1100
    # 含两段 reason
    assert any("a:" in r for r in e.priority_reasons)
    assert any("b:" in r for r in e.priority_reasons)


# ── focus_count 截断 ──

def test_focus_count_truncates_top_n(queue):
    """focus_count=2 应只返前 2 条."""
    hyps = [
        {"id": f"H-{i}", "confidence_level": "low", "risk_if_wrong": "high"}
        for i in range(5)
    ]
    result = queue.rank(hyps, focus_count=2)
    assert len(result.ranked) == 2


def test_focus_count_zero_returns_empty(queue):
    """focus_count=0 → 返空."""
    result = queue.rank(
        [{"id": "H-1", "confidence_level": "low", "risk_if_wrong": "high"}],
        focus_count=0,
    )
    assert result.ranked == []


def test_focus_count_none_returns_all(queue):
    hyps = [{"id": f"H-{i}"} for i in range(10)]
    result = queue.rank(hyps)
    assert len(result.ranked) == 10


# ── falsified 轻微优先 ──

def test_falsified_gets_minor_boost(queue):
    """falsified 假设得 +1 score (复审). V7 后需 skip_frozen=False 才进 ranked."""
    result = queue.rank(
        [{"id": "H-f", "verification_status": "falsified"}],
        skip_frozen=False,
    )
    assert result.ranked[0].priority_score == 1
    assert any("falsified" in r for r in result.ranked[0].priority_reasons)


# ── 稳定排序 ──

def test_stable_order_for_same_score(queue):
    """同 score 按 id 升序稳定排."""
    hyps = [
        {"id": "H-zebra", "confidence_level": "low", "risk_if_wrong": "high"},
        {"id": "H-alpha", "confidence_level": "low", "risk_if_wrong": "high"},
        {"id": "H-mike", "confidence_level": "low", "risk_if_wrong": "high"},
    ]
    result = queue.rank(hyps)
    ids = [e.hypothesis_id for e in result.ranked]
    assert ids == ["H-alpha", "H-mike", "H-zebra"]  # 字典序


# ── summary ──

def test_summary_with_ranked(queue):
    result = queue.rank([{"id": "H-x", "confidence_level": "low", "risk_if_wrong": "high"}])
    s = result.summary
    assert "input 1" in s
    assert "ranked 1" in s
    assert "top_score=1000" in s


def test_summary_empty(queue):
    s = queue.rank([]).summary
    assert "ranked 0" in s


# ── 便捷入口 ──

def test_helper_function():
    result = rank_hypothesis_challenge_queue([
        {"id": "H-1", "confidence_level": "low", "risk_if_wrong": "high"}
    ])
    assert len(result.ranked) == 1
    assert result.ranked[0].priority_score >= 1000


# ── V7 2026-05-07: skip_frozen 默认跳过 falsified / real_world_validated ──

def test_skip_frozen_default_skips_falsified(queue):
    """skip_frozen 默认 True → falsified 假设不进 ranked."""
    hyps = [
        {"id": "H-active", "confidence_level": "low", "risk_if_wrong": "high"},
        {"id": "H-falsified", "verification_status": "falsified", "confidence_level": "low", "risk_if_wrong": "high"},
        {"id": "H-validated", "verification_status": "real_world_validated", "confidence_level": "high", "risk_if_wrong": "high"},
    ]
    result = queue.rank(hyps)
    ids_ranked = [e.hypothesis_id for e in result.ranked]
    assert "H-active" in ids_ranked
    assert "H-falsified" not in ids_ranked
    assert "H-validated" not in ids_ranked
    # frozen 假设进 skipped
    skipped_ids = [s[0] for s in result.skipped]
    assert "H-falsified" in skipped_ids
    assert "H-validated" in skipped_ids
    for hid, reason in result.skipped:
        if hid in ("H-falsified", "H-validated"):
            assert "已封存" in reason


def test_skip_frozen_false_includes_falsified(queue):
    """skip_frozen=False 时 falsified 假设进 ranked + 触发 +1 boost."""
    hyps = [
        {"id": "H-falsified", "verification_status": "falsified"},
    ]
    result = queue.rank(hyps, skip_frozen=False)
    assert len(result.ranked) == 1
    assert result.ranked[0].hypothesis_id == "H-falsified"
    assert result.ranked[0].priority_score == 1  # falsified +1


def test_skip_frozen_does_not_skip_red_green_pass(queue):
    """red_green_pass 不算 frozen — 应进 ranked."""
    hyps = [
        {"id": "H-rgp", "verification_status": "red_green_pass", "confidence_level": "medium", "risk_if_wrong": "medium"},
    ]
    result = queue.rank(hyps)
    assert len(result.ranked) == 1
    assert result.ranked[0].hypothesis_id == "H-rgp"


def test_skip_frozen_does_not_skip_challenged(queue):
    """challenged 不算 frozen — 应进 ranked (它正在被质疑还没结论)."""
    hyps = [
        {"id": "H-chal", "verification_status": "untested", "status": "challenged",
         "confidence_level": "low", "risk_if_wrong": "high"},
    ]
    result = queue.rank(hyps)
    assert len(result.ranked) == 1


def test_skip_frozen_with_focus_count(queue):
    """skip_frozen + focus_count 一起 — focus_count 在 frozen 跳过后才数."""
    hyps = [
        {"id": "H-active-1", "confidence_level": "low", "risk_if_wrong": "high"},
        {"id": "H-falsified-1", "verification_status": "falsified"},
        {"id": "H-active-2", "confidence_level": "low", "risk_if_wrong": "high"},
        {"id": "H-falsified-2", "verification_status": "falsified"},
        {"id": "H-active-3", "confidence_level": "low", "risk_if_wrong": "high"},
    ]
    result = queue.rank(hyps, focus_count=2)
    assert len(result.ranked) == 2  # 应是 2 个 active, 不被 falsified 占位
    for e in result.ranked:
        assert "H-active" in e.hypothesis_id


def test_summary_counts_skipped_frozen(queue):
    """summary 应反映 skip 数."""
    hyps = [
        {"id": "H-a", "confidence_level": "low", "risk_if_wrong": "high"},
        {"id": "H-f", "verification_status": "falsified"},
    ]
    result = queue.rank(hyps)
    assert "ranked 1" in result.summary
    assert "skipped 1" in result.summary
