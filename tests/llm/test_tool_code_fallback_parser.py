"""跨厂 LLM 工具协议适配 — `<tool_code>` markup fallback parser (2026-05-05).

P1.1 修法: qwen3.6-plus 等流式响应里返 `<tool_code>NAME(args)</tool_code>` 文本块
而非 OpenAI tool_calls 字段. fallback parser 用 ast.parse 安全解, 转 _ToolUseBlock.

单元测试覆盖:
  - 简单 NAME(arg=value) 单块
  - 多块 (一个 LLM 响应里多次 tool_use)
  - 字符串参数含转义 / Windows 路径
  - 数字 / 布尔 / 列表 / dict 字面量参数
  - positional args (qwen 偶尔用)
  - 损坏 markup 不破 (跳过)
  - 注入防御 (eval 不能跑代码)
  - cleaned text 真剥 markup
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.runtime.llm.llm import _parse_tool_code_blocks, _ToolUseBlock


class TestSimpleParsing:
    def test_single_block_kw_args(self):
        text = '<tool_code>glob(pattern="*.py")</tool_code>'
        blocks, cleaned = _parse_tool_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].name == "glob"
        assert blocks[0].input == {"pattern": "*.py"}
        assert cleaned == ""

    def test_no_markup_returns_empty(self):
        text = "Hello, this is just text without markup."
        blocks, cleaned = _parse_tool_code_blocks(text)
        assert blocks == []
        assert cleaned == text

    def test_multi_block(self):
        text = (
            "Let me search and read.\n"
            '<tool_code>glob(pattern="*.py")</tool_code>\n'
            'Then:\n'
            '<tool_code>read_file(path="/tmp/x.py")</tool_code>\n'
        )
        blocks, cleaned = _parse_tool_code_blocks(text)
        assert len(blocks) == 2
        assert blocks[0].name == "glob"
        assert blocks[1].name == "read_file"
        assert blocks[1].input == {"path": "/tmp/x.py"}
        assert "<tool_code>" not in cleaned
        assert "Let me search" in cleaned
        assert "Then:" in cleaned

    def test_windows_path_with_escapes(self):
        # qwen 实测 markup 输出: Windows 路径 backslash 双层转义
        text = (
            '<tool_code>glob(pattern="C:\\\\Users\\\\foo\\\\**\\\\*.py")</tool_code>'
        )
        blocks, cleaned = _parse_tool_code_blocks(text)
        assert len(blocks) == 1
        # ast.literal_eval 还原一层转义: '\\\\' (双反斜杠源码) → '\\' (字符串里单反斜杠)
        # 输出还含 backslash 即 OK
        assert "\\" in blocks[0].input["pattern"]


class TestArgumentTypes:
    def test_int_arg(self):
        text = '<tool_code>read_file(path="x", limit=100)</tool_code>'
        blocks, _ = _parse_tool_code_blocks(text)
        assert blocks[0].input == {"path": "x", "limit": 100}

    def test_bool_arg(self):
        text = '<tool_code>edit(file_path="x", replace_all=True)</tool_code>'
        blocks, _ = _parse_tool_code_blocks(text)
        assert blocks[0].input["replace_all"] is True

    def test_list_arg(self):
        text = '<tool_code>tool(items=[1, 2, 3])</tool_code>'
        blocks, _ = _parse_tool_code_blocks(text)
        assert blocks[0].input == {"items": [1, 2, 3]}

    def test_dict_arg(self):
        text = '<tool_code>tool(config={"k": "v"})</tool_code>'
        blocks, _ = _parse_tool_code_blocks(text)
        assert blocks[0].input == {"config": {"k": "v"}}

    def test_none_arg(self):
        text = '<tool_code>tool(maybe=None)</tool_code>'
        blocks, _ = _parse_tool_code_blocks(text)
        assert blocks[0].input == {"maybe": None}

    def test_positional_args_kept(self):
        # qwen 有时用 positional, 转 arg0 / arg1
        text = '<tool_code>fn("first", 42)</tool_code>'
        blocks, _ = _parse_tool_code_blocks(text)
        assert blocks[0].input == {"arg0": "first", "arg1": 42}

    def test_mixed_positional_and_kw(self):
        text = '<tool_code>fn("first", limit=10)</tool_code>'
        blocks, _ = _parse_tool_code_blocks(text)
        assert blocks[0].input == {"arg0": "first", "limit": 10}


class TestSafetyAndRobustness:
    def test_eval_injection_rejected(self):
        """ast.literal_eval 仅允字面量 — eval / 函数调用作参数会被拒."""
        text = '<tool_code>tool(arg=__import__("os").system("rm -rf /"))</tool_code>'
        blocks, _ = _parse_tool_code_blocks(text)
        # 整个 block 解析失败 → 跳
        assert blocks == []

    def test_method_call_as_func_rejected(self):
        """函数名必须是普通 Name (不允许 obj.method)."""
        text = '<tool_code>obj.method(x=1)</tool_code>'
        blocks, _ = _parse_tool_code_blocks(text)
        assert blocks == []

    def test_invalid_syntax_skipped(self):
        text = '<tool_code>not valid python !!@#$</tool_code>'
        blocks, cleaned = _parse_tool_code_blocks(text)
        assert blocks == []
        # 但 markup 仍被剥 (减少 LLM 自我混淆)
        assert "<tool_code>" not in cleaned

    def test_empty_block_skipped(self):
        text = '<tool_code></tool_code>'
        blocks, _ = _parse_tool_code_blocks(text)
        assert blocks == []

    def test_one_valid_one_invalid(self):
        text = (
            '<tool_code>glob(pattern="*.py")</tool_code>\n'
            '<tool_code>broken!!!</tool_code>'
        )
        blocks, _ = _parse_tool_code_blocks(text)
        # 有效的拿到, 无效的跳 — 不全死
        assert len(blocks) == 1
        assert blocks[0].name == "glob"


class TestMultilineMarkup:
    def test_markup_with_newlines(self):
        # qwen 实测格式: <tool_code>\n  call(args)\n</tool_code>
        text = (
            "<tool_code>\n"
            'glob(pattern="*.py")\n'
            "</tool_code>"
        )
        blocks, _ = _parse_tool_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].name == "glob"


class TestBlockShape:
    def test_block_has_id_name_input_type(self):
        text = '<tool_code>fn(x=1)</tool_code>'
        blocks, _ = _parse_tool_code_blocks(text)
        b = blocks[0]
        assert isinstance(b, _ToolUseBlock)
        assert b.id.startswith("toolcode_")
        assert b.name == "fn"
        assert isinstance(b.input, dict)
        assert b.type == "tool_use"

    def test_multiple_blocks_get_unique_ids(self):
        text = '<tool_code>a()</tool_code><tool_code>b()</tool_code>'
        blocks, _ = _parse_tool_code_blocks(text)
        assert len(blocks) == 2
        assert blocks[0].id != blocks[1].id
