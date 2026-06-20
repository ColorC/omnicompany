# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T13:55:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest HypothesisConfidenceAuditor — 6 启发式分支 + needs_upgrade 判定 + 不动假设本身 + 真 dogfood 跑本地 25 假设"
# [OMNI] why="V4-3 修真问题. V0 升级时 confidence 都默认 low, 现立审计类列建议 confidence + 提示哪些需手工升级"
# [OMNI] tags=test,pytest,confidence-auditor,hypothesis,V4
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_hypothesis_confidence_auditor.py"
"""pytest HypothesisConfidenceAuditor.

测 case:
- 边界 (空 list / 非 dict / 缺 id)
- 6 启发式分支 (real_world_validated / ≥3 finding / red_green_pass / HIGH 权威 / 1-2 finding / 默认 low)
- needs_upgrade 判定 (current < suggested 时 True)
- by_suggested 分布 + summary
- 不动假设本身 (审计类)
- 真 dogfood 跑本地 25 假设
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from omnicompany.packages.services._diagnosis.doctor.builders import (
    HypothesisConfidenceAuditor,
    audit_hypothesis_confidence,
)


@pytest.fixture
def auditor():
    return HypothesisConfidenceAuditor()


# ── 边界 ──

def test_audit_empty_list(auditor):
    r = auditor.audit([])
    assert r.audited == []
    assert "audited 0" in r.summary


def test_audit_skip_non_dict(auditor):
    r = auditor.audit(["string", 42, None])
    assert r.audited == []
    assert len(r.skipped) == 3


def test_audit_skip_no_id(auditor):
    r = auditor.audit([{"statement": "no id"}])
    assert r.audited == []
    assert r.skipped == [("<no-id>", "缺 id")]


# ── 启发式 1: real_world_validated → high ──

def test_real_world_validated_suggests_high(auditor):
    hyp = {"id": "H-rw", "verification_status": "real_world_validated", "confidence_level": "low"}
    r = auditor.audit([hyp])
    e = r.audited[0]
    assert e.suggested_confidence == "high"
    assert "real_world_validated" in e.reason
    assert e.needs_upgrade is True  # low → high


# ── 启发式 2: ≥3 finding → high ──

def test_three_findings_suggests_high(auditor):
    hyp = {
        "id": "H-3f", "verification_status": "untested", "confidence_level": "low",
        "related_finding_ids": ["F-1", "F-2", "F-3"],
    }
    r = auditor.audit([hyp])
    e = r.audited[0]
    assert e.suggested_confidence == "high"
    assert "实战 3 次" in e.reason


def test_five_findings_suggests_high(auditor):
    hyp = {
        "id": "H-5f", "verification_status": "untested", "confidence_level": "low",
        "related_finding_ids": [f"F-{i}" for i in range(5)],
    }
    r = auditor.audit([hyp])
    assert r.audited[0].suggested_confidence == "high"


# ── 启发式 3: red_green_pass → medium ──

def test_red_green_pass_suggests_medium(auditor):
    hyp = {
        "id": "H-rg", "verification_status": "red_green_pass", "confidence_level": "low",
        "related_finding_ids": [],
    }
    r = auditor.audit([hyp])
    e = r.audited[0]
    assert e.suggested_confidence == "medium"
    assert "red_green_pass" in e.reason
    assert e.needs_upgrade is True


# ── 启发式 4: HIGH 权威规范派生 → medium ──

def test_high_authority_suggests_medium(auditor):
    hyp = {
        "id": "H-ha", "verification_status": "untested", "confidence_level": "low",
        "source_authority": "HIGH",
    }
    r = auditor.audit([hyp])
    e = r.audited[0]
    assert e.suggested_confidence == "medium"
    assert "HIGH" in e.reason


# ── 启发式 5: 1-2 finding → medium ──

def test_one_finding_suggests_medium(auditor):
    hyp = {
        "id": "H-1f", "verification_status": "untested", "confidence_level": "low",
        "related_finding_ids": ["F-1"],
    }
    r = auditor.audit([hyp])
    assert r.audited[0].suggested_confidence == "medium"
    assert "1 次" in r.audited[0].reason


def test_two_findings_suggests_medium(auditor):
    hyp = {
        "id": "H-2f", "verification_status": "untested", "confidence_level": "low",
        "related_finding_ids": ["F-1", "F-2"],
    }
    r = auditor.audit([hyp])
    assert r.audited[0].suggested_confidence == "medium"


# ── 启发式 6: 默认 low ──

def test_no_signals_suggests_low(auditor):
    hyp = {
        "id": "H-bare", "verification_status": "untested", "confidence_level": "low",
        "source_authority": "LOW",
    }
    r = auditor.audit([hyp])
    e = r.audited[0]
    assert e.suggested_confidence == "low"
    assert "新生成未验证" in e.reason
    assert e.needs_upgrade is False  # low == low


# ── needs_upgrade 判定 ──

def test_current_high_already_no_upgrade(auditor):
    """current=high 已经够 → needs_upgrade=False 即使 suggested 是 high."""
    hyp = {
        "id": "H-already-high",
        "verification_status": "real_world_validated",
        "confidence_level": "high",
    }
    r = auditor.audit([hyp])
    assert r.audited[0].needs_upgrade is False


def test_current_medium_with_high_suggestion_needs_upgrade(auditor):
    """current=medium + suggested=high → needs_upgrade=True."""
    hyp = {
        "id": "H-mid-to-high",
        "verification_status": "real_world_validated",
        "confidence_level": "medium",
    }
    r = auditor.audit([hyp])
    assert r.audited[0].suggested_confidence == "high"
    assert r.audited[0].needs_upgrade is True


def test_current_high_with_medium_suggestion_no_downgrade(auditor):
    """current=high + suggested=medium → needs_upgrade=False (审计不降级)."""
    hyp = {
        "id": "H-high-not-downgrade",
        "verification_status": "red_green_pass",  # 启发式建议 medium
        "confidence_level": "high",                # 但已 high (人手工标过)
    }
    r = auditor.audit([hyp])
    assert r.audited[0].suggested_confidence == "medium"
    assert r.audited[0].needs_upgrade is False  # 不降级


# ── by_suggested 分布 + summary ──

def test_by_suggested_counts(auditor):
    hyps = [
        {"id": "H-1", "verification_status": "real_world_validated"},  # high
        {"id": "H-2", "verification_status": "red_green_pass"},        # medium
        {"id": "H-3", "verification_status": "untested"},              # low
    ]
    r = auditor.audit(hyps)
    assert r.by_suggested == {"high": 1, "medium": 1, "low": 1}


def test_summary_with_audited(auditor):
    hyps = [
        {"id": "H-1", "verification_status": "real_world_validated", "confidence_level": "low"},
    ]
    r = auditor.audit(hyps)
    s = r.summary
    assert "audited 1" in s
    assert "needs_upgrade=1" in s
    assert "high" in s


# ── 不动假设本身 ──

def test_does_not_mutate_input(auditor):
    """审计类不动原 dict."""
    hyp = {"id": "H-immut", "verification_status": "real_world_validated", "confidence_level": "low"}
    auditor.audit([hyp])
    assert hyp["confidence_level"] == "low"  # 原不改


# ── 真 dogfood ──

def test_dogfood_local_25_hypotheses(auditor):
    """跑本地 25 假设, 看真分布. V0 默认 low + 没真 finding → 应大量 low."""
    hyp_dir = Path(__file__).resolve().parents[4] / "data" / "services" / "doctor" / "hypotheses"
    if not hyp_dir.exists():
        pytest.skip(f"data/.../hypotheses 目录不存在: {hyp_dir}")
    hyps = []
    for path in sorted(hyp_dir.glob("*.yaml")):
        with path.open(encoding="utf-8") as f:
            d = yaml.safe_load(f)
        if isinstance(d, dict):
            hyps.append(d)
    if not hyps:
        pytest.skip("data/.../hypotheses 无 yaml")
    r = auditor.audit(hyps)
    # 应当 audited > 0
    assert len(r.audited) > 0
    # by_suggested 应至少含 'low' (因为多数没强信号)
    assert "low" in r.by_suggested
    print(f"\n本地 25 假设 confidence 审计: {r.summary}")


# ── V10 启发式扩: challenge_log 历史 ──

def test_five_challenges_unfalsified_suggests_high(auditor):
    """≥5 质疑且未 falsified → high (经反复质疑仍站立)."""
    hyp = {
        "id": "H-survived",
        "verification_status": "untested",
        "challenge_log": [{"ts": f"2026-05-{i:02d}T00:00:00Z", "challenge_reason": f"q{i}"}
                          for i in range(1, 6)],  # 5 条
        "confidence_level": "low",
    }
    r = auditor.audit([hyp])
    e = r.audited[0]
    assert e.suggested_confidence == "high"
    assert "5 次质疑" in e.reason
    assert e.needs_upgrade is True


def test_six_challenges_unfalsified_suggests_high(auditor):
    """≥5 阈值 — 6 次也是 high."""
    hyp = {
        "id": "H-6q",
        "verification_status": "untested",
        "challenge_log": [{"ts": "x", "challenge_reason": "q"} for _ in range(6)],
    }
    assert auditor.audit([hyp]).audited[0].suggested_confidence == "high"


def test_two_challenges_unfalsified_suggests_medium(auditor):
    """≥2 < 5 + 未 falsified → medium."""
    hyp = {
        "id": "H-survived-2",
        "verification_status": "untested",
        "challenge_log": [{"ts": "x", "challenge_reason": "q1"},
                          {"ts": "x", "challenge_reason": "q2"}],
    }
    e = auditor.audit([hyp]).audited[0]
    assert e.suggested_confidence == "medium"
    assert "2 次质疑仍未被证否" in e.reason


def test_one_challenge_does_not_trigger(auditor):
    """1 challenge 未达 medium 阈值 → 默认 low."""
    hyp = {
        "id": "H-1q",
        "verification_status": "untested",
        "challenge_log": [{"ts": "x", "challenge_reason": "q"}],
    }
    e = auditor.audit([hyp]).audited[0]
    assert e.suggested_confidence == "low"


def test_falsified_with_challenges_does_not_trigger_high(auditor):
    """falsified 状态即使 ≥5 challenge 也不升 high — 已证否的应封存."""
    hyp = {
        "id": "H-fal-5q",
        "verification_status": "falsified",
        "challenge_log": [{"ts": "x", "challenge_reason": "q"} for _ in range(5)],
    }
    e = auditor.audit([hyp]).audited[0]
    assert e.suggested_confidence == "low"  # 没匹其他启发式 → 默认


def test_high_findings_takes_precedence_over_challenges(auditor):
    """≥3 finding (启发式 2) 优先于 challenge_log (启发式 3) — 都是 high 但 reason 不同."""
    hyp = {
        "id": "H-both",
        "verification_status": "untested",
        "related_finding_ids": ["F-1", "F-2", "F-3"],
        "challenge_log": [{"ts": "x", "challenge_reason": "q"} for _ in range(5)],
    }
    e = auditor.audit([hyp]).audited[0]
    assert e.suggested_confidence == "high"
    assert "实战 3 次" in e.reason  # 启发式 2 优先, reason 应反映 finding


def test_red_green_pass_takes_precedence_over_2_challenges(auditor):
    """red_green_pass (启发式 4) 优先于 ≥2 challenge (启发式 7)."""
    hyp = {
        "id": "H-rgp-2q",
        "verification_status": "red_green_pass",
        "challenge_log": [{"ts": "x", "challenge_reason": "q"} for _ in range(2)],
    }
    e = auditor.audit([hyp]).audited[0]
    assert e.suggested_confidence == "medium"
    assert "red_green_pass" in e.reason


# ── 便捷入口 ──

def test_helper_function():
    r = audit_hypothesis_confidence([
        {"id": "H-x", "verification_status": "real_world_validated"}
    ])
    assert r.audited[0].suggested_confidence == "high"


# ── V12 CLI 入口 (2026-05-07) ─────────────────────────────────────────────

import json
import yaml as _yaml
from omnicompany.packages.services._diagnosis.doctor.builders.hypothesis_confidence_auditor import (
    main as cli_main,
)


def _write_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        _yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


@pytest.fixture
def tmp_hyps(tmp_path):
    """tmp dir 写 3 假设 (1 应升 high, 1 medium, 1 low)."""
    d = tmp_path / "hyps"
    d.mkdir()
    _write_yaml(d / "H-high.yaml", {
        "id": "H-high", "verification_status": "real_world_validated",
        "confidence_level": "low",
    })
    _write_yaml(d / "H-medium.yaml", {
        "id": "H-medium", "verification_status": "red_green_pass",
        "confidence_level": "low",
    })
    _write_yaml(d / "H-low.yaml", {
        "id": "H-low", "verification_status": "untested",
        "confidence_level": "low",
    })
    return d


def test_cli_default_shows_all(tmp_hyps, capsys):
    rc = cli_main(["--hypotheses-dir", str(tmp_hyps)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "audited 3" in out
    # 3 条都该出现
    assert "H-high" in out
    assert "H-medium" in out
    assert "H-low" in out


def test_cli_only_needs_upgrade(tmp_hyps, capsys):
    rc = cli_main(["--hypotheses-dir", str(tmp_hyps), "--only-needs-upgrade"])
    assert rc == 0
    out = capsys.readouterr().out
    # H-high 跟 H-medium 应升 (low → high/medium), H-low 不该出
    assert "H-high" in out
    assert "H-medium" in out
    assert "H-low" not in out


def test_cli_output_json(tmp_hyps, tmp_path):
    out_file = tmp_path / "audit.json"
    rc = cli_main([
        "--hypotheses-dir", str(tmp_hyps),
        "--output-json", str(out_file),
    ])
    assert rc == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert "summary" in data
    assert "by_suggested" in data
    assert "audited" in data
    # 3 audited
    assert len(data["audited"]) == 3
    # by_suggested 应含 high + medium + low
    assert "high" in data["by_suggested"]


def test_cli_dir_not_exists_returns_1(tmp_path, capsys):
    rc = cli_main(["--hypotheses-dir", str(tmp_path / "no_such_dir")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "ERROR" in err


def test_cli_empty_dir_returns_0_with_warning(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = cli_main(["--hypotheses-dir", str(empty)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "无 yaml" in out
