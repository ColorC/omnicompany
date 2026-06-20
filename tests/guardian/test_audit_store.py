# [OMNI] origin=claude-code domain=tests/guardian ts=2026-04-24T00:00:00Z type=test
"""GuardianAuditStore (2026-04-24 用户要求 '跑了要有痕迹 · 防重跑') 回归测试.

锁定:
1. append + read_back 基础读写
2. lookup_latest 五元组全匹配命中, 任一项变即不命中
3. file_sha16 / prompt_sha8 / rule_version 变化都让缓存失效
4. 写盘路径 data/services/guardian/audit/ 防递归 (不被 guardian 自己扫到)
5. 写入伴随 sidecar (data-provenance)
"""
from __future__ import annotations

import time
from pathlib import Path

from omnicompany.packages.services._core.guardian.audit_store import (
    AuditRecord,
    GuardianAuditStore,
    compute_file_sha16,
    compute_prompt_sha8,
    compute_rule_version,
)


def _sample_record(**kwargs) -> AuditRecord:
    defaults = dict(
        target_path="scripts/foo.py",
        file_sha16="aaa111",
        rule_id="OMNI-073",
        rule_version="v1",
        prompt_sha8="9ef23a10",
        reviewer="GuardianAgent:test:v1",
        verdict="confirmed",
        confidence=0.9,
        reasoning="test",
    )
    defaults.update(kwargs)
    return AuditRecord(**defaults)


def test_append_and_read_back(tmp_path: Path):
    store = GuardianAuditStore(tmp_path)
    r = _sample_record()
    store.append_record(r)
    records = list(store.iter_records())
    assert len(records) == 1
    assert records[0].target_path == r.target_path
    assert records[0].verdict == "confirmed"


def test_append_many(tmp_path: Path):
    store = GuardianAuditStore(tmp_path)
    rs = [_sample_record(target_path=f"scripts/f{i}.py") for i in range(5)]
    n = store.append_many(rs)
    assert n == 5
    assert len(list(store.iter_records())) == 5


def test_lookup_latest_exact_hit(tmp_path: Path):
    store = GuardianAuditStore(tmp_path)
    store.append_record(_sample_record())
    hit = store.lookup_latest(
        target_path="scripts/foo.py", rule_id="OMNI-073",
        file_sha16="aaa111", rule_version="v1", prompt_sha8="9ef23a10",
    )
    assert hit is not None
    assert hit.verdict == "confirmed"


def test_lookup_file_sha_change_misses(tmp_path: Path):
    store = GuardianAuditStore(tmp_path)
    store.append_record(_sample_record(file_sha16="aaa111"))
    hit = store.lookup_latest(
        target_path="scripts/foo.py", rule_id="OMNI-073",
        file_sha16="bbb222",  # 文件内容变
        rule_version="v1", prompt_sha8="9ef23a10",
    )
    assert hit is None, "文件改了缓存应失效"


def test_lookup_prompt_sha_change_misses(tmp_path: Path):
    store = GuardianAuditStore(tmp_path)
    store.append_record(_sample_record(prompt_sha8="9ef23a10"))
    hit = store.lookup_latest(
        target_path="scripts/foo.py", rule_id="OMNI-073",
        file_sha16="aaa111", rule_version="v1",
        prompt_sha8="NEW_SHA",  # prompt 改了
    )
    assert hit is None, "prompt 改了缓存应失效"


def test_lookup_rule_version_change_misses(tmp_path: Path):
    store = GuardianAuditStore(tmp_path)
    store.append_record(_sample_record(rule_version="v1"))
    hit = store.lookup_latest(
        target_path="scripts/foo.py", rule_id="OMNI-073",
        file_sha16="aaa111", rule_version="v2",  # 规则改了
        prompt_sha8="9ef23a10",
    )
    assert hit is None, "rule_version 改了缓存应失效"


