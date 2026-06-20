# [OMNI] origin=claude-code ts=2026-06-12 type=infra
# [OMNI] material_id="material:tests.governance.plan_resolution.py"
"""计划归属解析的契约测试 — 治理覆盖表优先, 未治理退回前缀规则。"""

from omnicompany.core.projects_registry import resolve_project_plans

CATALOGUE = [
    {"id": "gameplay_system/[2026-04-30]gameplay_system-KB-INGEST"},
    {"id": "gameplay_system/[2026-04-11]gameplay_system-TABLE-PIPELINE-REFACTOR"},
    {"id": "gameplay_system/figma-to-prefab/plans/[2026-04-24]a2-comparison"},
    {"id": "dashboard/[2026-05-23]BOSS-SIGHT"},
]


def test_override_wins_over_prefix():
    gov = {
        # 物理在 gameplay_system/ 下, 但治理判给 omnidashboard
        "gameplay_system/[2026-04-30]gameplay_system-KB-INGEST": {"project": "omnidashboard"},
    }
    got = resolve_project_plans("omnidashboard", ["dashboard"], CATALOGUE, gov)
    ids = {x["id"] for x in got}
    assert "gameplay_system/[2026-04-30]gameplay_system-KB-INGEST" in ids
    assert "dashboard/[2026-05-23]BOSS-SIGHT" in ids  # 未治理 → 前缀规则兜底


def test_governed_null_excluded_everywhere():
    gov = {"gameplay_system/[2026-04-30]gameplay_system-KB-INGEST": {"project": None}}
    got = resolve_project_plans("gameplay_system-config", ["gameplay_system"], CATALOGUE, gov)
    ids = {x["id"] for x in got}
    # 治理说"不属于任何项目" → 即使前缀命中也排除
    assert "gameplay_system/[2026-04-30]gameplay_system-KB-INGEST" not in ids
    # 同目录未治理的照旧前缀兜底
    assert "gameplay_system/[2026-04-11]gameplay_system-TABLE-PIPELINE-REFACTOR" in ids


def test_prefix_fallback_exact_and_slash_boundary():
    got = resolve_project_plans("gameplay_system-prefab", ["gameplay_system/figma-to-prefab"], CATALOGUE, {})
    ids = {x["id"] for x in got}
    assert ids == {"gameplay_system/figma-to-prefab/plans/[2026-04-24]a2-comparison"}
    # 前缀必须落在路径段边界: "gameplay_system/figma-to" 不该命中
    got2 = resolve_project_plans("x", ["gameplay_system/figma-to"], CATALOGUE, {})
    assert got2 == []
