# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T10:05:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest HypothesisChallengeRecorder — 记 challenge_log + 改 status=challenged + frozen status (falsified/real_world_validated) 拒"
# [OMNI] why="V2 步骤 3 工具部分实施. schema §三步骤 3+4 边界 (frozen 不再 challenge)"
# [OMNI] tags=test,pytest,challenge-recorder,hypothesis-state,V2
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_hypothesis_challenge_recorder.py"
"""pytest HypothesisChallengeRecorder.

测 case:
- 边界 (非 dict / 缺 id / 缺 reason)
- 真用 (一次 record → log + status changed)
- 累积 record (多次 → log_entry 累积)
- frozen status: falsified + real_world_validated 拒
- 非标 source 软警告 (允许但 log 留 note)
- log entry 字段完整 (ts/reason/source/challenger_id/status_before/verification_status_before)
- 不修原 dict (返新 dict)
- challenger_id 默认值
"""
from __future__ import annotations

import re
from datetime import datetime

import pytest

from omnicompany.packages.services._diagnosis.doctor.builders import (
    HypothesisChallengeRecorder,
    record_hypothesis_challenge,
)


@pytest.fixture
def recorder():
    return HypothesisChallengeRecorder()


@pytest.fixture
def basic_hyp():
    return {
        "id": "H-test-001",
        "statement": "Worker 必须有 X",
        "applies_to": "worker",
        "status": "active",
        "verification_status": "untested",
        "challenge_log": [],
    }


# ── 边界 ──

def test_record_non_dict_returns_skipped(recorder):
    r = recorder.record("not-a-dict", "reason")
    assert r.recorded is False
    assert "非 dict" in r.skip_reason


def test_record_no_id_returns_skipped(recorder):
    r = recorder.record({"statement": "no id"}, "reason")
    assert r.recorded is False
    assert "缺 id" in r.skip_reason


def test_record_empty_reason_returns_skipped(recorder, basic_hyp):
    r = recorder.record(basic_hyp, "")
    assert r.recorded is False
    assert "challenge_reason 必填" in r.skip_reason


def test_record_whitespace_reason_returns_skipped(recorder, basic_hyp):
    r = recorder.record(basic_hyp, "   ")
    assert r.recorded is False


# ── 真用 ──

def test_record_basic_writes_log_and_changes_status(recorder, basic_hyp):
    r = recorder.record(basic_hyp, "反例 fixture 显示假设不成立",
                         source="red_green_test", challenger_id="ai-ide")
    assert r.recorded is True
    assert r.hypothesis_id == "H-test-001"
    assert r.upgraded_dict["status"] == "challenged"
    assert len(r.upgraded_dict["challenge_log"]) == 1
    log = r.upgraded_dict["challenge_log"][0]
    assert log["challenge_reason"] == "反例 fixture 显示假设不成立"
    assert log["source"] == "red_green_test"
    assert log["challenger_id"] == "ai-ide"
    assert log["status_before"] == "active"
    assert log["verification_status_before"] == "untested"
    # ts 是 ISO Z
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", log["ts"])


def test_record_does_not_mutate_input(recorder, basic_hyp):
    """V0 不动原 dict — 返新 dict."""
    original_log_id = id(basic_hyp["challenge_log"])
    r = recorder.record(basic_hyp, "test reason")
    assert basic_hyp["status"] == "active"        # 原不改
    assert len(basic_hyp["challenge_log"]) == 0   # 原 log 不动
    assert id(basic_hyp["challenge_log"]) == original_log_id  # 原 list 对象不变
    assert r.upgraded_dict is not basic_hyp        # 真新对象


def test_record_default_challenger_id(recorder, basic_hyp):
    """challenger_id 默认 'ai-ide'."""
    r = recorder.record(basic_hyp, "reason")
    assert r.upgraded_dict["challenge_log"][0]["challenger_id"] == "ai-ide"


