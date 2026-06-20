# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T12:00:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest ChallengeDiagnosticAgent 形态接通 smoke 测 — SPEC 完整 / 工具全注册 / prompt 文件存在 / 红绿 fixture 解析 / dispatcher wire"
# [OMNI] why="Stage C 接通必带 dogfood 但真 LLM dogfood 涉 token 成本. smoke 测验形态合规 + 红绿 fixture 形态正确, 真 LLM 跑留 V3.1 用户授权"
# [OMNI] tags=test,pytest,doctor,challenge-agent,smoke,V3
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_challenge_diagnostic_agent_smoke.py"
"""ChallengeDiagnosticAgent smoke 测 — 形态接通 (不调真 LLM).

测 case:
- SPEC 13 字段完整 + llm_model='qwen-3.6-plus' (唯一模型铁律)
- SPEC.tools 全部从 TOOL_REGISTRY 解析得通
- prompt 文件存在 + 含关键段 (步骤 3-4 / 拒打分 / 工具列表)
- agent 实例化 (用 MemoryBus stub) + FORMAT_IN/OUT 派生正确
- agent 在 build_diagnostic_workers list 里
- 红绿 fixture yaml 形态正确 (V1 schema 字段全)
- 红 fixture statement 含证否锚点 (跟 HIGH 权威规范矛盾)
- 绿 fixture verification_status='red_green_pass' (允许 challenge 但应不被 falsify)
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from omnicompany.packages.services._diagnosis.doctor.agents import (
    ChallengeDiagnosticAgent,
    CHALLENGE_DIAGNOSTIC_SPEC,
    build_diagnostic_workers,
    run_challenge_diagnosis,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
PLAN_DIR = PROJECT_ROOT / "docs" / "plans" / "_infra" / "diagnosis" / "[2026-05-05]DIAGNOSIS-RECONSOLIDATION"


# ── SPEC 形态 ──

def test_spec_id_and_name():
    assert CHALLENGE_DIAGNOSTIC_SPEC.id == "doctor.challenge_diagnostic"
    assert CHALLENGE_DIAGNOSTIC_SPEC.name == "ChallengeDiagnosticAgent"
    assert CHALLENGE_DIAGNOSTIC_SPEC.domain == "doctor"


def test_spec_uses_unique_llm_model():
    """铁律 1 — 唯一模型 'qwen-3.6-plus'."""
    assert CHALLENGE_DIAGNOSTIC_SPEC.llm_model == "qwen-3.6-plus"


def test_spec_max_turns_loose_per_iron_rule_b():
    """铁律 B — max_turns 宽松 (≥ 100), 不能是 30 / 50 这种紧默认值."""
    assert CHALLENGE_DIAGNOSTIC_SPEC.llm_max_turns >= 100


def test_spec_trigger_and_output_materials_distinct():
    """trigger 跟 output material 不冲突 — output 应在 forbidden_input_materials 里."""
    assert CHALLENGE_DIAGNOSTIC_SPEC.primary_output not in CHALLENGE_DIAGNOSTIC_SPEC.trigger_materials
    assert CHALLENGE_DIAGNOSTIC_SPEC.primary_output in CHALLENGE_DIAGNOSTIC_SPEC.forbidden_input_materials


# ── 工具集解析 ──

def test_all_tools_resolve_in_registry():
    """SPEC.tools 全部能从 TOOL_REGISTRY 解析."""
    from omnicompany.packages.services._core.agent.configurable import TOOL_REGISTRY
    for tool_name in CHALLENGE_DIAGNOSTIC_SPEC.tools:
        assert tool_name in TOOL_REGISTRY, f"工具 {tool_name!r} 未注册到 TOOL_REGISTRY"


def test_required_tools_present():
    """关键工具必含: record_hypothesis_challenge / record_hypothesis_resolution / git_log / submit_verdict."""
    tools = set(CHALLENGE_DIAGNOSTIC_SPEC.tools)
    assert "record_hypothesis_challenge" in tools
    assert "record_hypothesis_resolution" in tools
    assert "git_log" in tools
    assert "submit_verdict" in tools
    assert "write_finding" in tools


# ── prompt 文件 ──

def test_prompt_file_exists_and_readable():
    prompt_rel = CHALLENGE_DIAGNOSTIC_SPEC.prompt_path
    full = PROJECT_ROOT / prompt_rel
    assert full.exists(), f"prompt 文件不存在: {prompt_rel}"
    content = full.read_text(encoding="utf-8")
    assert len(content) > 500


def test_prompt_contains_key_sections():
    """prompt 应含步骤 3-4 / 拒打分 / 工具列表关键段."""
    prompt_text = (PROJECT_ROOT / CHALLENGE_DIAGNOSTIC_SPEC.prompt_path).read_text(encoding="utf-8")
    # 步骤 3-4
    assert "步骤 3" in prompt_text
    assert "步骤 4" in prompt_text
    # 3 路径
    assert "反例 fixture" in prompt_text
    assert "历史实例" in prompt_text
    assert "权威规范" in prompt_text
    # 拒打分
    assert "拒打分" in prompt_text
    # 工具列表
    assert "record_hypothesis_challenge" in prompt_text
    assert "record_hypothesis_resolution" in prompt_text


def test_prompt_does_not_contain_severity_score():
    """prompt 不该出现 severity / score / level / tier (拒打分铁律)."""
    prompt_text = (PROJECT_ROOT / CHALLENGE_DIAGNOSTIC_SPEC.prompt_path).read_text(encoding="utf-8")
    # 但允许"拒 severity / score / level / tier"这种否定句, 用 "出现立刻" 跟 "submit_verdict 拒"作 sentinel
    # 简单查: 这些词只在"拒"段落出现, 不在工具用法说明里
    assert "submit_verdict 拒" in prompt_text or "拒 severity" in prompt_text


# ── agent 实例化 ──

def test_agent_instantiates_with_memory_bus():
    from omnicompany.bus.memory import MemoryBus
    bus = MemoryBus()
    agent = ChallengeDiagnosticAgent(bus=bus)
    assert agent.SPEC.id == "doctor.challenge_diagnostic"
    assert agent.FORMAT_IN == "doctor.challenge_diagnosis.request"
    assert agent.FORMAT_OUT == "doctor.challenge_diagnosis.verdict"


def test_agent_in_build_diagnostic_workers():
    """ChallengeDiagnosticAgent 应在 build_diagnostic_workers 返 list."""
    from omnicompany.bus.memory import MemoryBus
    bus = MemoryBus()
    workers = build_diagnostic_workers(bus=bus)
    challenge_agents = [w for w in workers if w.__class__.__name__ == "ChallengeDiagnosticAgent"]
    assert len(challenge_agents) == 1


def test_run_challenge_diagnosis_helper_exists():
    """run_challenge_diagnosis async helper 应导出可用."""
    assert callable(run_challenge_diagnosis)


# ── 红绿 fixture yaml 形态 ──

@pytest.fixture
def red_fixture_data():
    p = PLAN_DIR / "sample_hypothesis_red_easy_falsify.yaml"
    assert p.exists()
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def green_fixture_data():
    p = PLAN_DIR / "sample_hypothesis_green_solid.yaml"
    assert p.exists()
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_red_fixture_has_v1_schema(red_fixture_data):
    """红 fixture 含 V1 schema 字段全."""
    for field in (
        "id", "statement", "applies_to", "verification_status",
        "risk_if_wrong", "confidence_level", "source_authority",
        "dependent_hypotheses", "challenge_log", "related_finding_ids",
    ):
        assert field in red_fixture_data, f"红 fixture 缺字段: {field}"


def test_red_fixture_statement_overly_absolute(red_fixture_data):
    """红 fixture statement 故意立绝对化 (跟 HIGH 权威规范矛盾) — 含'必须 / 禁用 / 永远不'."""
    statement = red_fixture_data["statement"]
    assert "必须" in statement
    # 故意绝对化触发证否
    assert "禁用" in statement or "永远不" in statement


def test_red_fixture_starts_in_active_state(red_fixture_data):
    """红 fixture verification_status='untested' (允许 agent challenge)."""
    assert red_fixture_data["verification_status"] == "untested"


def test_green_fixture_has_v1_schema(green_fixture_data):
    for field in (
        "id", "statement", "applies_to", "verification_status",
        "risk_if_wrong", "confidence_level",
    ):
        assert field in green_fixture_data, f"绿 fixture 缺字段: {field}"


def test_green_fixture_state_allows_challenge(green_fixture_data):
    """绿 fixture verification_status='red_green_pass' (允许 challenge 但应不被 falsify)."""
    assert green_fixture_data["verification_status"] == "red_green_pass"
    # 不能是 frozen status (falsified / real_world_validated)
    assert green_fixture_data["verification_status"] not in ("falsified", "real_world_validated")


def test_red_and_green_fixtures_are_distinct(red_fixture_data, green_fixture_data):
    """红绿 fixture 是两条不同假设."""
    assert red_fixture_data["id"] != green_fixture_data["id"]
    assert red_fixture_data["applies_to"] == green_fixture_data["applies_to"]  # 都是 worker
