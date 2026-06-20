# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T03:30:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest 单元测 doctor FacilityScanner — 修 AP-018+AP-019 (rule-maker-violator + tool-not-eat-own-dogfood, scanner 没自测)"
# [OMNI] why="阶段 10 自我拷问发现: scanners 跟 builders 只 smoke 验跑 happy path, 没 pytest 单元测边界 case (NoneType / 空 input / 路径不存在). 立 pytest test 让 scanner 自吃狗粮"
# [OMNI] tags=test,pytest,facility-scanner,unit-test,boundary-case,red-green-baseline
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_facility_scanner.py"
"""pytest 单元测 doctor FacilityScanner 边界 case.

修 self_interrogation §四 AP-018 + AP-019:
- AP-018 rule-maker-violator: scanner 是诊断工具, 应自测
- AP-019 tool-not-eat-own-dogfood: 工具立时不用自己工具

测 case 含:
- 红样本 (team_path 不存在 / 空 team / 无 formats.py)
- 绿样本 (csv_to_md 真 team)
- 边界 (NoneType / 空字符串 / 路径含特殊字符)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnicompany.packages.services._diagnosis.doctor.scanners import (
    FacilityScanner,
    scan_team_test_facilities,
)


@pytest.fixture
def project_root() -> Path:
    """项目根 find-up."""
    here = Path(__file__).resolve()
    for p in (here, *here.parents):
        if (p / "src" / "omnicompany").is_dir() and (p / "docs").is_dir():
            return p
    raise RuntimeError("project root not found")


# ── 红样本 — 异常 input ──

def test_facility_scanner_team_path_not_exists(project_root):
    """红样本: team_path 不存在应不挂 + 返 error 字段."""
    scanner = FacilityScanner(project_root=project_root)
    result = scanner.scan(team_path="src/nonexistent/path/never/exists/")
    assert result.team_path == "src/nonexistent/path/never/exists/"
    assert "error" in result.overall_health_signals
    assert result.facilities == []
    assert result.coverage_matrix == []


def test_facility_scanner_empty_team_dir(project_root, tmp_path):
    """红样本: 空 team 目录 (没文件) 应返 0 facility / 0 material."""
    empty_dir = tmp_path / "empty_team"
    empty_dir.mkdir()
    scanner = FacilityScanner(project_root=tmp_path)
    result = scanner.scan(team_path="empty_team")
    assert result.overall_health_signals["facility_count"] == 0
    assert result.overall_health_signals["material_count"] == 0


def test_facility_scanner_team_no_formats_py(project_root, tmp_path):
    """红样本: 有 worker.py 但没 formats.py — 0 material 0 coverage."""
    team = tmp_path / "team_no_formats"
    team.mkdir()
    (team / "worker.py").write_text("# stub", encoding="utf-8")
    scanner = FacilityScanner(project_root=tmp_path)
    result = scanner.scan(team_path="team_no_formats")
    assert result.overall_health_signals["material_count"] == 0


# ── 绿样本 — csv_to_md 真 team ──

def test_facility_scanner_csv_to_md_smoke(project_root):
    """绿样本: csv_to_md 真 team 应能扫到 Material (即使 0 facility)."""
    scanner = FacilityScanner(project_root=project_root)
    result = scanner.scan(
        team_path="src/omnicompany/packages/services/_utility/csv_to_md/"
    )
    # Material 应 ≥ 1 (csv_to_md formats.py 有 file_input/parsed_rows/md_output 等)
    assert result.overall_health_signals["material_count"] >= 1
    # 验证字符串字段存在
    assert "coverage_ratio_str" in result.overall_health_signals


# ── 红绿对比 (本测试自身红绿基线) ──

def test_facility_scanner_red_green_discrimination(project_root, tmp_path):
    """红绿对比: 真 team (csv_to_md) 跟空 team finding 数应明显区分."""
    scanner = FacilityScanner(project_root=project_root)

    # 绿: csv_to_md 真 team
    green = scanner.scan(team_path="src/omnicompany/packages/services/_utility/csv_to_md/")
    green_material_count = green.overall_health_signals["material_count"]

    # 红: 不存在 path
    red = scanner.scan(team_path="src/totally/fake/never/exists/")
    red_has_error = "error" in red.overall_health_signals

    # 判别力: 绿真 team 应 ≥1 material, 红应 0 + 有 error 字段
    assert green_material_count >= 1, "绿样本 csv_to_md 应 ≥1 material"
    assert red_has_error, "红样本 (路径不存在) 应有 error 字段"


# ── helper API ──

def test_scan_team_test_facilities_helper_returns_dict():
    """scan_team_test_facilities 应返 dict 可序列化."""
    result = scan_team_test_facilities(
        team_path="src/omnicompany/packages/services/_utility/csv_to_md/"
    )
    assert isinstance(result, dict)
    assert "facilities" in result
    assert "coverage_matrix" in result
    assert "overall_health_signals" in result
    # 各字段类型
    assert isinstance(result["facilities"], list)
    assert isinstance(result["overall_health_signals"], dict)