def test_record_default_source_is_manual(recorder, basic_hyp):
    """source 默认 'manual'."""
    r = recorder.record(basic_hyp, "reason")
    assert r.upgraded_dict["challenge_log"][0]["source"] == "manual"


# ── 累积 record ──

def test_multiple_records_accumulate_log(recorder, basic_hyp):
    """同假设多次 record → challenge_log 累积."""
    r1 = recorder.record(basic_hyp, "first challenge")
    r2 = recorder.record(r1.upgraded_dict, "second challenge", source="historical_instance")
    r3 = recorder.record(r2.upgraded_dict, "third challenge", source="standards_authority")
    assert len(r3.upgraded_dict["challenge_log"]) == 3
    reasons = [le["challenge_reason"] for le in r3.upgraded_dict["challenge_log"]]
    assert reasons == ["first challenge", "second challenge", "third challenge"]
    sources = [le["source"] for le in r3.upgraded_dict["challenge_log"]]
    assert sources == ["manual", "historical_instance", "standards_authority"]
    # 第二次 record 时 status_before 应为 'challenged' (上一次改的)
    assert r2.upgraded_dict["challenge_log"][1]["status_before"] == "challenged"


# ── frozen status 拒 ──

def test_falsified_hypothesis_rejected(recorder):
    """falsified 状态不允许再 challenge (按 schema §三步骤 4)."""
    hyp = {
        "id": "H-falsified",
        "verification_status": "falsified",
    }
    r = recorder.record(hyp, "想再 challenge")
    assert r.recorded is False
    assert "falsified" in r.skip_reason
    assert "已证否" in r.skip_reason


def test_real_world_validated_hypothesis_rejected(recorder):
    """real_world_validated 状态不允许再 challenge (实战验过的不该轻易翻盘)."""
    hyp = {
        "id": "H-validated",
        "verification_status": "real_world_validated",
    }
    r = recorder.record(hyp, "想推翻实战")
    assert r.recorded is False
    assert "real_world_validated" in r.skip_reason


def test_red_green_pass_can_be_challenged(recorder):
    """red_green_pass 状态 (跑过红绿但未 ≥3 次实战) 仍允许 challenge."""
    hyp = {
        "id": "H-rg",
        "verification_status": "red_green_pass",
        "challenge_log": [],
    }
    r = recorder.record(hyp, "红绿基线可能不充分")
    assert r.recorded is True


def test_untested_can_be_challenged(recorder, basic_hyp):
    """untested 状态可 challenge (默认状态)."""
    r = recorder.record(basic_hyp, "新假设需先质疑再验")
    assert r.recorded is True


# ── 非标 source 软警告 ──

def test_non_standard_source_allowed_with_warning(recorder, basic_hyp):
    """非标 source 允许但留 source_warning."""
    r = recorder.record(basic_hyp, "reason", source="custom_source_x")
    assert r.recorded is True
    log = r.upgraded_dict["challenge_log"][0]
    assert log["source"] == "custom_source_x"
    assert "source_warning" in log
    assert "非标 source" in log["source_warning"]


def test_standard_source_no_warning(recorder, basic_hyp):
    """标准 source (例 red_green_test) 无 source_warning."""
    r = recorder.record(basic_hyp, "reason", source="red_green_test")
    log = r.upgraded_dict["challenge_log"][0]
    assert "source_warning" not in log


# ── V0 hyp 没 challenge_log 字段时新建 ──

def test_v0_hyp_without_challenge_log_field(recorder):
    """V0 老假设没 challenge_log 字段 → record 后新建 list."""
    hyp = {"id": "H-v0", "verification_status": "untested"}  # 无 challenge_log
    r = recorder.record(hyp, "reason")
    assert r.recorded is True
    assert isinstance(r.upgraded_dict["challenge_log"], list)
    assert len(r.upgraded_dict["challenge_log"]) == 1


# ── 便捷入口 ──

def test_helper_function(basic_hyp):
    r = record_hypothesis_challenge(basic_hyp, "reason")
    assert r.recorded is True
    assert r.upgraded_dict["status"] == "challenged"
