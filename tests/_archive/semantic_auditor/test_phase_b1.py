# [OMNI] origin=claude-code domain=services/semantic_auditor ts=2026-04-18T00:00:00Z
"""semantic_auditor Phase B1 单测 — 三个 HARD Router + 端到端。

覆盖：
  - standards_loader: YAML 加载 / kind 推断 / 标准匹配 / excerpt 取回（full/section）
  - ArtifactSelectorRouter: paths / full-scan / git-diff / 错误路径
  - StandardMatcherRouter: 匹配逻辑 / 无匹配 artifact
  - ExcerptRetrieverRouter: full + section + fallback
  - 三节点端到端跑通
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from omnicompany.protocol.anchor import VerdictKind  # noqa: E402
from omnicompany.packages.services.semantic_auditor.standards_loader import (  # noqa: E402
    load_standards_index,
    infer_kind,
    match_standards,
    retrieve_excerpt,
    _extract_sections,
)
from omnicompany.packages.services.semantic_auditor.routers import (  # noqa: E402
    ArtifactSelectorRouter,
    StandardMatcherRouter,
    ExcerptRetrieverRouter,
)
from omnicompany.packages.services.semantic_auditor.pipeline import (  # noqa: E402
    build_pipeline,
)


_YAML = """
standards:
  - id: TEST-FULL
    file: test_standard_full.md
    applies_to: [router]
    path_match:
      - "src/**/routers/**/*.py"
    excerpt_strategy: full

  - id: TEST-SECTION
    file: test_standard_section.md
    applies_to: [design_md]
    path_match:
      - "**/DESIGN.md"
    excerpt_strategy: section
    key_sections:
      - "## 核心部分"

kind_inference:
  - kind: router
    match:
      - "src/**/routers/**/*.py"
  - kind: design_md
    match:
      - "**/DESIGN.md"
"""

_STD_FULL = """# Test Full Standard
全文应该被整份返回。
包含多行。
"""

_STD_SECTION = """# Test Section Standard

## 前言
这部分不应出现。

## 核心部分
这部分**应该**出现。
包含二级子项:
- 子项 A
- 子项 B

