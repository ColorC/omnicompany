"""Wave 5+7 — FileRead L1+L2 + Read→Edit 状态机 e2e 测试 (2026-05-04 立).

覆盖:
  - FileRead L1: DESCRIPTION 含 cc 原文关键句 (image / PDF / Jupyter / screenshot)
  - FileRead L1: INPUT_SCHEMA 含 pages 字段
  - FileRead L2: image (.png/.jpg) → 报错指引
  - FileRead L2: PDF (.pdf) → 报错指引 + pages 参数提示
  - FileRead L2: Jupyter (.ipynb) → 报错指引 NotebookEdit
  - FileRead L5: 成功读后 abs_path 进 ctx.read_files
  - FileEdit L5: abs_path 不在 ctx.read_files → 报"先 Read"错
  - FileEdit L5: 已 Read 的 abs_path → 编辑通过
  - WriteFile L5: 写入后 abs_path 进 ctx.read_files (Write→Edit 流不破)

注: ctx.read_files 没注入 (老 ctx) 时检查兼容跳过 (向下兼容).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.agent.routers.file_read import FileReadRouter
from omnicompany.packages.services._core.agent.routers.file_edit import FileEditRouter
from omnicompany.packages.services._core.agent.routers.write_file import WriteFileRouter
from omnicompany.packages.services._core.agent.routers.single_tool import (
    ToolContext,
    ToolExecutionError,
)


def _new(cls):
    """绕 SingleToolRouter __init__ bus 校验."""
    return cls.__new__(cls)


# ═══════════════════════════════════════════════════════════════════════
# L1 schema — DESCRIPTION + INPUT_SCHEMA 跟 cc 原文对照
# ═══════════════════════════════════════════════════════════════════════


class TestFileReadL1Schema:
    def test_description_has_image_line(self):
        desc = FileReadRouter.DESCRIPTION
        # cc 原文关键句
        assert "Claude Code to read images" in desc
        assert "PNG, JPG" in desc

    def test_description_has_pdf_line(self):
        desc = FileReadRouter.DESCRIPTION
        assert ".pdf" in desc.lower()
        assert "pages" in desc
        assert "Maximum 20 pages per request" in desc

    def test_description_has_jupyter_line(self):
        desc = FileReadRouter.DESCRIPTION
        assert ".ipynb" in desc

    def test_description_has_screenshot_line(self):
        desc = FileReadRouter.DESCRIPTION
        assert "screenshots" in desc.lower()

    def test_description_has_empty_file_warning(self):
        desc = FileReadRouter.DESCRIPTION
        assert "system reminder" in desc.lower()

    def test_description_has_cat_n_format(self):
        desc = FileReadRouter.DESCRIPTION
        assert "cat -n format" in desc
        assert "starting at 1" in desc

    def test_description_has_2000_lines_default(self):
        desc = FileReadRouter.DESCRIPTION
        assert "2000 lines" in desc

    def test_input_schema_has_pages(self):
        props = FileReadRouter.INPUT_SCHEMA["properties"]
        assert "pages" in props
        assert "PDF" in props["pages"]["description"]


class TestFileEditL1Schema:
    def test_description_requires_read_first(self):
        desc = FileEditRouter.DESCRIPTION
        assert "Read" in desc
        assert "before editing" in desc.lower() or "must use your `Read`" in desc.lower()

    def test_description_has_unique_old_string(self):
        desc = FileEditRouter.DESCRIPTION
        assert "unique" in desc.lower()
        assert "replace_all" in desc

    def test_description_warns_line_number_prefix(self):
        desc = FileEditRouter.DESCRIPTION
        assert "line number prefix" in desc.lower()


# ═══════════════════════════════════════════════════════════════════════
# L2 行为 — image / PDF / Jupyter 边界
# ═══════════════════════════════════════════════════════════════════════


class TestFileReadL2Boundary:
    def test_image_png_rejected(self, tmp_path):
        img = tmp_path / "screenshot.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        r = _new(FileReadRouter)
        ctx = ToolContext()
        with pytest.raises(ToolExecutionError, match="image"):
            r._execute({"file_path": str(img)}, ctx)

    def test_image_jpg_rejected(self, tmp_path):
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xFF\xD8\xFF" + b"\x00" * 50)

        r = _new(FileReadRouter)
        ctx = ToolContext()
        with pytest.raises(ToolExecutionError, match="image"):
            r._execute({"file_path": str(img)}, ctx)

    def test_pdf_rejected(self, tmp_path):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n" + b"\x00" * 50)

        r = _new(FileReadRouter)
        ctx = ToolContext()
        with pytest.raises(ToolExecutionError, match="PDF"):
            r._execute({"file_path": str(pdf)}, ctx)

    def test_pdf_with_pages_still_rejected(self, tmp_path):
        # pages 参数现在不实现真解析, 仍报错 (诚实)
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        r = _new(FileReadRouter)
        ctx = ToolContext()
        with pytest.raises(ToolExecutionError, match="PDF"):
            r._execute({"file_path": str(pdf), "pages": "1-5"}, ctx)

    def test_jupyter_rejected(self, tmp_path):
        nb = tmp_path / "notebook.ipynb"
        nb.write_text('{"cells": []}')

        r = _new(FileReadRouter)
        ctx = ToolContext()
        with pytest.raises(ToolExecutionError, match="NotebookEdit"):
            r._execute({"file_path": str(nb)}, ctx)

    def test_normal_text_still_works(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("def hello():\n    return 1\n")

        r = _new(FileReadRouter)
        ctx = ToolContext()
        out = r._execute({"file_path": str(f)}, ctx)
        # cat -n 格式
        assert "1\t" in out or "     1\t" in out
        assert "def hello" in out


# ═══════════════════════════════════════════════════════════════════════
# L5 协议 — Read→Edit 状态机
# ═══════════════════════════════════════════════════════════════════════


class TestReadEditStateMachine:
    def test_read_adds_to_set(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("hello world\n")

        r = _new(FileReadRouter)
        ctx = ToolContext()
        ctx.read_files = set()  # 模拟 AgentNodeLoop 注入
        r._execute({"file_path": str(f)}, ctx)

        assert str(f.resolve()) in ctx.read_files

    def test_edit_without_read_fails(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("foo bar baz")

        e = _new(FileEditRouter)
        ctx = ToolContext()
        ctx.read_files = set()  # 空 — 没读过
        with pytest.raises(ToolExecutionError, match="Read tool first"):
            e._execute({
                "file_path": str(f),
                "old_string": "foo",
                "new_string": "FOO",
            }, ctx)

    def test_edit_after_read_succeeds(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("foo bar baz")

        ctx = ToolContext()
        ctx.read_files = set()

        # Read first
        r = _new(FileReadRouter)
        r._execute({"file_path": str(f)}, ctx)

        # Then Edit (同 ctx, 共享 read_files)
        e = _new(FileEditRouter)
        out = e._execute({
            "file_path": str(f),
            "old_string": "foo",
            "new_string": "FOO",
        }, ctx)
        assert "Edited" in out

        # 验证内容真改了
        assert f.read_text() == "FOO bar baz"

    def test_edit_without_read_files_attr_skips_check(self, tmp_path):
        """老 ctx 没 read_files 属性 → 不检查 (向下兼容)."""
        f = tmp_path / "file.txt"
        f.write_text("foo bar baz")

        e = _new(FileEditRouter)
        ctx = ToolContext()  # 没 set read_files 属性
        # Edit 应通过 (没 Read→Edit 协议强制)
        out = e._execute({
            "file_path": str(f),
            "old_string": "foo",
            "new_string": "FOO",
        }, ctx)
        assert "Edited" in out

    def test_write_then_edit_works(self, tmp_path):
        """Write 成功后 abs_path 进 read_files, 紧跟 Edit 不破."""
        target = tmp_path / "new_file.txt"

        ctx = ToolContext()
        ctx.read_files = set()
        ctx.allowed_write_paths = (str(target),)  # WriteFile 白名单

        # Write (注: write_file 用 `path` 不是 `file_path`)
        w = _new(WriteFileRouter)
        out = w._execute({
            "path": str(target),
            "content": "hello world",
        }, ctx)
        assert "Wrote" in out
        # 写入后应进 read_files
        assert str(target.resolve()) in ctx.read_files

        # 紧跟 Edit (无需先 Read)
        e = _new(FileEditRouter)
        out2 = e._execute({
            "file_path": str(target),
            "old_string": "hello",
            "new_string": "hi",
        }, ctx)
        assert "Edited" in out2

    def test_edit_then_edit_works(self, tmp_path):
        """已读过的文件可多次连续 Edit (Edit 不必再 Read)."""
        f = tmp_path / "file.txt"
        f.write_text("a b c")

        ctx = ToolContext()
        ctx.read_files = set()

        r = _new(FileReadRouter)
        r._execute({"file_path": str(f)}, ctx)

        e = _new(FileEditRouter)
        e._execute({
            "file_path": str(f), "old_string": "a", "new_string": "AAA",
        }, ctx)
        # 第二次 Edit (无需重读)
        out = e._execute({
            "file_path": str(f), "old_string": "b", "new_string": "BBB",
        }, ctx)
        assert "Edited" in out
        assert f.read_text() == "AAA BBB c"


# ═══════════════════════════════════════════════════════════════════════
# L5 集成 — AgentNodeLoop 默认注入 read_files
# ═══════════════════════════════════════════════════════════════════════


class TestAgentNodeLoopDefaultInjection:
    def test_build_tool_context_has_read_files(self):
        """AgentNodeLoop.build_tool_context 默认含 read_files set."""
        from omnicompany.packages.services._core.agent.loop import AgentNodeLoop

        # 用 _StubLoop 绕开 LLMClient 真实例化 (factory 风险)
        import threading as _threading

        class _StubLoop(AgentNodeLoop):
            ALLOW_NO_BUS = True
            NODE_PROMPT = "stub"
            TOOL_ROUTERS = []

            def __init__(self):
                # 跳过 super().__init__() 复杂实例化, 直接装最小状态
                self._read_files = set()
                # Wave 8 加 abort_event 后 build_tool_context 也读这个 — 必须装
                self._abort_event = _threading.Event()
                # P1.2 加 spawned_traces 后 build_tool_context 也读这个
                self._spawned_traces = []

        loop = _StubLoop()
        ctx_data = loop.build_tool_context(input_data={}, turn=0, trace_id="t-1")
        assert "read_files" in ctx_data
        assert isinstance(ctx_data["read_files"], set)
        # 是同一引用 (跨工具调用共享)
        assert ctx_data["read_files"] is loop._read_files
