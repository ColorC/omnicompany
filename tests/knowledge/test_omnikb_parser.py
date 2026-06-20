# [OMNI] origin=claude-code domain=tests/omnikb ts=2026-04-09T00:00:00Z
"""OmniKB parser & index tests.

验证:
  1. 4 种新 entry 类型 (karch/kdec/kexp/krepo) 的 parser 能正确解析 fixture
  2. KBIndex.from_store 能找到所有 fixtures
  3. KBIndex.find(types=...) 过滤正确
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnicompany.packages.services.knowledge import (
    KArchitectureEntry,
    KDecisionEntry,
    KExperimentEntry,
    KRepoArchitectEntry,
    parse_kb_document,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "knowledge"


def _load(name: str):
    path = FIXTURE_DIR / name
    assert path.exists(), f"fixture {name} not found"
    return parse_kb_document(path)


def test_karch_fixture():
    entry = _load("sample_karch.md")
    assert isinstance(entry, KArchitectureEntry)
    assert entry.id == "kb.arch.sample"
    assert entry.name == "Sample Architecture Topic"
    assert entry.scope == "omnicompany"
    assert len(entry.code_anchors) == 2
    assert entry.code_anchors[0] == "src/omnicompany/packages/services/knowledge/schema.py"
    assert "kb.decision.sample" in entry.related_decisions
    assert entry.maturity == "stable"


def test_kdec_fixture():
    entry = _load("sample_kdec.md")
    assert isinstance(entry, KDecisionEntry)
    assert entry.id == "kb.decision.sample"
    assert entry.status == "decided"
    assert entry.date_decided == "2026-04-09"
    assert len(entry.drivers) == 1
    assert len(entry.options_considered) == 2
    assert entry.decision.startswith("为每种")
    assert "kb.arch.sample" in entry.related_karchs


def test_kexp_fixture():
    entry = _load("sample_kexp.md")
    assert isinstance(entry, KExperimentEntry)
    assert entry.id == "kb.experiment.sample"
    assert entry.maturity == "living"
    assert entry.date_started == "2026-04-09"
    assert entry.date_concluded == ""
    assert entry.hypothesis.startswith("golden fixtures")
    assert len(entry.samples_run) == 2
    assert entry.samples_run[0]["outcome"] == "ok"
    assert "kb.decision.sample" in entry.related_decisions


def test_krepo_fixture():
    entry = _load("sample_krepo.md")
    assert isinstance(entry, KRepoArchitectEntry)
    assert entry.id == "kb.repo.sample__fixture"
    assert entry.scope == "external:sample/fixture"
    assert entry.download_state == "deleted"
    assert len(entry.capability_areas) == 1
    assert entry.capability_areas[0]["name"] == "Sample capability"
    assert "docs/" in entry.known_unread_areas


def test_unknown_type_returns_none(tmp_path):
    """含未知 omnikb_type 的 md 应返回 None, 不抛异常。"""
    bad = tmp_path / "bad.md"
    bad.write_text(
        "---\nomnikb_type: nonsense\nid: kb.foo.bar\nname: Bad\n---\n\nbody",
        encoding="utf-8",
    )
    assert parse_kb_document(bad) is None


def test_missing_frontmatter_returns_none(tmp_path):
    """无 frontmatter 的 md 应返回 None。"""
    bad = tmp_path / "plain.md"
    bad.write_text("# Plain markdown\n\nNo frontmatter here.\n", encoding="utf-8")
    assert parse_kb_document(bad) is None


def test_parser_tolerates_omnimark_header(tmp_path):
    """OmniGuardian guarded_write 会在文件顶部贴 `# [OMNI] ...` 头, parser 必须能跳过。

    没有这个容忍度, 所有经 guarded_write 写的 KB 文件都会变成 None。
    """
    stamped = tmp_path / "stamped_karch.md"
    stamped.write_text(
        "# [OMNI] origin=internal-engine domain=services/knowledge ts=2026-04-09T00:00:00Z\n"
        "---\n"
        "omnikb_type: karch\n"
        "id: kb.arch.stamped\n"
        "name: Stamped\n"
        "tags: []\n"
        "maturity: draft\n"
        "scope: omnicompany\n"
        "---\n\n"
        "# Body\n",
        encoding="utf-8",
    )
    entry = parse_kb_document(stamped)
    assert entry is not None
    assert isinstance(entry, KArchitectureEntry)
    assert entry.id == "kb.arch.stamped"


def test_index_text_search(tmp_path, monkeypatch):
    """KBIndex.text_search 能按 name/description/tags 子串匹配。

    这里建一个临时 project_root 只含 fixtures, 避免干扰真实 index。
    """
    from omnicompany.packages.services.knowledge import KBStore, KBIndex

    # 建临时目录结构
    fake_root = tmp_path / "fake_project"
    (fake_root / "data" / "knowledge" / "architecture").mkdir(parents=True)
    (fake_root / "data" / "knowledge" / "decisions").mkdir(parents=True)

    import shutil
    shutil.copy(FIXTURE_DIR / "sample_karch.md",
                fake_root / "data" / "knowledge" / "architecture" / "sample.md")
    shutil.copy(FIXTURE_DIR / "sample_kdec.md",
                fake_root / "data" / "knowledge" / "decisions" / "sample.md")

    store = KBStore(fake_root)
    index = KBIndex.from_store(store)

    stats = index.stats()
    assert stats["karch"] == 1
    assert stats["kdec"] == 1

    # 文本搜索
    hits = index.text_search("sample")
    assert len(hits) >= 2

    # 类型过滤
    archs = index.find(types=["karch"])
    assert len(archs) == 1
    assert archs[0].omnikb_type == "karch"
