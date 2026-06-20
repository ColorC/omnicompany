# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T13:10:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest HypothesisResolutionRecorder — 跟 ChallengeRecorder 同形态. 必先 challenged + frozen 拒 + 不动原 dict"
# [OMNI] why="V4-1 修 V3 留下债. ResolutionRecorder 提到 builders/ 后跟 ChallengeRecorder 一致, 测试也跟着"
# [OMNI] tags=test,pytest,resolution-recorder,hypothesis-state,V4
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_hypothesis_resolution_recorder.py"
"""pytest HypothesisResolutionRecorder.

测 case (跟 test_hypothesis_challenge_recorder.py 同形态):
- 边界 (非 dict / 缺 id / 缺 evidence)
- 真用 (一次 record → resolution + status changed)
- 必先 challenged 才允许 (按 schema §三步骤 3-4 顺序)
- frozen status: falsified + real_world_validated 拒
- 非标 method 软警告
- resolution 字段完整 (ts/outcome/evidence/method/falsifier_id/status_before/verification_status_before)
- 不修原 dict (返新 dict)
- falsifier_id 默认值
"""
from __future__ import annotations

import re

import pytest

from omnicompany.packages.services._diagnosis.doctor.builders import (
    HypothesisResolutionRecorder,
    record_hypothesis_resolution,
)


@pytest.fixture
def recorder():
    return HypothesisResolutionRecorder()


@pytest.fixture
def challenged_hyp():
    """已 challenged 的假设 (resolution 前置条件)."""
    return {
        "id": "H-test-resolution-001",
        "statement": "Worker 必须有 X",
        "applies_to": "worker",
        "status": "challenged",
        "verification_status": "untested",
        "challenge_log": [{"ts": "2026-05-01T00:00:00Z", "challenge_reason": "X"}],
    }


# ── 边界 ──

def test_record_non_dict_returns_skipped(recorder):
    r = recorder.record("not-a-dict", "evidence")
    assert r.falsified is False
    assert "非 dict" in r.skip_reason


def test_record_no_id_returns_skipped(recorder):
    r = recorder.record({"statement": "no id", "status": "challenged"}, "evidence")
    assert r.falsified is False
    assert "缺 id" in r.skip_reason


def test_record_empty_evidence_returns_skipped(recorder, challenged_hyp):
    r = recorder.record(challenged_hyp, "")
    assert r.falsified is False
    assert "falsifying_evidence 必填" in r.skip_reason


def test_record_whitespace_evidence_returns_skipped(recorder, challenged_hyp):
    r = recorder.record(challenged_hyp, "   ")
    assert r.falsified is False


# ── 真用 ──

def test_record_basic_falsifies(recorder, challenged_hyp):
    r = recorder.record(challenged_hyp, "red_minimal_worker.py 反例显示假设不成立",
                         method="red_green_test", falsifier_id="agent:challenge")
    assert r.falsified is True
    assert r.hypothesis_id == "H-test-resolution-001"
    assert r.upgraded_dict["status"] == "falsified"
    assert r.upgraded_dict["verification_status"] == "falsified"
    assert "resolution" in r.upgraded_dict
    res = r.upgraded_dict["resolution"]
    assert res["outcome"] == "falsified"
    assert res["falsifying_evidence"] == "red_minimal_worker.py 反例显示假设不成立"
    assert res["method"] == "red_green_test"
    assert res["falsifier_id"] == "agent:challenge"
    assert res["status_before"] == "challenged"
    assert res["verification_status_before"] == "untested"
    # ts 是 ISO Z
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", res["ts"])


def test_record_does_not_mutate_input(recorder, challenged_hyp):
    """不动原 dict — 返新 dict."""
    r = recorder.record(challenged_hyp, "evidence")
    assert challenged_hyp["status"] == "challenged"  # 原不改
    assert "resolution" not in challenged_hyp        # 原不加字段
    assert r.upgraded_dict is not challenged_hyp


