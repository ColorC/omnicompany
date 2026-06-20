"""OmniMark 单元测试

覆盖：
  1. parse_omnimark — 各种格式、缺字段、旧格式兼容
  2. stamp_file — 注入、跳过、覆盖、位置（shebang / 无内容）
  3. _inject_header — shebang 保留
  4. _infer_domain — 路径推断
  5. file_fingerprint — 一致性
  6. to_comment_line — 渲染正确字段
"""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.core.omnimark import (
    OmniMarkFields,
    parse_omnimark,
    stamp_file,
    file_fingerprint,
    _inject_header,
    _infer_domain,
)


# ─── parse_omnimark ──────────────────────────────────────────────

def test_parse_canonical_format():
    content = "# [OMNI] origin=human domain=omnicompany/core ts=2026-04-05T00:00:00Z\n"
    m = parse_omnimark(content)
    assert m is not None
    assert m.origin == "human"
    assert m.domain == "omnicompany/core"
    assert m.ts == "2026-04-05T00:00:00Z"


def test_parse_all_fields():
    content = (
        "# [OMNI] origin=sw-implement domain=packages/gameplay_system"
        " agent=claude-sonnet-4-6 ts=2026-04-05T12:00:00Z"
        " trace=trc_abc123 node=implementor-router status=active\n"
    )
    m = parse_omnimark(content)
    assert m.origin == "sw-implement"
    assert m.agent == "claude-sonnet-4-6"
    assert m.trace == "trc_abc123"
    assert m.node == "implementor-router"
    assert m.status == "active"


def test_parse_old_format_created_by_intent():
    """旧格式（created_by + intent）向后兼容。"""
    content = "# [OMNI] origin=omnicompany created_by=omnicompany intent=guardian-patrol\n"
    m = parse_omnimark(content)
    assert m is not None
    assert m.origin == "omnicompany"
    assert m.created_by == "omnicompany"
    assert m.intent == "guardian-patrol"


def test_parse_no_omnimark_returns_none():
    content = "import os\ndef foo(): pass\n"
    assert parse_omnimark(content) is None


def test_parse_empty_string_returns_none():
    assert parse_omnimark("") is None


def test_parse_from_path(tmp_path):
    f = tmp_path / "test.py"
    f.write_text(
        "# [OMNI] origin=human domain=test ts=2026-04-05T00:00:00Z\n"
        "import os\n",
        encoding="utf-8",
    )
    m = parse_omnimark(f)
    assert m is not None
    assert m.origin == "human"


def test_parse_path_nonexistent(tmp_path):
    """不存在的文件路径返回 None。"""
    assert parse_omnimark(tmp_path / "no_such_file.py") is None


def test_parse_only_scans_first_30_lines():
    """OmniMark must be within the first 30 lines."""
    lines = ["# ordinary comment\n"] * 30
    lines.append("# [OMNI] origin=human domain=test ts=2026-04-05T00:00:00Z\n")
    assert parse_omnimark("".join(lines)) is None


def test_parse_on_line_19_is_valid():
    lines = ["# ordinary comment\n"] * 18
    lines.append("# [OMNI] origin=human domain=test ts=2026-04-05T00:00:00Z\n")
    m = parse_omnimark("".join(lines))
    assert m is not None
    assert m.origin == "human"


def test_parse_html_comment_format():
    """Markdown/HTML 风格 <!-- [OMNI] ... -->。"""
    content = "<!-- [OMNI] origin=claude-code domain=docs ts=2026-04-05T00:00:00Z -->\n"
    m = parse_omnimark(content)
    assert m is not None
    assert m.origin == "claude-code"


def test_parse_unknown_fields_go_to_extra():
    content = "# [OMNI] origin=human ts=2026-04-05T00:00:00Z custom_field=foobar\n"
    m = parse_omnimark(content)
    assert m.extra.get("custom_field") == "foobar"


# ─── to_comment_line ─────────────────────────────────────────────

def test_to_comment_line_minimal():
    m = OmniMarkFields(origin="human", ts="2026-04-05T00:00:00Z")
    line = m.to_comment_line()
    assert line.startswith("# [OMNI]")
    assert "origin=human" in line
    assert "ts=2026-04-05T00:00:00Z" in line


def test_to_comment_line_omits_empty_fields():
    m = OmniMarkFields(origin="human", ts="2026-04-05T00:00:00Z")
    line = m.to_comment_line()
    assert "agent=" not in line
    assert "trace=" not in line
    assert "node=" not in line


def test_to_comment_line_includes_all_filled_fields():
    m = OmniMarkFields(
        origin="sw-implement",
        domain="packages/gameplay_system",
        agent="claude-sonnet-4-6",
        ts="2026-04-05T12:00:00Z",
        trace="trc_abc",
        node="impl-router",
    )
    line = m.to_comment_line()
    assert "domain=packages/gameplay_system" in line
    assert "agent=claude-sonnet-4-6" in line
    assert "trace=trc_abc" in line
    assert "node=impl-router" in line


def test_to_comment_line_omits_default_status():
    """status=active 是默认值，不应输出（减少噪音）。"""
    m = OmniMarkFields(origin="human", ts="2026-04-05T00:00:00Z", status="active")
    line = m.to_comment_line()
    assert "status=" not in line


def test_to_comment_line_includes_non_default_status():
    m = OmniMarkFields(origin="human", ts="2026-04-05T00:00:00Z", status="quarantined")
    line = m.to_comment_line()
    assert "status=quarantined" in line


# ─── _inject_header ──────────────────────────────────────────────

def test_inject_at_top_of_empty_file():
    result = _inject_header("", "# [OMNI] origin=human ts=X", ".py")
    assert result.startswith("# [OMNI]")


