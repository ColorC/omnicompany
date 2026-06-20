# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T06:00:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest 单元测 HypothesisAgentPromptBuilder — 据假设产 prompt skeleton (修 V1 大动作 plan §一第 7 条)"
# [OMNI] why="跟其他 doctor builder/scanner pytest 单元测同模式. 修 AP-019 (tool-not-eat-own-dogfood) — builder 自吃狗粮"
# [OMNI] tags=test,pytest,builder,hypothesis-agent,unit-test
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_hypothesis_agent_prompt_builder.py"
"""pytest 单元测 HypothesisAgentPromptBuilder.

测 case:
- 边界 (空 list / 缺字段 / 非 dict input)
- 真用 (典型假设 dict)
- skeleton 内容合规 (含 OMNI 头 / status=skeleton / 假设 id 嵌入 / TODO 提示)
"""
from __future__ import annotations

import pytest

from omnicompany.packages.services._diagnosis.doctor.builders import (
    HypothesisAgentPromptBuilder,
    HypothesisAgentPromptSkeleton,
)


@pytest.fixture
def sample_hypothesis():
    return {
        "id": "H-2026-05-07-001",
        "source_kind": "spec",
        "source_path": "docs/standards/concepts/worker.md",
        "source_excerpt": "Worker 必有 FORMAT_OUT (R-01)",
        "statement": "任意 Worker 子类必须显式声明 FORMAT_OUT 类属性, 不得继承默认或留空.",
        "motivation": "Worker 跟 omnicompany 总线交互的契约就是 FORMAT_OUT.",
        "applies_to": "worker",
        "evidence_query": "看 worker class 体内有没 FORMAT_OUT = 赋值",
        "status": "active",
        "tags": [],
        "confidence_level": "medium",
        "source_authority": "LOW",
        "verification_status": "red_green_pass",
        "risk_if_wrong": "high",
        "related_anti_pattern_ids": ["AP-007"],
    }


# ── 边界 case ──

def test_build_empty_list():
    """空 hypotheses list 不产 skeleton + 含 notes."""
    b = HypothesisAgentPromptBuilder()
    result = b.build([])
    assert result.skeletons == []
    assert any("空" in n for n in result.notes)


def test_build_non_dict_input():
    """非 dict input 跳过 + 加 note."""
    b = HypothesisAgentPromptBuilder()
    result = b.build(["string", 42, None])
    assert result.skeletons == []
    assert len(result.notes) >= 1


def test_build_missing_id():
    """缺 id 假设跳过 + 加 note."""
    b = HypothesisAgentPromptBuilder()
    result = b.build([{"statement": "no id"}])
    assert result.skeletons == []


def test_build_missing_statement():
    """缺 statement 假设跳过."""
    b = HypothesisAgentPromptBuilder()
    result = b.build([{"id": "H-no-statement"}])
    assert result.skeletons == []


# ── 真用 case ──

def test_build_typical_hypothesis(sample_hypothesis):
    """典型假设产 1 skeleton 含必要字段."""
    b = HypothesisAgentPromptBuilder()
    result = b.build([sample_hypothesis])
    assert len(result.skeletons) == 1
    sk = result.skeletons[0]
    assert sk.hypothesis_id == "H-2026-05-07-001"
    assert "FORMAT_OUT" in sk.hypothesis_statement
    assert sk.target_path_suggestion.endswith("_prompt.md")
    assert "agents/" in sk.target_path_suggestion


def test_build_skeleton_has_omni_header(sample_hypothesis):
    """skeleton 含 OMNI 头."""
    b = HypothesisAgentPromptBuilder()
    result = b.build([sample_hypothesis])
    content = result.skeletons[0].content
    assert "[OMNI]" in content
    assert "status=skeleton" in content
    assert "agent=doctor.builder" in content


def test_build_skeleton_has_hypothesis_archive(sample_hypothesis):
    """skeleton 嵌入假设档案 (含 statement / motivation / applies_to / risk)."""
    b = HypothesisAgentPromptBuilder()
    result = b.build([sample_hypothesis])
    content = result.skeletons[0].content
    assert sample_hypothesis["statement"] in content
    assert sample_hypothesis["motivation"] in content
    assert "applies_to: worker" in content
    assert "AP-007" in content
    assert "risk_if_wrong: high" in content


def test_build_skeleton_has_todo(sample_hypothesis):
    """skeleton 含 TODO 提示, 让调用方 review."""
    b = HypothesisAgentPromptBuilder()
    result = b.build([sample_hypothesis])
    content = result.skeletons[0].content
    assert "TODO" in content
    assert "调用方手工" in content or "review" in content


def test_build_multiple_hypotheses():
    """多个假设产多个 skeleton."""
    b = HypothesisAgentPromptBuilder()
    hyps = [
        {"id": f"H-test-{i}", "statement": f"假设 {i} 必须 X", "applies_to": "worker"}
        for i in range(3)
    ]
    result = b.build(hyps)
    assert len(result.skeletons) == 3
    ids = {sk.hypothesis_id for sk in result.skeletons}
    assert ids == {"H-test-0", "H-test-1", "H-test-2"}


def test_build_target_path_safe_id():
    """假设 id 含 - 应转 _ 用作文件名."""
    b = HypothesisAgentPromptBuilder()
    hyp = {"id": "H-2026-05-07-test", "statement": "test", "applies_to": "worker"}
    result = b.build([hyp])
    sk = result.skeletons[0]
    # filename 应 hypothesis_H_2026_05_07_test_prompt.md
    assert "H_2026_05_07_test" in sk.target_path_suggestion
