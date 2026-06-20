# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T11:10:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest RecordHypothesisChallengeTool + RecordHypothesisResolutionTool — 真读写 yaml + frozen status 拒 + sequence (challenge → resolution)"
# [OMNI] why="V3 ChallengeAgent 工具部分. 这两个 SingleToolRouter 包 ChallengeRecorder 加 IO 层 + 加 resolution 流程"
# [OMNI] tags=test,pytest,doctor,tools,challenge,resolution,V3
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_record_challenge_resolution_tools.py"
"""pytest RecordHypothesisChallengeTool + RecordHypothesisResolutionTool.

测 case:
- challenge 真读写 yaml + frozen 拒
- resolution 必先 challenged 才允许 (按 schema §三步骤 3-4 顺序)
- 顺序流程: untested → challenge → challenged → resolution → falsified
- 路径校验 (项目根外拒)
- yaml 不存在拒
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from omnicompany.packages.services._diagnosis.doctor.tools.record_hypothesis_challenge import (
    RecordHypothesisChallengeTool,
)
from omnicompany.packages.services._diagnosis.doctor.tools.record_hypothesis_resolution import (
    RecordHypothesisResolutionTool,
)
from omnicompany.packages.services._core.agent.routers.single_tool import (
    ToolExecutionError,
)


class FakeCtx:
    """简单 ctx fixture (跟 test_git_log_tool 同模式)."""
    def __init__(self):
        self.scratch = {}


def _make_ctx():
    return FakeCtx()


def _new_challenge_tool():
    """绕 __init__ (需 bus), 直接 __new__ 用于 _execute 单元测."""
    return RecordHypothesisChallengeTool.__new__(RecordHypothesisChallengeTool)


def _new_resolution_tool():
    return RecordHypothesisResolutionTool.__new__(RecordHypothesisResolutionTool)


@pytest.fixture
def project_root(tmp_path, monkeypatch):
    """模拟项目根 — 含 src/omnicompany 跟 docs 目录骨架, 让 _project_root() 返 tmp_path."""
    (tmp_path / "src" / "omnicompany").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    # patch _PROJECT_ROOT
    from omnicompany.packages.services._diagnosis.doctor.tools import (
        record_hypothesis_challenge,
        record_hypothesis_resolution,
    )
    monkeypatch.setattr(record_hypothesis_challenge, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(record_hypothesis_resolution, "_PROJECT_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def basic_hyp_yaml(project_root):
    """写一份最简单的 V1 假设 yaml 到 tmp 项目根."""
    rel_path = "data/services/doctor/hypotheses/H-test-001.yaml"
    full = project_root / rel_path
    full.parent.mkdir(parents=True)
    hyp = {
        "id": "H-test-001",
        "statement": "Worker 必须有 X",
        "applies_to": "worker",
        "status": "active",
        "verification_status": "untested",
        "challenge_log": [],
    }
    full.write_text(yaml.safe_dump(hyp, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return rel_path, full


# ── RecordHypothesisChallengeTool ──

def test_challenge_tool_records_to_yaml(basic_hyp_yaml):
    rel_path, full = basic_hyp_yaml
    tool = _new_challenge_tool()
    out = tool._execute(
        {"hypothesis_yaml_path": rel_path, "challenge_reason": "反例 fixture 显示假设不成立",
         "source": "red_green_test", "challenger_id": "agent:challenge"},
        _make_ctx(),
    )
    assert "RECORDED" in out
    assert "H-test-001" in out
    assert "'challenged'" in out
    # 真读 yaml 验
    with full.open(encoding="utf-8") as f:
        updated = yaml.safe_load(f)
    assert updated["status"] == "challenged"
    assert len(updated["challenge_log"]) == 1
    assert updated["challenge_log"][0]["challenge_reason"] == "反例 fixture 显示假设不成立"


def test_challenge_tool_rejects_missing_reason(basic_hyp_yaml):
    rel_path, _ = basic_hyp_yaml
    tool = _new_challenge_tool()
    with pytest.raises(ToolExecutionError, match="challenge_reason 必填"):
        tool._execute({"hypothesis_yaml_path": rel_path, "challenge_reason": ""}, _make_ctx())


def test_challenge_tool_rejects_missing_path():
    tool = _new_challenge_tool()
    with pytest.raises(ToolExecutionError, match="hypothesis_yaml_path 必填"):
        tool._execute({"hypothesis_yaml_path": "", "challenge_reason": "x"}, _make_ctx())


def test_challenge_tool_rejects_path_outside_project_root(project_root):
    tool = _new_challenge_tool()
    with pytest.raises(ToolExecutionError, match="必须在项目根内"):
        tool._execute(
            {"hypothesis_yaml_path": "../outside.yaml", "challenge_reason": "x"},
            _make_ctx(),
        )


def test_challenge_tool_rejects_nonexistent_yaml(project_root):
    tool = _new_challenge_tool()
    with pytest.raises(ToolExecutionError, match="假设 yaml 不存在"):
        tool._execute(
            {"hypothesis_yaml_path": "data/services/doctor/hypotheses/H-no-such.yaml",
             "challenge_reason": "x"},
            _make_ctx(),
        )


def test_challenge_tool_rejects_falsified_hypothesis(project_root):
    """已 falsified 的不允许再 challenge — 工具返 NOT_RECORDED 不抛."""
    rel_path = "data/services/doctor/hypotheses/H-falsified.yaml"
    full = project_root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(yaml.safe_dump({
        "id": "H-falsified",
        "verification_status": "falsified",
        "status": "falsified",
    }, allow_unicode=True), encoding="utf-8")

    tool = _new_challenge_tool()
    out = tool._execute(
        {"hypothesis_yaml_path": rel_path, "challenge_reason": "想再战"},
        _make_ctx(),
    )
    assert "NOT_RECORDED" in out
    assert "falsified" in out
    # yaml 不被改
    with full.open(encoding="utf-8") as f:
        re_loaded = yaml.safe_load(f)
    assert re_loaded["status"] == "falsified"


# ── RecordHypothesisResolutionTool ──

def test_resolution_tool_requires_challenged_status(basic_hyp_yaml):
    """status='active' (没经过 challenge) → resolution 拒."""
    rel_path, _ = basic_hyp_yaml
    tool = _new_resolution_tool()
    out = tool._execute(
        {"hypothesis_yaml_path": rel_path, "falsifying_evidence": "X 反例显示不成立",
         "method": "red_green_test", "falsifier_id": "agent:challenge"},
        _make_ctx(),
    )
    assert "REJECTED" in out
    assert "challenged" in out


def test_resolution_tool_falsifies_after_challenge(basic_hyp_yaml):
    """完整流程: untested → challenge → challenged → resolution → falsified."""
    rel_path, full = basic_hyp_yaml

    # 步 1: challenge
    challenge_tool = _new_challenge_tool()
    challenge_tool._execute(
        {"hypothesis_yaml_path": rel_path, "challenge_reason": "反例显示不成立",
         "source": "red_green_test"},
        _make_ctx(),
    )

    # 步 2: resolution
    resolution_tool = _new_resolution_tool()
    out = resolution_tool._execute(
        {"hypothesis_yaml_path": rel_path,
         "falsifying_evidence": "red_minimal_worker.py 反例 PASS 但 Worker 仍能跑 — 假设 'Worker 必须有 X' 不成立",
         "method": "red_green_test"},
        _make_ctx(),
    )
    assert "FALSIFIED" in out
    assert "H-test-001" in out

    # 真读 yaml 验
    with full.open(encoding="utf-8") as f:
        final = yaml.safe_load(f)
    assert final["status"] == "falsified"
    assert final["verification_status"] == "falsified"
    assert "resolution" in final
    assert final["resolution"]["outcome"] == "falsified"
    assert "red_minimal_worker.py" in final["resolution"]["falsifying_evidence"]


def test_resolution_tool_rejects_already_falsified(project_root):
    """已 falsified 拒 (frozen)."""
    rel_path = "data/services/doctor/hypotheses/H-already-falsified.yaml"
    full = project_root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(yaml.safe_dump({
        "id": "H-already-falsified",
        "verification_status": "falsified",
        "status": "falsified",
        "resolution": {"outcome": "falsified", "ts": "2026-05-01T00:00:00Z"},
    }, allow_unicode=True), encoding="utf-8")

    tool = _new_resolution_tool()
    out = tool._execute(
        {"hypothesis_yaml_path": rel_path, "falsifying_evidence": "二次证否"},
        _make_ctx(),
    )
    assert "REJECTED" in out
    assert "falsified" in out


def test_resolution_tool_rejects_real_world_validated(project_root):
    """已 real_world_validated (实战 ≥3 验过) 拒."""
    rel_path = "data/services/doctor/hypotheses/H-validated.yaml"
    full = project_root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(yaml.safe_dump({
        "id": "H-validated",
        "verification_status": "real_world_validated",
        "status": "active",
    }, allow_unicode=True), encoding="utf-8")

    tool = _new_resolution_tool()
    out = tool._execute(
        {"hypothesis_yaml_path": rel_path, "falsifying_evidence": "想推翻"},
        _make_ctx(),
    )
    assert "REJECTED" in out


def test_resolution_tool_requires_evidence(basic_hyp_yaml):
    rel_path, _ = basic_hyp_yaml
    tool = _new_resolution_tool()
    with pytest.raises(ToolExecutionError, match="falsifying_evidence 必填"):
        tool._execute(
            {"hypothesis_yaml_path": rel_path, "falsifying_evidence": ""},
            _make_ctx(),
        )


# ── 工具注册到 TOOL_REGISTRY ──

def test_tools_registered():
    """import doctor.tools 后, 两个新工具应已注册."""
    from omnicompany.packages.services._core.agent.configurable import TOOL_REGISTRY
    from omnicompany.packages.services._diagnosis.doctor import tools  # noqa: F401
    assert "record_hypothesis_challenge" in TOOL_REGISTRY
    assert "record_hypothesis_resolution" in TOOL_REGISTRY