def test_inject_after_shebang():
    content = "#!/usr/bin/env python3\nimport os\n"
    result = _inject_header(content, "# [OMNI] origin=human ts=X", ".py")
    lines = result.splitlines()
    assert lines[0] == "#!/usr/bin/env python3"
    assert lines[1] == "# [OMNI] origin=human ts=X"


def test_inject_after_coding_declaration():
    content = "# -*- coding: utf-8 -*-\nimport os\n"
    result = _inject_header(content, "# [OMNI] origin=human ts=X", ".py")
    lines = result.splitlines()
    assert lines[0] == "# -*- coding: utf-8 -*-"
    assert lines[1] == "# [OMNI] origin=human ts=X"


def test_inject_before_docstring():
    content = '"""Module docstring."""\nimport os\n'
    result = _inject_header(content, "# [OMNI] origin=human ts=X", ".py")
    lines = result.splitlines()
    assert lines[0] == "# [OMNI] origin=human ts=X"
    assert '"""Module docstring."""' in result


# ─── _infer_domain ───────────────────────────────────────────────

def test_infer_domain_from_packages_path():
    p = Path("src/omnicompany/packages/domains/gameplay_system/benchmark/flows/foo.py")
    domain = _infer_domain(p)
    assert domain == "domains/gameplay_system"


def test_infer_domain_from_packages_shallow():
    p = Path("src/omnicompany/packages/services/_core/guardian/_patrol_shim.py")
    domain = _infer_domain(p)
    assert domain == "services/_core"


def test_infer_domain_runtime():
    p = Path("src/omnicompany/runtime/runner.py")
    domain = _infer_domain(p)
    assert domain == "omnicompany/runtime"


def test_infer_domain_core():
    p = Path("src/omnicompany/core/omnimark.py")
    domain = _infer_domain(p)
    assert domain == "omnicompany/core"


def test_infer_domain_unknown_path():
    p = Path("random/path/file.py")
    domain = _infer_domain(p)
    assert domain == ""  # 无法推断，返回空


# ─── stamp_file ──────────────────────────────────────────────────

def test_stamp_file_injects_header(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("import os\n", encoding="utf-8")
    ok = stamp_file(f, origin="human")
    assert ok
    content = f.read_text(encoding="utf-8")
    assert "# [OMNI]" in content
    assert "origin=human" in content


def test_stamp_file_skips_if_already_stamped(tmp_path):
    f = tmp_path / "foo.py"
    original = "# [OMNI] origin=human ts=2026-04-05T00:00:00Z\nimport os\n"
    f.write_text(original, encoding="utf-8")

    ok = stamp_file(f, origin="workflow-factory")
    assert ok
    # 内容不应被修改（origin 还是 human）
    assert f.read_text(encoding="utf-8") == original


def test_stamp_file_overwrite_replaces_header(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text(
        "# [OMNI] origin=human ts=2026-04-05T00:00:00Z\nimport os\n",
        encoding="utf-8",
    )
    stamp_file(f, origin="workflow-factory", overwrite=True)
    content = f.read_text(encoding="utf-8")
    # 新的 origin 应该在里面
    assert "origin=workflow-factory" in content


def test_stamp_file_nonexistent_returns_false(tmp_path):
    ok = stamp_file(tmp_path / "no_such_file.py", origin="human")
    assert not ok


def test_stamp_file_preserves_shebang(tmp_path):
    f = tmp_path / "script.py"
    f.write_text("#!/usr/bin/env python3\nimport os\n", encoding="utf-8")
    stamp_file(f, origin="human")
    lines = f.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "#!/usr/bin/env python3"
    assert "# [OMNI]" in lines[1]


def test_stamp_file_ts_is_set(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("import os\n", encoding="utf-8")
    stamp_file(f, origin="human")
    content = f.read_text(encoding="utf-8")
    assert "ts=2026" in content or "ts=20" in content  # 时间戳含年份


def test_stamp_file_pending_review_status_for_unknown(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("import os\n", encoding="utf-8")
    stamp_file(f, origin="unknown", status="pending-review")
    content = f.read_text(encoding="utf-8")
    assert "status=pending-review" in content


# ─── file_fingerprint ────────────────────────────────────────────

def test_fingerprint_is_consistent(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("import os\n", encoding="utf-8")
    fp1 = file_fingerprint(f)
    fp2 = file_fingerprint(f)
    assert fp1 == fp2
    assert fp1.startswith("sha256:")


def test_fingerprint_changes_with_content(tmp_path):
    f = tmp_path / "foo.py"
    f.write_text("import os\n", encoding="utf-8")
    fp1 = file_fingerprint(f)
    f.write_text("import sys\n", encoding="utf-8")
    fp2 = file_fingerprint(f)
    assert fp1 != fp2


def test_fingerprint_nonexistent_file(tmp_path):
    fp = file_fingerprint(tmp_path / "no_such.py")
    assert fp == "sha256:error"


# ─── is_canonical ────────────────────────────────────────────────

def test_is_canonical_requires_origin_and_ts():
    m = OmniMarkFields(origin="human", ts="2026-04-05T00:00:00Z")
    assert m.is_canonical()


def test_is_canonical_missing_ts():
    m = OmniMarkFields(origin="human", ts="")
    assert not m.is_canonical()


def test_is_canonical_missing_origin():
    m = OmniMarkFields(origin="", ts="2026-04-05T00:00:00Z")
    assert not m.is_canonical()


def test_old_format_not_canonical():
    """旧格式（有 created_by/intent 但无 ts）不算 canonical。"""
    content = "# [OMNI] origin=omnicompany created_by=omnicompany intent=patrol\n"
    m = parse_omnimark(content)
    assert m is not None
    assert not m.is_canonical()  # 没有 ts
