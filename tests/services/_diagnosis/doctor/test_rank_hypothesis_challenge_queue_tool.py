# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T13:50:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest RankHypothesisChallengeQueueTool — 真扫 yaml dir + 调 ChallengeQueue + 排序输出 + ctx.scratch 留完整结果"
# [OMNI] why="V4-2 接通 ChallengeQueue 跟 MetaDiagnosticAgent. 工具是 SingleToolRouter 包装, 加 IO 层. 验工具行为 + 注册 + meta_diagnostic SPEC 含"
# [OMNI] tags=test,pytest,doctor,tools,challenge-queue,meta-diagnostic,V4
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_rank_hypothesis_challenge_queue_tool.py"
"""pytest RankHypothesisChallengeQueueTool.

测 case:
- 边界 (空 dir / 不存在 dir / 项目根外路径)
- 真用 (扫 dir 加载 yaml + 排序输出)
- focus_count 截断
- applies_to 触发 b 类 / 不传 applies_to 不触发 b
- ctx.scratch 留完整结果 (含 hypothesis_dict)
- 工具注册到 TOOL_REGISTRY
- MetaDiagnosticAgent SPEC.tools 含本工具
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from omnicompany.packages.services._diagnosis.doctor.tools.rank_hypothesis_challenge_queue import (
    RankHypothesisChallengeQueueTool,
)


class FakeCtx:
    def __init__(self):
        self.scratch = {}


def _new_tool():
    """绕 __init__ (需 bus), 直接 __new__."""
    return RankHypothesisChallengeQueueTool.__new__(RankHypothesisChallengeQueueTool)


@pytest.fixture
def project_root(tmp_path, monkeypatch):
    """模拟项目根含 src/omnicompany + docs."""
    (tmp_path / "src" / "omnicompany").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    from omnicompany.packages.services._diagnosis.doctor.tools import (
        rank_hypothesis_challenge_queue as tool_module,
    )
    monkeypatch.setattr(tool_module, "_PROJECT_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def hyp_dir(project_root):
    """tmp 项目根写 4 假设 yaml."""
    rel = "data/services/doctor/hypotheses"
    full = project_root / rel
    full.mkdir(parents=True)

    # H-A: a 类触发 (low+high)
    (full / "H-A.yaml").write_text(yaml.safe_dump({
        "id": "H-A", "statement": "x", "applies_to": "worker",
        "confidence_level": "low", "risk_if_wrong": "high",
        "verification_status": "untested",
    }, allow_unicode=True), encoding="utf-8")

    # H-B: b 类触发 (untested + applies_to=worker)
    (full / "H-B.yaml").write_text(yaml.safe_dump({
        "id": "H-B", "statement": "y", "applies_to": "worker",
        "confidence_level": "medium", "risk_if_wrong": "medium",
        "verification_status": "untested",
    }, allow_unicode=True), encoding="utf-8")

    # H-C: c 类基础假设
    (full / "H-C.yaml").write_text(yaml.safe_dump({
        "id": "H-C", "statement": "z", "applies_to": "agent",
        "confidence_level": "medium", "risk_if_wrong": "medium",
    }, allow_unicode=True), encoding="utf-8")

    # H-d1/d2/d3 依赖 H-C
    for i in range(1, 4):
        (full / f"H-d{i}.yaml").write_text(yaml.safe_dump({
            "id": f"H-d{i}", "statement": "dep", "applies_to": "agent",
            "dependent_hypotheses": ["H-C"],
        }, allow_unicode=True), encoding="utf-8")

    return rel


# ── 边界 ──

def test_no_dir_returns_no_dir(project_root):
    tool = _new_tool()
    out = tool._execute(
        {"hypotheses_dir": "data/services/doctor/no_such_dir"},
        FakeCtx(),
    )
    assert "NO_DIR" in out


def test_empty_dir_returns_empty(project_root):
    rel = "data/services/doctor/hypotheses_empty"
    (project_root / rel).mkdir(parents=True)
    tool = _new_tool()
    out = tool._execute({"hypotheses_dir": rel}, FakeCtx())
    assert "EMPTY_DIR" in out


def test_path_outside_project_root_rejected(project_root):
    from omnicompany.packages.services._core.agent.routers.single_tool import ToolExecutionError
    tool = _new_tool()
    with pytest.raises(ToolExecutionError, match="必须在项目根内"):
        tool._execute({"hypotheses_dir": "../outside"}, FakeCtx())


# ── 真用 ──

def test_loads_and_ranks_with_applies_to(hyp_dir):
    """传 applies_to=worker → b 类触发 H-A 跟 H-B; H-C c 类 (3 依赖)."""
    tool = _new_tool()
    out = tool._execute(
        {"hypotheses_dir": hyp_dir, "applies_to": "worker", "focus_count": 5},
        FakeCtx(),
    )
    assert "RANKED_5" in out
    assert "loaded=6" in out
    # H-A 应排第 1 (a=1000 + b=100 触发, applies_to=worker 命中)
    lines = out.split("\n")
    first_data_line = [ln for ln in lines if ln.startswith("  H-")][0]
    assert "H-A" in first_data_line
    # H-A score 应 ≥ 1100 (a + b)
    assert "score=1100" in first_data_line


def test_without_applies_to_does_not_trigger_b(hyp_dir):
    """不传 applies_to → b 类不触发, H-A 只触发 a (1000)."""
    tool = _new_tool()
    out = tool._execute(
        {"hypotheses_dir": hyp_dir, "focus_count": 5},
        FakeCtx(),
    )
    lines = out.split("\n")
    first_data_line = [ln for ln in lines if ln.startswith("  H-")][0]
    assert "H-A" in first_data_line
    # H-A 应 score=1000 (只 a, b 不触发)
    assert "score=1000" in first_data_line


def test_focus_count_truncates(hyp_dir):
    """focus_count=2 → 只返前 2."""
    tool = _new_tool()
    out = tool._execute(
        {"hypotheses_dir": hyp_dir, "applies_to": "worker", "focus_count": 2},
        FakeCtx(),
    )
    assert "RANKED_2" in out
    # 应含 "showing top 2 of 6" 提示
    assert "showing top 2 of 6" in out


def test_focus_count_caps_at_30(hyp_dir):
    """focus_count > 30 应 cap 到 30."""
    tool = _new_tool()
    out = tool._execute(
        {"hypotheses_dir": hyp_dir, "focus_count": 99999},
        FakeCtx(),
    )
    # 6 假设全返
    assert "RANKED_6" in out


def test_depended_by_threshold_custom(hyp_dir):
    """自定阈值 = 2 → H-C 仍触发 (3 依赖 ≥ 2)."""
    tool = _new_tool()
    out = tool._execute(
        {"hypotheses_dir": hyp_dir, "depended_by_threshold": 2},
        FakeCtx(),
    )
    # 应有 H-C 的 c 类信号
    assert "H-C" in out


# ── ctx.scratch ──

def test_scratch_holds_full_result_with_hypothesis_dict(hyp_dir):
    """ctx.scratch 留完整 ranked list 含 hypothesis_dict (agent 后续读)."""
    tool = _new_tool()
    ctx = FakeCtx()
    tool._execute(
        {"hypotheses_dir": hyp_dir, "applies_to": "worker", "focus_count": 3},
        ctx,
    )
    assert "last_challenge_queue_result" in ctx.scratch
    ranked = ctx.scratch["last_challenge_queue_result"]
    assert len(ranked) == 3
    # 第一条应是 H-A (a + b 触发)
    assert ranked[0]["hypothesis_id"] == "H-A"
    assert ranked[0]["priority_score"] == 1100
    # hypothesis_dict 含原 yaml 字段
    assert ranked[0]["hypothesis_dict"]["statement"] == "x"
    assert ranked[0]["hypothesis_dict"]["applies_to"] == "worker"


# ── 注册 ──

def test_tool_registered():
    """import doctor.tools 后, 本工具应注册."""
    from omnicompany.packages.services._core.agent.configurable import TOOL_REGISTRY
    from omnicompany.packages.services._diagnosis.doctor import tools  # noqa: F401
    assert "rank_hypothesis_challenge_queue" in TOOL_REGISTRY


# ── MetaDiagnosticAgent SPEC 含本工具 ──

def test_meta_diagnostic_spec_includes_tool():
    """MetaDiagnosticAgent SPEC.tools 含 rank_hypothesis_challenge_queue (V4-2 接通点)."""
    from omnicompany.packages.services._diagnosis.doctor.agents import META_DIAGNOSTIC_SPEC
    assert "rank_hypothesis_challenge_queue" in META_DIAGNOSTIC_SPEC.tools


# ── V7 2026-05-07: tool 透传 skip_frozen ──

def test_tool_default_skips_frozen_hypotheses(project_root):
    """工具默认 include_frozen=False — falsified 假设跳过."""
    rel = "data/services/doctor/hypotheses_v7"
    full = project_root / rel
    full.mkdir(parents=True)
    (full / "H-active.yaml").write_text(yaml.safe_dump({
        "id": "H-active", "confidence_level": "low", "risk_if_wrong": "high",
    }, allow_unicode=True), encoding="utf-8")
    (full / "H-falsified.yaml").write_text(yaml.safe_dump({
        "id": "H-falsified", "verification_status": "falsified",
        "confidence_level": "low", "risk_if_wrong": "high",
    }, allow_unicode=True), encoding="utf-8")

    tool = _new_tool()
    out = tool._execute({"hypotheses_dir": rel}, FakeCtx())
    assert "H-active" in out
    assert "H-falsified" not in out


def test_tool_include_frozen_includes_falsified(project_root):
    """include_frozen=True 时 falsified 假设进 ranked."""
    rel = "data/services/doctor/hypotheses_v7_inc"
    full = project_root / rel
    full.mkdir(parents=True)
    (full / "H-falsified.yaml").write_text(yaml.safe_dump({
        "id": "H-falsified", "verification_status": "falsified",
    }, allow_unicode=True), encoding="utf-8")

    tool = _new_tool()
    out = tool._execute(
        {"hypotheses_dir": rel, "include_frozen": True},
        FakeCtx(),
    )
    assert "H-falsified" in out


def test_meta_diagnostic_prompt_mentions_rank_tool():
    """MetaDiagnosticAgent prompt 应说明何时调本工具."""
    from omnicompany.packages.services._diagnosis.doctor.agents import META_DIAGNOSTIC_SPEC
    prompt_path = Path(__file__).resolve().parents[4] / META_DIAGNOSTIC_SPEC.prompt_path
    text = prompt_path.read_text(encoding="utf-8")
    assert "rank_hypothesis_challenge_queue" in text
    assert "死局" in text  # prompt 应说"死局时调"
    assert "schema §三步骤 1-2" in text or "步骤 1-2" in text
