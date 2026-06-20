"""commit_steward 的确定性层 + 分批应用逻辑测试(不依赖 LLM、不动真 git 历史)。

MAP/REDUCE 走性价比模型(call_json + run_parallel_items, 与 plan_steward 同源, 已有覆盖);
这里测可单测的确定性部分: 文件分类策略 + 批次 message 组装 + dry-run 不动 git。
"""
from __future__ import annotations

from omnicompany.packages.services._governance.commit_steward import (
    ChangeFile,
    CommitBatch,
    apply_batches,
    classify_change,
)
from omnicompany.packages.services._governance.commit_steward.steward import _is_committable


def test_classify_low_repetition_plaintext_is_read():
    assert classify_change("src/x/a.py", 10, 5)[0] == "read"
    assert classify_change("docs/standards/x.md", 3, 0)[0] == "read"
    assert classify_change("src/x/a.tsx", 1, 1)[0] == "read"


def test_classify_high_repetition_is_skip():
    assert classify_change("docs/ARCH-CHANGES.jsonl", 5000, 0)[0] == "skip"
    assert classify_change("docs/tech_debt/REGISTRY.md", 28000, 2000)[0] == "skip"
    assert classify_change("assets/shot.png", 0, 0)[0] == "skip"
    assert classify_change("frontend/package-lock.json", 800, 0)[0] == "skip"
    assert classify_change("x/__pycache__/y.pyc", 0, 0)[0] == "skip"


def test_classify_huge_plaintext_diff_downgrades_to_skip():
    policy, reason = classify_change("src/x/big.py", 5000, 1000)
    assert policy == "skip"
    assert "超大改动" in reason


def test_is_committable_excludes_read_failures():
    ok = ChangeFile(path="a.py", status="M", summary="改了分类逻辑", policy="read")
    assert _is_committable(ok)
    ledger = ChangeFile(path="REGISTRY.md", status="M", summary="[账本] M", policy="skip",
                        reason="数据账本/生成物(确定性跳过逐行读)")
    assert _is_committable(ledger)  # 账本仍可提交, 只是没深读
    failed = ChangeFile(path="b.py", status="M", summary="", policy="skip",
                       reason="读不到内容(留工作区不提交)")
    assert not _is_committable(failed)  # 读失败的留工作区


def test_commit_batch_message_format():
    b = CommitBatch(subject="fix(x): 修分类", body="改了 classify_change\n顺带补测试", files=["a.py"])
    msg = b.message()
    assert msg.startswith("fix(x): 修分类\n\n")
    assert "顺带补测试" in msg
    assert msg.endswith("\n")


def test_apply_dry_run_does_not_touch_git():
    batches = [CommitBatch(subject="s1", body="b1", files=["a.py", "b.py"]),
               CommitBatch(subject="s2", body="b2", files=["c.md"])]
    res = apply_batches(batches, dry_run=True)
    assert res["dry_run"] is True
    assert len(res["batches"]) == 2
    assert all(not r["committed"] for r in res["batches"])  # dry-run 一律未提交
    assert res["batches"][0]["files"] == ["a.py", "b.py"]