## 附录
这部分不应出现。
"""


@pytest.fixture
def fake_root(tmp_path):
    """构造一个最小的 project_root，包含 standards-index.yaml 和测试 standards。"""
    std_dir = tmp_path / "docs" / "standards"
    std_dir.mkdir(parents=True)
    (std_dir / "standards-index.yaml").write_text(_YAML, encoding="utf-8")
    # 注意：index.file 是 relative to project_root，不是 docs/standards/
    # 所以 TEST-FULL.file=test_standard_full.md 实际找 project_root/test_standard_full.md
    (tmp_path / "test_standard_full.md").write_text(_STD_FULL, encoding="utf-8")
    (tmp_path / "test_standard_section.md").write_text(_STD_SECTION, encoding="utf-8")
    return tmp_path


# ═══ standards_loader ═══════════════════════════════════════════

class TestStandardsLoader:
    def test_load_index(self, fake_root):
        index = load_standards_index(fake_root)
        assert len(index.standards) == 2
        assert index.get("TEST-FULL").excerpt_strategy == "full"
        assert index.get("TEST-SECTION").excerpt_strategy == "section"
        assert len(index.kind_inference) == 2

    def test_load_missing_index(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_standards_index(tmp_path)

    def test_infer_kind_router(self, fake_root):
        index = load_standards_index(fake_root)
        assert infer_kind("src/omnicompany/packages/services/foo/routers/x.py", index) == "router"

    def test_infer_kind_design(self, fake_root):
        index = load_standards_index(fake_root)
        assert infer_kind("src/omnicompany/packages/services/foo/DESIGN.md", index) == "design_md"

    def test_infer_kind_none(self, fake_root):
        index = load_standards_index(fake_root)
        assert infer_kind("README.md", index) is None

    def test_match_standards_by_kind_and_path(self, fake_root):
        index = load_standards_index(fake_root)
        ids = match_standards("router", "src/omnicompany/routers/foo.py", index)
        assert "TEST-FULL" in ids

    def test_match_standards_no_match(self, fake_root):
        index = load_standards_index(fake_root)
        ids = match_standards("unknown", "src/random/x.py", index)
        assert ids == []

    def test_retrieve_excerpt_full(self, fake_root):
        index = load_standards_index(fake_root)
        text = retrieve_excerpt("TEST-FULL", index)
        assert "全文应该被整份返回" in text
        assert "包含多行" in text

    def test_retrieve_excerpt_section(self, fake_root):
        index = load_standards_index(fake_root)
        text = retrieve_excerpt("TEST-SECTION", index)
        assert "## 核心部分" in text
        assert "这部分**应该**出现" in text
        assert "## 前言" not in text
        assert "## 附录" not in text

    def test_retrieve_excerpt_unknown_id(self, fake_root):
        index = load_standards_index(fake_root)
        with pytest.raises(ValueError):
            retrieve_excerpt("NOT-EXIST", index)

    def test_extract_sections_fallback_empty_to_all(self):
        content = "## A\ntext\n"
        # key_sections 不匹配 → _extract_sections 返回空
        result = _extract_sections(content, ["## NotExists"])
        assert result == ""


# ═══ ArtifactSelectorRouter ══════════════════════════════════════

class TestArtifactSelector:
    def test_paths_input(self, fake_root):
        r = ArtifactSelectorRouter()
        v = r.run({
            "project_root": str(fake_root),
            "paths": ["src/omnicompany/routers/a.py", "README.md"],
        })
        assert v.kind == VerdictKind.PASS
        assert v.output["artifact_count"] == 2
        paths = [a["path"] for a in v.output["artifacts"]]
        assert "src/omnicompany/routers/a.py" in paths
        # 被 kind_inference 命中的 artifact 有 kind
        router_art = next(a for a in v.output["artifacts"] if a["path"].endswith("a.py"))
        assert router_art["kind"] == "router"
        # 没命中的 kind=None
        readme_art = next(a for a in v.output["artifacts"] if a["path"] == "README.md")
        assert readme_art["kind"] is None

    def test_missing_source_and_paths_fails(self, fake_root):
        r = ArtifactSelectorRouter()
        v = r.run({"project_root": str(fake_root)})
        assert v.kind == VerdictKind.FAIL
        assert "source" in v.output["reason"]

    def test_bad_source_fails(self, fake_root):
        r = ArtifactSelectorRouter()
        v = r.run({"project_root": str(fake_root), "source": "invalid"})
        assert v.kind == VerdictKind.FAIL

    def test_missing_index_fails_gracefully(self, tmp_path):
        r = ArtifactSelectorRouter()
        v = r.run({"project_root": str(tmp_path), "paths": []})
        assert v.kind == VerdictKind.FAIL
        assert "standards-index" in v.output["reason"]

    def test_non_dict_input(self):
        r = ArtifactSelectorRouter()
        v = r.run("not a dict")
        assert v.kind == VerdictKind.FAIL


# ═══ StandardMatcherRouter ═══════════════════════════════════════

class TestStandardMatcher:
    def test_matches_router_standard(self, fake_root):
        r = StandardMatcherRouter()
        v = r.run({
            "project_root": str(fake_root),
            "artifacts": [
                {"path": "src/omnicompany/routers/x.py", "kind": "router"},
            ],
        })
        assert v.kind == VerdictKind.PASS
        assert v.output["target_count"] == 1
        assert "TEST-FULL" in v.output["audit_targets"][0]["applicable_standards"]

    def test_unmatched_artifact_counted(self, fake_root):
        r = StandardMatcherRouter()
        v = r.run({
            "project_root": str(fake_root),
            "artifacts": [
                {"path": "random/path.txt", "kind": None},
            ],
        })
        assert v.kind == VerdictKind.PASS
        assert v.output["target_count"] == 0
        assert v.output["unmatched_artifacts"] == 1

    def test_missing_artifacts_key(self, fake_root):
        r = StandardMatcherRouter()
        v = r.run({"project_root": str(fake_root)})
        assert v.kind == VerdictKind.FAIL

    def test_artifacts_not_list(self, fake_root):
        r = StandardMatcherRouter()
        v = r.run({"project_root": str(fake_root), "artifacts": "not list"})
        assert v.kind == VerdictKind.FAIL


# ═══ ExcerptRetrieverRouter ══════════════════════════════════════

class TestExcerptRetriever:
    def test_full_and_section_mixed(self, fake_root):
        r = ExcerptRetrieverRouter()
        v = r.run({
            "project_root": str(fake_root),
            "audit_targets": [
                {
                    "artifact": {"path": "src/omnicompany/routers/x.py", "kind": "router"},
                    "applicable_standards": ["TEST-FULL"],
                },
                {
                    "artifact": {"path": "services/foo/DESIGN.md", "kind": "design_md"},
                    "applicable_standards": ["TEST-SECTION"],
                },
            ],
        })
        assert v.kind == VerdictKind.PASS
        assert v.output["excerpt_count"] == 2
        excerpts = v.output["excerpts"]
        full_ex = next(e for e in excerpts if e["standard_id"] == "TEST-FULL")
        assert "全文应该被整份返回" in full_ex["excerpt_text"]
        section_ex = next(e for e in excerpts if e["standard_id"] == "TEST-SECTION")
        assert "## 核心部分" in section_ex["excerpt_text"]
        assert "## 附录" not in section_ex["excerpt_text"]

    def test_unknown_standard_goes_to_failed(self, fake_root):
        r = ExcerptRetrieverRouter()
        v = r.run({
            "project_root": str(fake_root),
            "audit_targets": [
                {
                    "artifact": {"path": "x.py", "kind": None},
                    "applicable_standards": ["NOT-EXIST"],
                },
            ],
        })
        assert v.kind == VerdictKind.PASS
        assert v.output["excerpt_count"] == 0
        assert len(v.output["failed_retrievals"]) == 1


# ═══ 端到端三节点串联 ══════════════════════════════════════════

class TestEndToEnd:
    def test_three_node_chain(self, fake_root):
        """ArtifactSelector → StandardMatcher → ExcerptRetriever 手工串联"""
        # 写一个模拟 Router 文件，让 full-scan 能扫到
        routers_dir = fake_root / "src" / "omnicompany" / "routers"
        routers_dir.mkdir(parents=True)
        (routers_dir / "fake_router.py").write_text("# mock router\n", encoding="utf-8")

        selector = ArtifactSelectorRouter()
        matcher = StandardMatcherRouter()
        retriever = ExcerptRetrieverRouter()

        v1 = selector.run({"project_root": str(fake_root), "source": "full-scan"})
        assert v1.kind == VerdictKind.PASS

        # chain 上游 output → 下游 input
        v2 = matcher.run(v1.output)
        assert v2.kind == VerdictKind.PASS

        v3 = retriever.run(v2.output)
        assert v3.kind == VerdictKind.PASS
        assert v3.output["excerpt_count"] >= 1

    def test_pipeline_spec_builds(self):
        """build_pipeline() 能产生合法 PipelineSpec；B1 三节点必在前三位。"""
        spec = build_pipeline()
        assert spec.entry == "artifact_selector"
        node_ids = [n.id for n in spec.nodes]
        assert node_ids[:3] == ["artifact_selector", "standard_matcher", "excerpt_retriever"]
