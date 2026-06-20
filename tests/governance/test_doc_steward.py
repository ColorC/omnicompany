"""doc_steward 确定性引用完整性层的测试(不依赖 LLM)。

时效性语义层(judge_timeliness/run_timeliness)走性价比模型, 这里不打真实网络;
它复用 plan_steward 同一套 call_json + run_parallel_items, 已有覆盖。
"""
from __future__ import annotations

from pathlib import Path

from omnicompany.packages.services._governance.doc_steward import (
    discover_targets,
    run_reference_audit,
    scan_references,
)


def _make_repo(tmp: Path) -> Path:
    (tmp / "docs" / "standards" / "concepts").mkdir(parents=True)
    (tmp / "docs" / "standards" / "_global").mkdir(parents=True)
    (tmp / "docs" / "plans" / "x" / "[2026-06-13]T").mkdir(parents=True)
    (tmp / "docs" / "plans" / "_archive" / "old").mkdir(parents=True)
    # 一个存在的目标
    (tmp / "docs" / "standards" / "_global" / "real.md").write_text("# real", encoding="utf-8")
    return tmp


def test_broken_ref_detected(tmp_path):
    repo = _make_repo(tmp_path)
    doc = repo / "docs" / "standards" / "concepts" / "a.md"
    doc.write_text(
        "见 [真](../_global/real.md) 和 [假](../_global/missing.md)。\n"
        "外链 [x](https://example.com) 不算。\n",
        encoding="utf-8",
    )
    findings = scan_references(doc, root=repo)
    targets = {f.target for f in findings}
    assert "../_global/missing.md" in targets  # 断链被抓
    assert "../_global/real.md" not in targets  # 有效链接不误报
    assert not any("example.com" in t for t in targets)  # 外链跳过


def test_anchor_ref_classified(tmp_path):
    repo = _make_repo(tmp_path)
    doc = repo / "docs" / "standards" / "concepts" / "b.md"
    doc.write_text("[代码](../../../src/gone.py#L195)\n", encoding="utf-8")
    findings = scan_references(doc, root=repo)
    assert len(findings) == 1
    assert findings[0].category == "broken_anchor"  # 带 # 的归为失效行锚


def test_discover_skips_archive(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "docs" / "plans" / "x" / "[2026-06-13]T" / "plan.md").write_text("# p", encoding="utf-8")
    (repo / "docs" / "plans" / "_archive" / "old" / "plan.md").write_text("# old", encoding="utf-8")
    targets = discover_targets(("plan",), root=repo)
    # 用相对仓库根的路径判断(避免 pytest tmp 目录名本身含 "_archive" 干扰)
    rels = {p.relative_to(repo).as_posix() for _k, p in targets}
    assert any("[2026-06-13]T" in r for r in rels)
    assert not any(r.startswith("docs/plans/_archive/") for r in rels)  # 归档被跳过


def test_run_reference_audit_aggregates(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "docs" / "standards" / "concepts" / "c.md").write_text(
        "[坏](./nope.md)\n", encoding="utf-8")
    res = run_reference_audit(root=repo, write=False)
    assert res["scanned_docs"] >= 2
    assert res["counts"]["broken_ref"] >= 1
    assert any(f["target"] == "./nope.md" for f in res["findings"])