def test_record_default_falsifier_id(recorder, challenged_hyp):
    """falsifier_id 默认 'ai-ide'."""
    r = recorder.record(challenged_hyp, "evidence")
    assert r.upgraded_dict["resolution"]["falsifier_id"] == "ai-ide"


def test_record_default_method_is_manual(recorder, challenged_hyp):
    """method 默认 'manual'."""
    r = recorder.record(challenged_hyp, "evidence")
    assert r.upgraded_dict["resolution"]["method"] == "manual"


# ── 必先 challenged ──

def test_active_status_rejected(recorder):
    """status='active' 拒 (没经过 challenge)."""
    hyp = {"id": "H-active", "status": "active", "verification_status": "untested"}
    r = recorder.record(hyp, "evidence")
    assert r.falsified is False
    assert "challenged" in r.skip_reason


def test_red_green_pass_status_rejected(recorder):
    """status='red_green_pass' (本字段是 verification_status 的值, 但 status 字段也可能记) 拒.

    实际 status 字段值通常 'active' / 'challenged' / 'falsified', 不是 verification_status.
    本测确保任何非 'challenged' 都被拒.
    """
    hyp = {"id": "H-rg-stat", "status": "red_green_pass", "verification_status": "red_green_pass"}
    r = recorder.record(hyp, "evidence")
    assert r.falsified is False


# ── frozen status 拒 (verification_status 字段) ──

def test_falsified_verification_status_rejected(recorder):
    """verification_status='falsified' 拒 (即使 status='challenged')."""
    hyp = {
        "id": "H-already-fal",
        "status": "challenged",
        "verification_status": "falsified",
    }
    r = recorder.record(hyp, "想再证否")
    assert r.falsified is False
    assert "已封存" in r.skip_reason


def test_real_world_validated_verification_status_rejected(recorder):
    """verification_status='real_world_validated' 拒 (实战验过的不该轻易翻盘)."""
    hyp = {
        "id": "H-validated",
        "status": "challenged",
        "verification_status": "real_world_validated",
    }
    r = recorder.record(hyp, "想推翻")
    assert r.falsified is False
    assert "翻盘" in r.skip_reason


# ── 非标 method 软警告 ──

def test_non_standard_method_allowed_with_warning(recorder, challenged_hyp):
    """非标 method 允许但留 method_warning."""
    r = recorder.record(challenged_hyp, "evidence", method="custom_method_x")
    assert r.falsified is True
    res = r.upgraded_dict["resolution"]
    assert res["method"] == "custom_method_x"
    assert "method_warning" in res
    assert "非标 method" in res["method_warning"]


def test_standard_method_no_warning(recorder, challenged_hyp):
    """标准 method (red_green_test 等) 无 method_warning."""
    r = recorder.record(challenged_hyp, "evidence", method="red_green_test")
    res = r.upgraded_dict["resolution"]
    assert "method_warning" not in res


# ── 便捷入口 ──

def test_helper_function(challenged_hyp):
    r = record_hypothesis_resolution(challenged_hyp, "evidence")
    assert r.falsified is True
    assert r.upgraded_dict["status"] == "falsified"


# ── SingleToolRouter 调本 Recorder 不内嵌逻辑 (V4 还债) ──

def test_tool_uses_resolution_recorder_not_inline_logic():
    """RecordHypothesisResolutionTool import 时应能找到 HypothesisResolutionRecorder.

    确认架构: 工具层包纯函数, 不内嵌逻辑 (跟 ChallengeRecorder 同一致).
    """
    import inspect
    from omnicompany.packages.services._diagnosis.doctor.tools import (
        record_hypothesis_resolution as tool_module,
    )
    src = inspect.getsource(tool_module)
    # 工具应 import 跟调 HypothesisResolutionRecorder
    assert "HypothesisResolutionRecorder" in src
    # 不应内嵌 _now_iso / _VALID_METHODS / _FROZEN_STATUSES (这些应在 builders/recorder)
    assert "_FROZEN_STATUSES" not in src or src.count("_FROZEN_STATUSES") == 0