def test_lookup_latest_returns_newest(tmp_path: Path):
    store = GuardianAuditStore(tmp_path)
    store.append_record(_sample_record(ts="2026-04-01T00:00:00Z", verdict="uncertain"))
    time.sleep(0.001)
    store.append_record(_sample_record(ts="2026-04-24T00:00:00Z", verdict="confirmed"))
    hit = store.lookup_latest(
        target_path="scripts/foo.py", rule_id="OMNI-073",
        file_sha16="aaa111", rule_version="v1", prompt_sha8="9ef23a10",
    )
    assert hit is not None
    assert hit.verdict == "confirmed"  # 返回最新


def test_lookup_no_match_returns_none(tmp_path: Path):
    store = GuardianAuditStore(tmp_path)
    hit = store.lookup_latest(
        target_path="foo", rule_id="OMNI-073",
        file_sha16="x", rule_version="v1", prompt_sha8="y",
    )
    assert hit is None


def test_dismissed_also_recorded(tmp_path: Path):
    """dismissed (合法判决) 也要记录 — 用户明示 '健康也要标记'."""
    store = GuardianAuditStore(tmp_path)
    store.append_record(_sample_record(verdict="dismissed"))
    hit = store.lookup_latest(
        target_path="scripts/foo.py", rule_id="OMNI-073",
        file_sha16="aaa111", rule_version="v1", prompt_sha8="9ef23a10",
    )
    assert hit is not None
    assert hit.verdict == "dismissed"


def test_stats(tmp_path: Path):
    store = GuardianAuditStore(tmp_path)
    store.append_many([
        _sample_record(verdict="confirmed"),
        _sample_record(target_path="a", verdict="dismissed"),
        _sample_record(target_path="b", rule_id="OMNI-074", verdict="confirmed"),
    ])
    s = store.stats()
    assert s["total"] == 3
    assert s["by_verdict"] == {"confirmed": 2, "dismissed": 1}
    assert s["by_rule"] == {"OMNI-073": 2, "OMNI-074": 1}


def test_records_path_under_guardian_audit(tmp_path: Path):
    """防递归关键: store 必须落在 data/services/guardian/audit/ 下 (已在规则豁免)."""
    store = GuardianAuditStore(tmp_path)
    assert "data/services/guardian/audit" in store.records_path.as_posix()
    assert store.records_path.name == "records.jsonl"


def test_sidecar_written(tmp_path: Path):
    """data-provenance I-20: audit 文件自动带 sidecar."""
    store = GuardianAuditStore(tmp_path)
    store.append_record(_sample_record())
    sidecar = store.records_path.with_suffix(".jsonl.omni.json")
    assert sidecar.exists()


# ── 工具函数测试 ────────────────────────────────────────────


def test_compute_file_sha16_stable(tmp_path: Path):
    p = tmp_path / "a.py"
    p.write_text("hello", encoding="utf-8")
    sha1 = compute_file_sha16(p)
    sha2 = compute_file_sha16(p)
    assert sha1 == sha2
    assert len(sha1) == 16


def test_compute_file_sha16_changes_with_content(tmp_path: Path):
    p = tmp_path / "a.py"
    p.write_text("v1", encoding="utf-8")
    sha1 = compute_file_sha16(p)
    p.write_text("v2", encoding="utf-8")
    sha2 = compute_file_sha16(p)
    assert sha1 != sha2


def test_compute_prompt_sha8():
    s1 = compute_prompt_sha8("prompt A")
    s2 = compute_prompt_sha8("prompt A")
    s3 = compute_prompt_sha8("prompt B")
    assert s1 == s2
    assert s1 != s3
    assert len(s1) == 8


def test_compute_rule_version_stable():
    from omnicompany.packages.services._core.guardian.rules.compliance_prevention import RULES
    r = next(rule for rule in RULES if rule.id == "OMNI-073")
    v1 = compute_rule_version(r)
    v2 = compute_rule_version(r)
    assert v1 == v2
    assert v1.startswith("v")
