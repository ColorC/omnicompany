# [OMNI] origin=claude-code domain=tests/dashboard ts=2026-06-13 type=test
"""agent_digest 摘要管线的确定性层测试(不联网 — summarize_one 打桩)。

覆盖: 频率/运行态闸(_needs_digest)、run_tick 落库 + max_per_tick 上限、get_digest 回读。
"""
from __future__ import annotations

import pytest


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNI_WORKSPACE_ROOT", str(tmp_path))
    return tmp_path


def _item(sid, *, status="working", mtime=1000.0, provider="claude_code"):
    return {"provider": provider, "session_id": sid, "cwd": "e:/x",
            "preview": f"task {sid}", "last_did": f"did {sid}", "mtime": mtime, "status": status}


def test_needs_digest_gating(tmp_workspace):
    from omnicompany.dashboard.boss_sight.services import agent_digest as ad
    now = 10_000.0
    # 没摘要 → 一定要算(不分运行态)
    assert ad._needs_digest(_item("a", status="done"), None, now)
    # 运行中 + transcript 变了 + 距上次够久 → 要算
    cur = {"_source_mtime": 500.0, "_updated_ts": now - 1000}
    assert ad._needs_digest(_item("a", status="working", mtime=2000.0), cur, now)
    # 非运行中(done) + 已有摘要 → 不动
    assert not ad._needs_digest(_item("a", status="done", mtime=2000.0), cur, now)
    # 运行中但 transcript 没新写入 → 不动
    cur2 = {"_source_mtime": 2000.0, "_updated_ts": now - 1000}
    assert not ad._needs_digest(_item("a", status="working", mtime=2000.0), cur2, now)
    # 运行中 + 变了 但刚算过(没到最小间隔) → 不动
    cur3 = {"_source_mtime": 500.0, "_updated_ts": now - 5}
    assert not ad._needs_digest(_item("a", status="working", mtime=2000.0), cur3, now)


def test_run_tick_persists_and_caps(tmp_workspace, monkeypatch):
    from omnicompany.dashboard.boss_sight.services import agent_digest as ad

    calls = {"n": 0}

    def fake_summarize(item):
        calls["n"] += 1
        return {"project": f"P-{item['session_id']}", "plan": "无",
                "title": f"做 {item['session_id']}", "last_step": f"刚做完 {item['session_id']}"}

    monkeypatch.setattr(ad, "summarize_one", fake_summarize)

    items = [_item(f"s{i}", mtime=1000.0 + i) for i in range(6)]
    stat = ad.run_tick(items, now=10_000.0, max_per_tick=4, workers=2)
    assert stat["targets"] == 4          # 6 条都没摘要, 但单轮上限 4
    assert stat["updated"] == 4
    assert calls["n"] == 4               # 便宜模型只被调 4 次(预算有界)

    # 落库可回读, 字段对
    d = ad.get_digest("claude_code", "s5")  # s5 mtime 最大, 优先入选
    assert d is not None and d["title"] == "做 s5" and d["project"] == "P-s5"

    # 第二轮: 已有摘要的 done 不再算; 没摘要的剩 2 条补上
    for it in items:
        it["status"] = "done"
    stat2 = ad.run_tick(items, now=10_500.0, max_per_tick=4, workers=2)
    assert stat2["targets"] == 2         # 只剩当初没入选的 2 条没摘要
    assert stat2["updated"] == 2


def test_get_digest_absent(tmp_workspace):
    from omnicompany.dashboard.boss_sight.services import agent_digest as ad
    assert ad.get_digest("claude_code", "nope") is None
