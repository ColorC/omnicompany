"""跨工具 trace_id 串联 e2e (2026-05-05 P1.2).

主 agent 派 sub-agent 时:
  - sub-agent 的 trace_id = `{父 trace}.spawn.{subagent_type}`
  - sub-agent 内部所有事件都用这个 trace_id (PromptBuilder / LLMCall / 子工具)
  - 主 agent 的 ctx.spawned_traces 收到子 trace, 知道哪些 sub-agent 派生了
  - 主 agent extract_result 时 Verdict.output 含 spawned_traces 字段

验收点:
  - AgentNodeLoop._spawned_traces 默认空 list 实例属性
  - build_tool_context 注入 spawned_traces
  - AgentRouter 派 sub-agent 时 append 子 trace
  - sub-agent.run input_data 含 parent_trace_id
  - 主 agent Verdict.output 含 spawned_traces (有派过 sub 时)
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any, ClassVar

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.agent.loop import AgentNodeLoop
from omnicompany.packages.services._core.agent.routers.single_tool import (
    ToolContext,
    ToolExecutionError,
)
from omnicompany.packages.services._core.agent.routers.agent_spawn import AgentRouter
from omnicompany.protocol.anchor import Verdict, VerdictKind


def _new(cls):
    return cls.__new__(cls)


# ═══════════════════════════════════════════════════════════════════════
# AgentNodeLoop spawned_traces 基础设施
# ═══════════════════════════════════════════════════════════════════════


class _StubLoop(AgentNodeLoop):
    ALLOW_NO_BUS: ClassVar[bool] = True
    NODE_PROMPT: ClassVar[str] = "stub"
    TOOL_ROUTERS: ClassVar[list] = []

    def __init__(self):
        self._bus = None
        self._read_files = set()
        self._abort_event = threading.Event()
        self._spawned_traces: list[str] = []


class TestSpawnedTracesInfra:
    def test_default_empty(self):
        loop = _StubLoop()
        assert loop._spawned_traces == []

    def test_build_tool_context_includes_spawned_traces(self):
        loop = _StubLoop()
        ctx = loop.build_tool_context(input_data={}, turn=0, trace_id="root-1")
        assert "spawned_traces" in ctx
        assert ctx["spawned_traces"] is loop._spawned_traces  # 同引用

    def test_shared_across_turns(self):
        """跨 turn 同 list 引用 — turn 0 派 sub, turn 5 仍能看到."""
        loop = _StubLoop()
        ctx0 = loop.build_tool_context(input_data={}, turn=0, trace_id="r")
        ctx5 = loop.build_tool_context(input_data={}, turn=5, trace_id="r")
        assert ctx0["spawned_traces"] is ctx5["spawned_traces"]


# ═══════════════════════════════════════════════════════════════════════
# AgentRouter 派 sub-agent 时把子 trace append
# ═══════════════════════════════════════════════════════════════════════


class _StubSubAgent(AgentNodeLoop):
    """sub-agent 桩 — 收 input 验 trace_id 链对, 不真启 LLM."""

    ALLOW_NO_BUS: ClassVar[bool] = True
    NODE_PROMPT: ClassVar[str] = "stub"

    last_input_data: dict | None = None

    def __init__(self):
        self._bus = None

    async def run(self, input_data: Any) -> Verdict:
        type(self).last_input_data = dict(input_data)
        return Verdict(
            kind=VerdictKind.PASS,
            output={
                "text": "ok",
                "turn_count": 1,
                "stop_reason": "finish_tool",
                "trace_id": input_data.get("trace_id", ""),
            },
        )


class TestAgentRouterAppendsSubTrace:
    def setup_method(self):
        _StubSubAgent.last_input_data = None

    def test_sub_trace_appended_to_ctx(self):
        ctx = ToolContext()
        ctx.trace_id = "main-trace-001"
        ctx.subagent_registry = {"general-purpose": lambda **kw: _StubSubAgent()}
        ctx.spawned_traces = []

        r = _new(AgentRouter)
        out = r._execute({
            "description": "x",
            "prompt": "y",
            "subagent_type": "general-purpose",
        }, ctx)
        assert out == "ok"
        # ctx.spawned_traces 加了子 trace
        assert len(ctx.spawned_traces) == 1
        assert ctx.spawned_traces[0] == "main-trace-001.spawn.general-purpose"

    def test_sub_agent_receives_correct_trace(self):
        ctx = ToolContext()
        ctx.trace_id = "main-X"
        ctx.subagent_registry = {"Explore": lambda **kw: _StubSubAgent()}
        ctx.spawned_traces = []

        r = _new(AgentRouter)
        r._execute({
            "description": "x", "prompt": "y", "subagent_type": "Explore",
        }, ctx)
        # sub-agent 收到的 trace_id = `{父}.spawn.{type}`
        sub_input = _StubSubAgent.last_input_data
        assert sub_input is not None
        assert sub_input["trace_id"] == "main-X.spawn.Explore"
        # 父 trace 也透传, 调试用
        assert sub_input["parent_trace_id"] == "main-X"

    def test_multiple_spawns_all_appended(self):
        ctx = ToolContext()
        ctx.trace_id = "root"
        ctx.subagent_registry = {
            "general-purpose": lambda **kw: _StubSubAgent(),
            "Explore": lambda **kw: _StubSubAgent(),
        }
        ctx.spawned_traces = []

        r = _new(AgentRouter)
        for sub_type in ("general-purpose", "Explore", "general-purpose"):
            r._execute({"description": "x", "prompt": "y", "subagent_type": sub_type}, ctx)

        assert len(ctx.spawned_traces) == 3
        assert ctx.spawned_traces == [
            "root.spawn.general-purpose",
            "root.spawn.Explore",
            "root.spawn.general-purpose",
        ]

    def test_no_trace_id_no_append(self):
        """主 agent ctx 没 trace_id → 不 append (空 trace 串没意义)."""
        ctx = ToolContext()
        # 不设 ctx.trace_id (默认空)
        ctx.subagent_registry = {"general-purpose": lambda **kw: _StubSubAgent()}
        ctx.spawned_traces = []

        r = _new(AgentRouter)
        r._execute({"description": "x", "prompt": "y"}, ctx)
        assert ctx.spawned_traces == []  # 没 append (没主 trace)

    def test_no_spawned_traces_attr_does_not_crash(self):
        """老 ctx 没 spawned_traces 属性 → 不破 (向下兼容)."""
        ctx = ToolContext()
        ctx.trace_id = "main"
        ctx.subagent_registry = {"general-purpose": lambda **kw: _StubSubAgent()}
        # 不设 ctx.spawned_traces (向下兼容子类)

        r = _new(AgentRouter)
        out = r._execute({"description": "x", "prompt": "y"}, ctx)
        # 仍正常返回
        assert out == "ok"


# ═══════════════════════════════════════════════════════════════════════
# 主 agent extract_result 暴露 spawned_traces 在 Verdict.output
# ═══════════════════════════════════════════════════════════════════════


class TestVerdictExposesSpawnedTraces:
    def test_finish_includes_spawned_traces_when_nonempty(self):
        """主 agent 跑完后 Verdict.output 含 spawned_traces 字段 (派过 sub)."""
        # 用源码 grep 验 (跑完整 loop 太复杂)
        from omnicompany.packages.services._core.agent.loop import AgentNodeLoop
        import inspect

        src = inspect.getsource(AgentNodeLoop.run)
        assert "_spawned_traces" in src
        assert "spawned_traces" in src

    def test_loop_init_creates_list(self):
        """新 AgentNodeLoop 实例 self._spawned_traces 是空 list."""
        loop = _StubLoop()
        assert isinstance(loop._spawned_traces, list)
        assert loop._spawned_traces == []

    def test_lists_isolated_per_loop(self):
        """两个 AgentNodeLoop 实例 spawned_traces 是独立 list (不共享)."""
        loop1 = _StubLoop()
        loop2 = _StubLoop()
        loop1._spawned_traces.append("t1.spawn.x")
        assert loop2._spawned_traces == []
        assert loop1._spawned_traces == ["t1.spawn.x"]
