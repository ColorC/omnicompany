"""default vs deferred 工具集 + ToolSearch 真实现测试 (2026-05-04 立, 第二波 P0).

哲学: canary 系统健康. 任一 FAIL 表示 default/deferred 机制失效, agent 拿到的工具集
不再跟 claude code 实际行为一致.

覆盖:
  - DEFAULT_TOOL_ROUTERS 数量 + 必含的 10 个核心
  - DEFERRED_TOOL_ROUTERS 数量 + 必含的关键 deferred (NotebookEdit / TodoWrite / WebSearch / MCP*)
  - default + deferred 互斥 (无重复)
  - get_default_tool_specs / get_deferred_tool_names_with_descriptions / lookup_tool_schemas helper
  - ToolSearch 真实现:
    * select:Name 精确拉
    * select:Name1,Name2 多个
    * keyword 搜索
    * +required 必含词
    * 不存在的工具
    * default 工具不在 deferred 列表 (search 不到 — 它本来就在系统里)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.agent.routers import (
    DEFAULT_TOOL_ROUTERS,
    DEFAULT_TOOLS_BY_NAME,
    DEFERRED_TOOL_ROUTERS,
    DEFERRED_TOOLS_BY_NAME,
    ALL_TOOL_ROUTERS,
    TOOLS_BY_NAME,
    SingleToolRouter,
    ToolContext,
    ToolExecutionError,
    get_default_tool_specs,
    get_deferred_tool_names_with_descriptions,
    lookup_tool_schemas,
)
from omnicompany.packages.services._core.agent.routers.skill_tools import (
    ToolSearchRouter,
)


def _new(cls):
    return cls.__new__(cls)


# ─── 集合划分 ────────────────────────────────────────────────────


class TestDefaultVsDeferredSplit:
    """canary: default 和 deferred 集合划分跟 claude code 对齐."""

    def test_default_count_in_range(self):
        """claude code 默认载入约 11 个 (含 ScheduleWakeup 不引), omnicompany 应 9-12 个."""
        assert 9 <= len(DEFAULT_TOOL_ROUTERS) <= 12, (
            f"DEFAULT_TOOL_ROUTERS 数量异常: {len(DEFAULT_TOOL_ROUTERS)}, "
            f"应 9-12 个 (跟 claude code 顶部 functions 对齐)"
        )

    def test_default_contains_core_io(self):
        """核心 IO 必在 default: Read / Edit / Glob / Grep."""
        for name in ("Read", "Edit", "Glob", "Grep"):
            assert name in DEFAULT_TOOLS_BY_NAME, f"{name} 必须在 default 集"

    def test_default_contains_shell_and_agent(self):
        """Shell + Agent 编排核心必在 default."""
        for name in ("PowerShell", "Agent", "Skill", "ToolSearch"):
            assert name in DEFAULT_TOOLS_BY_NAME, f"{name} 必须在 default 集"

    def test_deferred_contains_classic_deferred(self):
        """claude code 历史 deferred 列表里的工具必须在 omnicompany deferred.

        注: 'web_fetch' 是 omnicompany 历史命名 (snake_case), claude code 是 'WebFetch'.
        这是 L1 schema 待对齐项 (后续会话改名 + backward compat alias).
        """
        for name in (
            "NotebookEdit", "TodoWrite", "web_fetch", "WebSearch",
            "AskUserQuestion", "EnterPlanMode", "ExitPlanMode",
            "EnterWorktree", "ExitWorktree", "Monitor", "PushNotification",
            "RemoteTrigger", "ScheduleCron", "MCP", "McpAuth",
        ):
            assert name in DEFERRED_TOOLS_BY_NAME, f"{name} 必须在 deferred 集"

    def test_default_and_deferred_disjoint(self):
        """default 和 deferred 不能重复."""
        d_names = set(DEFAULT_TOOLS_BY_NAME)
        f_names = set(DEFERRED_TOOLS_BY_NAME)
        overlap = d_names & f_names
        assert overlap == set(), f"default 和 deferred 重叠: {overlap}"

    def test_all_equals_default_plus_deferred(self):
        """ALL = DEFAULT + DEFERRED, 没漏没多."""
        assert set(TOOLS_BY_NAME) == set(DEFAULT_TOOLS_BY_NAME) | set(DEFERRED_TOOLS_BY_NAME)
        assert len(ALL_TOOL_ROUTERS) == len(DEFAULT_TOOL_ROUTERS) + len(DEFERRED_TOOL_ROUTERS)


# ─── helper 函数 ────────────────────────────────────────────────


class TestHelperFunctions:
    def test_get_default_tool_specs_shape(self):
        """返 list of {name, description, input_schema}."""
        specs = get_default_tool_specs()
        assert len(specs) == len(DEFAULT_TOOL_ROUTERS)
        for s in specs:
            assert "name" in s and "description" in s and "input_schema" in s
            assert s["name"]
            assert s["description"]

    def test_deferred_names_with_descriptions(self):
        """返 list of {name, description}, 每个 description 一句话."""
        items = get_deferred_tool_names_with_descriptions()
        assert len(items) == len(DEFERRED_TOOL_ROUTERS)
        for it in items:
            assert "name" in it and "description" in it
            assert "input_schema" not in it  # deferred 不返 schema
            assert len(it["description"]) <= 200

    def test_lookup_tool_schemas_by_name(self):
        """按名字精确拉 schema."""
        out = lookup_tool_schemas(["Read", "NotebookEdit", "Agent"])
        assert len(out) == 3
        names = [s["name"] for s in out]
        assert names == ["Read", "NotebookEdit", "Agent"]
        for s in out:
            assert "input_schema" in s
            assert "properties" in s["input_schema"]

    def test_lookup_unknown_skipped(self):
        """不存在的名字静默跳过."""
        out = lookup_tool_schemas(["Read", "GhostTool", "Edit"])
        names = [s["name"] for s in out]
        assert "GhostTool" not in names
        assert "Read" in names and "Edit" in names


# ─── ToolSearchRouter 真实现 ────────────────────────────────────


class TestToolSearchSelectMode:
    """select:Name 精确选取模式."""

    def test_select_single(self):
        ctx = ToolContext()
        r = _new(ToolSearchRouter)
        out = r._execute({"query": "select:NotebookEdit"}, ctx)
        assert "<functions>" in out and "</functions>" in out
        assert "NotebookEdit" in out
        # 应有完整 schema (parameters 字段)
        assert '"parameters"' in out

    def test_select_multiple(self):
        ctx = ToolContext()
        r = _new(ToolSearchRouter)
        out = r._execute({"query": "select:NotebookEdit,WebSearch,TodoWrite"}, ctx)
        assert "NotebookEdit" in out
        assert "WebSearch" in out
        assert "TodoWrite" in out

    def test_select_unknown(self):
        """不存在的名字 → 0 命中."""
        ctx = ToolContext()
        r = _new(ToolSearchRouter)
        out = r._execute({"query": "select:GhostTool"}, ctx)
        assert "No deferred tools matched" in out

    def test_select_default_tool_not_found(self):
        """default 工具 (Read) 不在 deferred 集 — 通过 select 找不到 (这是预期行为).

        理由: default 工具的 schema 已经在 LLM system tools 里, 不需要再 fetch.
        """
        ctx = ToolContext()
        r = _new(ToolSearchRouter)
        out = r._execute({"query": "select:Read"}, ctx)
        assert "No deferred tools matched" in out


class TestToolSearchKeywordMode:
    """keyword 搜索模式."""

    def test_keyword_match(self):
        ctx = ToolContext()
        r = _new(ToolSearchRouter)
        out = r._execute({"query": "notebook"}, ctx)
        assert "NotebookEdit" in out

    def test_required_keyword(self):
        """+web → 名字或描述必含 web."""
        ctx = ToolContext()
        r = _new(ToolSearchRouter)
        out = r._execute({"query": "+web"}, ctx)
        # WebSearch / WebBrowser / WebFetch 都应在
        assert "WebSearch" in out or "WebBrowser" in out or "WebFetch" in out

    def test_max_results_limits(self):
        ctx = ToolContext()
        r = _new(ToolSearchRouter)
        out = r._execute({"query": "+a", "max_results": 2}, ctx)
        # 结果数 ≤ 2
        n = out.count("<function>")
        assert n <= 2


class TestToolSearchValidation:
    def test_query_required(self):
        ctx = ToolContext()
        r = _new(ToolSearchRouter)
        with pytest.raises(ToolExecutionError, match="query"):
            r._execute({}, ctx)

    def test_negative_max_results(self):
        ctx = ToolContext()
        r = _new(ToolSearchRouter)
        with pytest.raises(ToolExecutionError, match="max_results"):
            r._execute({"query": "x", "max_results": 0}, ctx)


class TestToolSearchCustomDeferredInjection:
    """Worker 可注入自己的 deferred 子集 (覆盖全局 fallback)."""

    def test_ctx_deferred_tools_dict(self):
        from omnicompany.packages.services._core.agent.routers.notebook_edit import (
            NotebookEditRouter,
        )
        ctx = ToolContext()
        ctx.deferred_tools = {"NotebookEdit": NotebookEditRouter}  # type: ignore[attr-defined]
        r = _new(ToolSearchRouter)
        out = r._execute({"query": "select:NotebookEdit"}, ctx)
        assert "NotebookEdit" in out
        # WebSearch 在全局 deferred 但不在 ctx 注入 → 找不到
        out2 = r._execute({"query": "select:WebSearch"}, ctx)
        assert "No deferred tools" in out2

    def test_ctx_deferred_tools_list(self):
        from omnicompany.packages.services._core.agent.routers.notebook_edit import (
            NotebookEditRouter,
        )
        from omnicompany.packages.services._core.agent.routers.web_search import (
            WebSearchRouter,
        )
        ctx = ToolContext()
        ctx.deferred_tools = [NotebookEditRouter, WebSearchRouter]  # type: ignore[attr-defined]
        r = _new(ToolSearchRouter)
        out = r._execute({"query": "select:NotebookEdit,WebSearch"}, ctx)
        assert "NotebookEdit" in out and "WebSearch" in out


# ─── 集成: ToolSearch 仍是 default 集成员 ────────────────────────


class TestToolSearchSelfInDefault:
    """canary: ToolSearchRouter 必须自己在 default 集 (LLM 一上来就要能调它)."""

    def test_tool_search_in_default(self):
        assert "ToolSearch" in DEFAULT_TOOLS_BY_NAME, (
            "ToolSearch 必须在 default 集 — 否则 LLM 没法 fetch deferred schema"
        )
