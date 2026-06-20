# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T03:35:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest 单元测 doctor PytestSkeletonBuilder — 修 AP-018+AP-019"
# [OMNI] why="阶段 10 修 3: builder 没自测. 立 pytest 测产 skeleton 边界 case + 内容合规"
# [OMNI] tags=test,pytest,builder,unit-test
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_pytest_skeleton_builder.py"
"""pytest 单元测 doctor PytestSkeletonBuilder.

测 case:
- 边界 (空 uncovered list / team_path 不存在)
- skeleton 内容合规 (含红绿基线骨架 + OMNI 头 + status=skeleton)
- helper API
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnicompany.packages.services._diagnosis.doctor.builders import (
    PytestSkeletonBuilder,
    build_pytest_skeleton_for_team,
)


@pytest.fixture
def project_root() -> Path:
    here = Path(__file__).resolve()
    for p in (here, *here.parents):
        if (p / "src" / "omnicompany").is_dir() and (p / "docs").is_dir():
            return p
    raise RuntimeError("project root not found")


# ── 边界 case ──

def test_build_empty_uncovered_list(project_root):
    """空 uncovered list 应不产 skeleton + 含 notes."""
    builder = PytestSkeletonBuilder(project_root=project_root)
    result = builder.build(
        team_path="src/omnicompany/packages/services/_utility/csv_to_md/",
        uncovered_material_ids=[],
    )
    assert result.skeletons == []
    assert any("无 uncovered" in n for n in result.notes)


def test_build_team_path_not_exists(project_root):
    """team_path 不存在 → 0 skeleton + notes 含错误."""
    builder = PytestSkeletonBuilder(project_root=project_root)
    result = builder.build(
        team_path="src/never/exists/",
        uncovered_material_ids=["a.b"],
    )
    assert result.skeletons == []
    assert any("不存在" in n for n in result.notes)


# ── 真用 case ──

def test_build_csv_to_md_skeletons(project_root):
    """绿样本: 给 csv_to_md 3 个 Material 产 3 份 skeleton."""
    builder = PytestSkeletonBuilder(project_root=project_root)
    result = builder.build(
        team_path="src/omnicompany/packages/services/_utility/csv_to_md/",
        uncovered_material_ids=["csv_to_md.file_input", "csv_to_md.parsed_rows", "csv_to_md.md_output"],
    )
    assert len(result.skeletons) == 3
    # 每份 skeleton 含必要字段
    for sk in result.skeletons:
        assert sk.material_id != ""
        assert sk.target_path.endswith(".py")
        assert "/tests/" in sk.target_path
        assert sk.content != ""


def test_skeleton_content_has_red_green_structure(project_root):
    """skeleton 内容含红绿基线骨架 (3 测试函数)."""
    builder = PytestSkeletonBuilder(project_root=project_root)
    result = builder.build(
        team_path="src/omnicompany/packages/services/_utility/csv_to_md/",
        uncovered_material_ids=["csv_to_md.file_input"],
    )
    sk = result.skeletons[0]
    # 红绿基线 3 函数
    assert "_green" in sk.content
    assert "_red" in sk.content
    assert "_discrimination" in sk.content
    # OMNI 头
    assert "[OMNI]" in sk.content
    # skeleton 标记
    assert "status=skeleton" in sk.content
    # TODO 提示
    assert "TODO" in sk.content
    # pytest import
    assert "import pytest" in sk.content


def test_skeleton_safe_filename(project_root):
    """material_id 含 . 应转 _ 用作 python identifier."""
    builder = PytestSkeletonBuilder(project_root=project_root)
    result = builder.build(
        team_path="src/omnicompany/packages/services/_utility/csv_to_md/",
        uncovered_material_ids=["csv_to_md.file_input"],
    )
    sk = result.skeletons[0]
    # target_path 应含 csv_to_md_file_input (. 转 _)
    assert "csv_to_md_file_input" in sk.target_path
    # content 含 def test_csv_to_md_file_input_green
    assert "def test_csv_to_md_file_input_green" in sk.content


# ── helper API ──

def test_build_pytest_skeleton_for_team_helper(project_root):
    """helper API 返 dict 可序列化."""
    result = build_pytest_skeleton_for_team(
        team_path="src/omnicompany/packages/services/_utility/csv_to_md/",
        uncovered_material_ids=["csv_to_md.file_input"],
    )
    assert isinstance(result, dict)
    assert "team_path" in result
    assert "skeletons" in result
    assert isinstance(result["skeletons"], list)
    assert len(result["skeletons"]) == 1
    sk = result["skeletons"][0]
    assert "target_path" in sk
    assert "content" in sk
    assert "material_id" in sk


# ── 红绿区分 ──

def test_skeleton_count_matches_uncovered_count(project_root):
    """skeleton 数严格等于 uncovered material 数."""
    builder = PytestSkeletonBuilder(project_root=project_root)
    cases = [1, 2, 3, 5]
    for n in cases:
        ids = [f"test.material_{i}" for i in range(n)]
        result = builder.build(
            team_path="src/omnicompany/packages/services/_utility/csv_to_md/",
            uncovered_material_ids=ids,
        )
        assert len(result.skeletons) == n, f"expected {n}, got {len(result.skeletons)}"
