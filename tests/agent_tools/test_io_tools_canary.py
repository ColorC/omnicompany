"""第二波核心 IO 工具 canary 测试 (2026-05-04 立).

哲学: canary 系统健康 — 任一 FAIL 表示对应工具不再可用.

覆盖:
  - FileReadRouter (Read): 读文件 + cat -n + offset/limit + 错误分支
  - FileEditRouter (Edit): exact replace + 唯一性 + replace_all
  - GlobRouter (Glob): glob 匹配 + mtime 排序 + head_limit
  - GrepRouter (Grep): 三种 output_mode + ripgrep/Python fallback
  - NotebookEditRouter (NotebookEdit): replace / insert / delete

注: 这里测 _execute() 的核心逻辑, 不走完整 Router.run() (那需要 bus + asyncio).
完整 Router 行为有 SingleToolRouter 基类自身测试覆盖.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.agent.routers.single_tool import (
    ToolContext,
    ToolExecutionError,
)
from omnicompany.packages.services._core.agent.routers.file_read import FileReadRouter
from omnicompany.packages.services._core.agent.routers.file_edit import FileEditRouter
from omnicompany.packages.services._core.agent.routers.glob_search import GlobRouter
from omnicompany.packages.services._core.agent.routers.grep_search import GrepRouter
from omnicompany.packages.services._core.agent.routers.notebook_edit import NotebookEditRouter


@pytest.fixture
def empty_ctx():
    return ToolContext(cwd=str(Path.cwd()), project_root=str(Path.cwd()))


def _make_router_no_init(cls):
    """跳过 SingleToolRouter.__init__ (它强制 bus 不为 None) 直接造对象, 测 _execute."""
    return cls.__new__(cls)


# ─── FileReadRouter ───────────────────────────────────────────────


class TestFileReadCanary:
    def test_basic_read(self, tmp_path, empty_ctx):
        f = tmp_path / "hello.txt"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")
        r = _make_router_no_init(FileReadRouter)
        out = r._execute({"file_path": str(f)}, empty_ctx)
        assert "line1" in out and "line2" in out and "line3" in out
        assert "1\tline1" in out  # cat -n 格式

    def test_offset_limit(self, tmp_path, empty_ctx):
        f = tmp_path / "many.txt"
        f.write_text("\n".join(f"line{i}" for i in range(1, 11)) + "\n", encoding="utf-8")
        r = _make_router_no_init(FileReadRouter)
        out = r._execute({"file_path": str(f), "offset": 5, "limit": 2}, empty_ctx)
        # offset=5 → 从 line5 开始, limit=2 → line5+line6
        assert "line5" in out and "line6" in out
        assert "line4" not in out
        assert "line7" not in out

    def test_relative_path_rejected(self, empty_ctx):
        r = _make_router_no_init(FileReadRouter)
        with pytest.raises(ToolExecutionError, match="absolute"):
            r._execute({"file_path": "relative/file.txt"}, empty_ctx)

    def test_nonexistent_rejected(self, tmp_path, empty_ctx):
        r = _make_router_no_init(FileReadRouter)
        # 用 tmp_path 下不存在的子路径 (绝对但不存在)
        ghost = tmp_path / "ghost_file.txt"
        with pytest.raises(ToolExecutionError, match="does not exist"):
            r._execute({"file_path": str(ghost)}, empty_ctx)

    def test_directory_rejected(self, tmp_path, empty_ctx):
        r = _make_router_no_init(FileReadRouter)
        with pytest.raises(ToolExecutionError, match="directory"):
            r._execute({"file_path": str(tmp_path)}, empty_ctx)

    def test_empty_file(self, tmp_path, empty_ctx):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        r = _make_router_no_init(FileReadRouter)
        out = r._execute({"file_path": str(f)}, empty_ctx)
        assert "empty" in out.lower() or out == "(file is empty or offset past end)"


# ─── FileEditRouter ───────────────────────────────────────────────


class TestFileEditCanary:
    def test_basic_replace(self, tmp_path, empty_ctx):
        f = tmp_path / "edit.txt"
        f.write_text("hello world\nfoo bar\n", encoding="utf-8")
        r = _make_router_no_init(FileEditRouter)
        out = r._execute({
            "file_path": str(f),
            "old_string": "hello world",
            "new_string": "hi earth",
        }, empty_ctx)
        assert "1 occurrence" in out
        assert f.read_text(encoding="utf-8") == "hi earth\nfoo bar\n"

    def test_non_unique_requires_replace_all(self, tmp_path, empty_ctx):
        f = tmp_path / "dup.txt"
        f.write_text("foo\nfoo\nfoo\n", encoding="utf-8")
        r = _make_router_no_init(FileEditRouter)
        with pytest.raises(ToolExecutionError, match="3 times"):
            r._execute({
                "file_path": str(f),
                "old_string": "foo",
                "new_string": "bar",
            }, empty_ctx)

    def test_replace_all(self, tmp_path, empty_ctx):
        f = tmp_path / "dup.txt"
        f.write_text("foo\nfoo\nfoo\n", encoding="utf-8")
        r = _make_router_no_init(FileEditRouter)
        out = r._execute({
            "file_path": str(f),
            "old_string": "foo",
            "new_string": "bar",
            "replace_all": True,
        }, empty_ctx)
        assert "3 occurrence" in out
        assert f.read_text(encoding="utf-8") == "bar\nbar\nbar\n"

    def test_not_found(self, tmp_path, empty_ctx):
        f = tmp_path / "x.txt"
        f.write_text("hello", encoding="utf-8")
        r = _make_router_no_init(FileEditRouter)
        with pytest.raises(ToolExecutionError, match="not found"):
            r._execute({
                "file_path": str(f),
                "old_string": "missing",
                "new_string": "whatever",
            }, empty_ctx)

    def test_identical_strings_rejected(self, tmp_path, empty_ctx):
        f = tmp_path / "x.txt"
        f.write_text("hello", encoding="utf-8")
        r = _make_router_no_init(FileEditRouter)
        with pytest.raises(ToolExecutionError, match="identical"):
            r._execute({
                "file_path": str(f),
                "old_string": "hello",
                "new_string": "hello",
            }, empty_ctx)

    def test_empty_old_string_rejected(self, tmp_path, empty_ctx):
        f = tmp_path / "x.txt"
        f.write_text("hello", encoding="utf-8")
        r = _make_router_no_init(FileEditRouter)
        with pytest.raises(ToolExecutionError, match="empty"):
            r._execute({
                "file_path": str(f),
                "old_string": "",
                "new_string": "x",
            }, empty_ctx)


# ─── GlobRouter ───────────────────────────────────────────────────


class TestGlobCanary:
    def test_basic_glob(self, tmp_path):
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.py").write_text("y")
        (tmp_path / "c.txt").write_text("z")
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))

        r = _make_router_no_init(GlobRouter)
        out = r._execute({"pattern": "*.py"}, ctx)
        assert "a.py" in out and "b.py" in out
        assert "c.txt" not in out

    def test_recursive_glob(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "top.py").write_text("x")
        (tmp_path / "sub" / "deep.py").write_text("y")
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))

        r = _make_router_no_init(GlobRouter)
        out = r._execute({"pattern": "**/*.py"}, ctx)
        assert "top.py" in out and "deep.py" in out

    def test_no_matches(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _make_router_no_init(GlobRouter)
        out = r._execute({"pattern": "*.xyz"}, ctx)
        assert "No matches" in out

    def test_head_limit(self, tmp_path):
        for i in range(10):
            (tmp_path / f"f{i}.py").write_text(str(i))
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _make_router_no_init(GlobRouter)
        out = r._execute({"pattern": "*.py", "head_limit": 3}, ctx)
        # 3 行结果 + 1 行 "truncated" 提示
        non_empty = [ln for ln in out.split("\n") if ln.strip()]
        assert len(non_empty) <= 4

    def test_mtime_order(self, tmp_path):
        """新文件应排在前."""
        import time
        f1 = tmp_path / "old.py"
        f1.write_text("o")
        time.sleep(0.05)
        f2 = tmp_path / "new.py"
        f2.write_text("n")
        # 强制设 mtime
        import os
        os.utime(f1, (1000000, 1000000))
        os.utime(f2, (2000000, 2000000))

        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _make_router_no_init(GlobRouter)
        out = r._execute({"pattern": "*.py"}, ctx)
        # new.py 行号靠前
        lines = out.split("\n")
        new_idx = next((i for i, l in enumerate(lines) if "new.py" in l), -1)
        old_idx = next((i for i, l in enumerate(lines) if "old.py" in l), -1)
        assert 0 <= new_idx < old_idx, f"new.py 应在 old.py 前面: {lines}"


# ─── GrepRouter ───────────────────────────────────────────────────


class TestGrepCanary:
    def test_files_with_matches_default(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello world\n")
        (tmp_path / "b.txt").write_text("goodbye\n")
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _make_router_no_init(GrepRouter)
        out = r._execute({"pattern": "hello"}, ctx)
        assert "a.txt" in out
        assert "b.txt" not in out

    def test_count_mode(self, tmp_path):
        f = tmp_path / "f.txt"
        f.write_text("hello\nhello\nworld\n")
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _make_router_no_init(GrepRouter)
        out = r._execute({"pattern": "hello", "output_mode": "count"}, ctx)
        # ripgrep -c: file:count, fallback: same
        assert "2" in out

    def test_content_mode(self, tmp_path):
        f = tmp_path / "f.txt"
        f.write_text("apple\nbanana\ncherry\n")
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _make_router_no_init(GrepRouter)
        out = r._execute({"pattern": "ban", "output_mode": "content"}, ctx)
        assert "banana" in out

    def test_no_matches(self, tmp_path):
        (tmp_path / "f.txt").write_text("nothing here")
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _make_router_no_init(GrepRouter)
        out = r._execute({"pattern": "xyzqwer", "output_mode": "files_with_matches"}, ctx)
        assert "No matches" in out


# ─── NotebookEditRouter ───────────────────────────────────────────


def _make_notebook(path: Path, cells: list[dict]) -> None:
    nb = {
        "cells": cells,
        "metadata": {"kernelspec": {"name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1)
        f.write("\n")


class TestNotebookEditCanary:
    def test_replace_cell(self, tmp_path, empty_ctx):
        nb = tmp_path / "x.ipynb"
        _make_notebook(nb, [
            {"cell_type": "code", "metadata": {}, "source": ["print(1)"], "outputs": [], "execution_count": None},
            {"cell_type": "code", "metadata": {}, "source": ["print(2)"], "outputs": [], "execution_count": None},
        ])
        r = _make_router_no_init(NotebookEditRouter)
        out = r._execute({
            "notebook_path": str(nb),
            "cell_number": 0,
            "new_source": "print(99)",
            "edit_mode": "replace",
        }, empty_ctx)
        assert "replaced" in out

        with nb.open(encoding="utf-8") as f:
            data = json.load(f)
        assert data["cells"][0]["source"] == ["print(99)"]
        # outputs 复位
        assert data["cells"][0]["outputs"] == []
        assert data["cells"][0]["execution_count"] is None

    def test_insert_cell(self, tmp_path, empty_ctx):
        nb = tmp_path / "x.ipynb"
        _make_notebook(nb, [
            {"cell_type": "code", "metadata": {}, "source": ["a"], "outputs": [], "execution_count": None},
        ])
        r = _make_router_no_init(NotebookEditRouter)
        r._execute({
            "notebook_path": str(nb),
            "cell_number": 0,
            "new_source": "# Title",
            "edit_mode": "insert",
            "cell_type": "markdown",
        }, empty_ctx)
        with nb.open(encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["cells"]) == 2
        assert data["cells"][0]["cell_type"] == "markdown"
        assert data["cells"][1]["source"] == ["a"]

    def test_delete_cell(self, tmp_path, empty_ctx):
        nb = tmp_path / "x.ipynb"
        _make_notebook(nb, [
            {"cell_type": "code", "metadata": {}, "source": ["a"], "outputs": [], "execution_count": None},
            {"cell_type": "code", "metadata": {}, "source": ["b"], "outputs": [], "execution_count": None},
            {"cell_type": "code", "metadata": {}, "source": ["c"], "outputs": [], "execution_count": None},
        ])
        r = _make_router_no_init(NotebookEditRouter)
        r._execute({
            "notebook_path": str(nb),
            "cell_number": 1,
            "edit_mode": "delete",
        }, empty_ctx)
        with nb.open(encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["cells"]) == 2
        assert data["cells"][0]["source"] == ["a"]
        assert data["cells"][1]["source"] == ["c"]

    def test_out_of_range(self, tmp_path, empty_ctx):
        nb = tmp_path / "x.ipynb"
        _make_notebook(nb, [
            {"cell_type": "code", "metadata": {}, "source": ["a"], "outputs": [], "execution_count": None},
        ])
        r = _make_router_no_init(NotebookEditRouter)
        with pytest.raises(ToolExecutionError, match="out of range"):
            r._execute({
                "notebook_path": str(nb),
                "cell_number": 99,
                "new_source": "x",
            }, empty_ctx)

    def test_non_ipynb_rejected(self, tmp_path, empty_ctx):
        f = tmp_path / "notebook.txt"
        f.write_text("not a notebook")
        r = _make_router_no_init(NotebookEditRouter)
        with pytest.raises(ToolExecutionError, match="ipynb"):
            r._execute({
                "notebook_path": str(f),
                "cell_number": 0,
                "new_source": "x",
            }, empty_ctx)


# ─── 集成: 工具元数据和 schema 完整性 ────────────────────────────


class TestToolSchemas:
    """canary: 5 个工具都有完整的 TOOL_NAME / DESCRIPTION / INPUT_SCHEMA."""

    @pytest.mark.parametrize("router_cls", [
        FileReadRouter, FileEditRouter, GlobRouter, GrepRouter, NotebookEditRouter,
    ])
    def test_required_classvars(self, router_cls):
        assert router_cls.TOOL_NAME, f"{router_cls.__name__} 缺 TOOL_NAME"
        assert router_cls.DESCRIPTION, f"{router_cls.__name__} 缺 DESCRIPTION"
        assert isinstance(router_cls.INPUT_SCHEMA, dict)
        assert "properties" in router_cls.INPUT_SCHEMA
        assert "required" in router_cls.INPUT_SCHEMA

    @pytest.mark.parametrize("router_cls,expected_name", [
        (FileReadRouter, "Read"),
        (FileEditRouter, "Edit"),
        (GlobRouter, "Glob"),
        (GrepRouter, "Grep"),
        (NotebookEditRouter, "NotebookEdit"),
    ])
    def test_tool_names_match_claude_code(self, router_cls, expected_name):
        """对齐 claude-code 工具名 (大小写敏感)."""
        assert router_cls.TOOL_NAME == expected_name
