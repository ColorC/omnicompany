# [OMNI] origin=claude-code domain=tests/packages/services ts=2026-04-25T06:40:00Z type=test status=active
"""spec_verification 核心层单测 (2026-04-25 抽核心后立).

策略: 注入 fake llm_caller 替代真 LLM, 验证逻辑.
"""
from __future__ import annotations

from omnicompany.packages.services.spec_verification import (
    VerifyConfig,
    verify_once,
    fix_once,
    verify_spec_consumption_with_fix,
)


def _make_fake_llm(responses: list[dict]):
    """返一个 callable, 按调用顺序吐 responses · 多调一次返 None."""
    state = {"i": 0}
    def _caller(*, system, user_content, tool_name, tool_description, schema):
        if state["i"] >= len(responses):
            return None
        r = responses[state["i"]]
        state["i"] += 1
        return r
    return _caller


_DEFAULT_CFG = lambda llm: VerifyConfig(
    domain="test",
    field_check_rules={"item_id": "应在 Java 的 Identifier", "rarity": ".rarity(...)"},
    llm_caller=llm,
    max_fix_retries=3,
)


def test_verify_once_pass():
    fake = _make_fake_llm([{
        "verified": True,
        "missing_fields": [],
        "field_evidence": {"item_id": "ModItems.java:5"},
        "reasoning": "all good",
    }])
    cfg = _DEFAULT_CFG(fake)
    r = verify_once(spec={"item_id": "x"}, files=[{"path": "a", "content": "b"}], config=cfg)
    assert r is not None
    assert r.verified is True
    assert r.missing_fields == []


def test_verify_once_fail():
    fake = _make_fake_llm([{
        "verified": False,
        "missing_fields": ["rarity: Java 漏 .rarity"],
        "field_evidence": {"item_id": "..."},
        "reasoning": "...",
    }])
    cfg = _DEFAULT_CFG(fake)
    r = verify_once(spec={"item_id": "x", "rarity": "uncommon"},
                    files=[{"path": "a", "content": "b"}], config=cfg)
    assert r.verified is False
    assert "rarity" in r.missing_fields[0]


def test_verify_once_llm_returns_none():
    fake = _make_fake_llm([])  # 0 responses
    cfg = _DEFAULT_CFG(fake)
    r = verify_once(spec={}, files=[{"path": "a", "content": "b"}], config=cfg)
    assert r is None


def test_fix_once_basic():
    fake = _make_fake_llm([{
        "files": [{"path": "a.java", "content": "fixed", "write_mode": "create"}],
        "fix_summary": "added rarity",
    }])
    cfg = _DEFAULT_CFG(fake)
    from omnicompany.packages.services.spec_verification import VerifyResult
    v = VerifyResult(verified=False, missing_fields=["rarity"], field_evidence={}, reasoning="...")
    new_files = fix_once(spec={}, files=[{"path": "a.java", "content": "old", "write_mode": "create"}],
                         verification=v, config=cfg)
    assert new_files == [{"path": "a.java", "content": "fixed", "write_mode": "create"}]


def test_fix_once_preserves_write_mode_when_missing():
    """fix LLM 如果忘填 write_mode, 应从原 files 恢复."""
    fake = _make_fake_llm([{
        "files": [{"path": "a.java", "content": "fixed"}],  # 缺 write_mode
        "fix_summary": "x",
    }])
    cfg = _DEFAULT_CFG(fake)
    from omnicompany.packages.services.spec_verification import VerifyResult
    v = VerifyResult(verified=False, missing_fields=["x"], field_evidence={}, reasoning="")
    new_files = fix_once(
        spec={},
        files=[{"path": "a.java", "content": "old", "write_mode": "create"}],
        verification=v, config=cfg,
    )
    assert new_files[0]["write_mode"] == "create"


def test_v2_loop_first_pass():
    """V2 loop · 第一次 verify 就过 → 0 fix · verified=True."""
    fake = _make_fake_llm([{
        "verified": True, "missing_fields": [], "field_evidence": {}, "reasoning": "good",
    }])
    cfg = _DEFAULT_CFG(fake)
    r = verify_spec_consumption_with_fix(
        spec={"item_id": "x"},
        files=[{"path": "a", "content": "b", "write_mode": "create"}],
        config=cfg,
    )
    assert r.verified is True
    assert r.fix_attempts == 0
    assert len(r.fix_history) == 0


def test_v2_loop_one_fix_then_pass():
    """V2 loop · 第一次 verify 缺 → fix LLM 修 → 第二次 verify 过 · 1 fix."""
    fake = _make_fake_llm([
        {"verified": False, "missing_fields": ["rarity"], "field_evidence": {}, "reasoning": "..."},
        {"files": [{"path": "a.java", "content": "fixed", "write_mode": "create"}], "fix_summary": "added"},
        {"verified": True, "missing_fields": [], "field_evidence": {"rarity": "..."}, "reasoning": "good"},
    ])
    cfg = _DEFAULT_CFG(fake)
    r = verify_spec_consumption_with_fix(
        spec={"item_id": "x", "rarity": "uncommon"},
        files=[{"path": "a.java", "content": "old", "write_mode": "create"}],
        config=cfg,
    )
    assert r.verified is True
    assert r.fix_attempts == 1
    assert any(h.get("fixed_by_llm") for h in r.fix_history)
    # 最终 files 应是 fix 后的
    assert r.files[0]["content"] == "fixed"


def test_v2_loop_exhausts_retries():
    """V2 loop · 永远 verify fail · max_retries 耗尽 · verified=False."""
    fake_responses = []
    for _ in range(4):  # max_retries=3 → 4 verify calls + 3 fix calls
        fake_responses.append({"verified": False, "missing_fields": ["x"], "field_evidence": {}, "reasoning": ""})
        fake_responses.append({"files": [{"path": "a", "content": "still_old", "write_mode": "create"}], "fix_summary": ""})
    fake = _make_fake_llm(fake_responses)
    cfg = _DEFAULT_CFG(fake)
    r = verify_spec_consumption_with_fix(
        spec={}, files=[{"path": "a", "content": "old", "write_mode": "create"}], config=cfg,
    )
    assert r.verified is False
    assert r.fix_attempts == 3
    # fix_history 应至少含 3 条 fixed_by_llm + 1 verify_only_no_fix (第 4 次 verify 失败后无 fix)
    fix_count = sum(1 for h in r.fix_history if h.get("fixed_by_llm"))
    assert fix_count == 3


def test_v2_empty_files():
    fake = _make_fake_llm([])
    cfg = _DEFAULT_CFG(fake)
    r = verify_spec_consumption_with_fix(spec={}, files=[], config=cfg)
    assert r.verified is False
    assert "files 空" in r.missing_fields[0]


def test_v2_verify_llm_fail_first_time():
    """verify LLM 失败 (返 None) · 立即返 verified=False."""
    fake = _make_fake_llm([])  # 第一次就 None
    cfg = _DEFAULT_CFG(fake)
    r = verify_spec_consumption_with_fix(
        spec={}, files=[{"path": "a", "content": "b", "write_mode": "create"}], config=cfg,
    )
    assert r.verified is False
    assert "verify LLM 调用失败" in r.missing_fields[0]
