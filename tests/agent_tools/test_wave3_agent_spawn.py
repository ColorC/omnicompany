"""Wave 3 P1 — AgentTool 真 spawn 测试 (2026-05-04 立).

验收点 (七层 checklist L2 行为骨架):
  - registry value 必须 callable, 不再占位
  - factory 返真 AgentNodeLoop 实例 (跟主 agent 同基类)
  - AgentRouter._execute 真 asyncio.run(agent.run({...})) 驱动
  - Verdict.output["text"] 提取无误
  - FAIL/PARTIAL Verdict 加 [sub-agent KIND] 前缀透传
  - dry_run 模式仍通 (旧测试不破)

明确**未**覆盖 (留 Wave 5):
  - 真 LLM smoke (跑 qwen-3.6-plus 验证 sub-agent 真能解任务)
  - NODE_PROMPT 跟 cc 原文比对 (现在简版)
  - 跨工具协议 (sub-agent 调 ToolSearch / Skill 等真 dogfood)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.bus.memory import MemoryBus
from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.packages.services._core.agent.loop import AgentNodeLoop
from omnicompany.packages.services._core.agent.routers.single_tool import (
    ToolContext,
    ToolExecutionError,
)
from omnicompany.packages.services._core.agent.routers.agent_spawn import AgentRouter
from omnicompany.packages.services._core.agent.routers.agent_spawn_factory import (
    GeneralPurposeSubAgent,
    ExploreSubAgent,
    PlanSubAgent,
    build_default_subagent_registry,
)


def _new(cls: type) -> Any:
    """绕开 SingleToolRouter __init__ 的 bus 校验, 直接 new 一个."""
    return cls.__new__(cls)


# ═══════════════════════════════════════════════════════════════════════
# build_default_subagent_registry
# ═══════════════════════════════════════════════════════════════════════


class TestBuildDefaultRegistry:
    def test_three_types_present(self):
        bus = MemoryBus()
        reg = build_default_subagent_registry(bus=bus)
        assert set(reg.keys()) == {"general-purpose", "Explore", "Plan"}

    def test_each_value_is_callable(self):
        bus = MemoryBus()
        reg = build_default_subagent_registry(bus=bus)
        for name, factory in reg.items():
            assert callable(factory), f"{name!r} factory not callable"

    def test_factory_produces_agent_node_loop(self):
        bus = MemoryBus()
        reg = build_default_subagent_registry(bus=bus)
        gen = reg["general-purpose"]()
        assert isinstance(gen, AgentNodeLoop)
        assert isinstance(gen, GeneralPurposeSubAgent)

        exp = reg["Explore"]()
        assert isinstance(exp, ExploreSubAgent)

        plan = reg["Plan"]()
        assert isinstance(plan, PlanSubAgent)

    def test_factory_accepts_model_kwarg(self):
        bus = MemoryBus()
        reg = build_default_subagent_registry(bus=bus)
        # 不真启 LLM, 但工厂接受 model 参数 (子 agent __init__ 会传给 LLMCallRouter)
        agent = reg["Explore"](model="some-model-id")
        assert isinstance(agent, AgentNodeLoop)

    def test_explore_subset_is_readonly(self):
        bus = MemoryBus()
        reg = build_default_subagent_registry(bus=bus)
        exp = reg["Explore"]()
        # Explore 工具集 = Read / Glob / Grep, 没有 Edit / Write / Bash
        tool_names = {r.TOOL_NAME for r in exp._tool_dispatch.routers}
        # 必含 Read / Glob / Grep
        assert "Read" in tool_names
        assert "Glob" in tool_names or "glob" in tool_names  # 历史命名
        assert "Grep" in tool_names or "grep" in tool_names
        # 不含修改类
        assert "Edit" not in tool_names and "FileEdit" not in tool_names
        assert "write_file" not in tool_names and "Write" not in tool_names

    def test_no_bus_raises(self):
        with pytest.raises(ValueError, match="bus"):
            build_default_subagent_registry(bus=None)


# ═══════════════════════════════════════════════════════════════════════
# AgentRouter._execute — registry 校验 + 真驱动
# ═══════════════════════════════════════════════════════════════════════


class _StubSubAgent(AgentNodeLoop):
    """测试用桩 — override run() 直接返 Verdict, 不走 LLM.

    验证 AgentRouter 真 asyncio.run + Verdict 提取 wiring.
    """

    NODE_PROMPT: ClassVar[str] = "stub"
    ALLOW_NO_BUS: ClassVar[bool] = True
    DESCRIPTION: ClassVar[str] = "test stub sub-agent"

    _STUB_TEXT: ClassVar[str] = "stub agent final answer"
    _STUB_KIND: ClassVar[VerdictKind] = VerdictKind.PASS
    _STUB_DIAGNOSIS: ClassVar[str] = ""

    def __init__(self):
        # 不走 super().__init__() 避免实例化所有 sub-Router
        self._bus = None

    async def run(self, input_data: Any) -> Verdict:
        return Verdict(
            kind=self._STUB_KIND,
            output={
                "text": self._STUB_TEXT,
                "turn_count": 1,
                "stop_reason": "finish_tool",
                "trace_id": input_data.get("trace_id", ""),
            },
            diagnosis=self._STUB_DIAGNOSIS,
        )


class _StubFailingSubAgent(_StubSubAgent):
    _STUB_TEXT: ClassVar[str] = "partial result"
    _STUB_KIND: ClassVar[VerdictKind] = VerdictKind.PARTIAL
    _STUB_DIAGNOSIS: ClassVar[str] = "Budget exhausted: 50 turns used"


class TestAgentRouterRealSpawn:
    def test_dry_run_unchanged(self, monkeypatch):
        """OMNI_AGENT_DRY_RUN=1 时仍走旧 mock 路径, 不需 registry."""
        monkeypatch.setenv("OMNI_AGENT_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(AgentRouter)
        out = r._execute({
            "description": "test",
            "prompt": "hi",
            "subagent_type": "Explore",
        }, ctx)
        data = json.loads(out)
        assert data["dry_run"] is True
        assert data["subagent_type"] == "Explore"

    def test_no_registry_raises(self):
        ctx = ToolContext()
        r = _new(AgentRouter)
        with pytest.raises(ToolExecutionError, match="subagent_registry"):
            r._execute({"description": "x", "prompt": "y"}, ctx)

    def test_unknown_subagent_type(self):
        ctx = ToolContext()
        ctx.subagent_registry = {"general-purpose": lambda **kw: _StubSubAgent()}
        r = _new(AgentRouter)
        with pytest.raises(ToolExecutionError, match="unknown subagent_type"):
            r._execute({
                "description": "x", "prompt": "y", "subagent_type": "GhostType",
            }, ctx)

    def test_non_callable_factory_rejected(self):
        ctx = ToolContext()
        ctx.subagent_registry = {"general-purpose": "not a callable"}
        r = _new(AgentRouter)
        with pytest.raises(ToolExecutionError, match="not callable"):
            r._execute({"description": "x", "prompt": "y"}, ctx)

    def test_factory_crash_wrapped(self):
        ctx = ToolContext()

        def _bad_factory(model=None):
            raise RuntimeError("factory boom")

        ctx.subagent_registry = {"general-purpose": _bad_factory}
        r = _new(AgentRouter)
        with pytest.raises(ToolExecutionError, match="factory.*crashed"):
            r._execute({"description": "x", "prompt": "y"}, ctx)

    def test_real_spawn_extracts_text(self):
        """核心: factory → AgentNodeLoop → asyncio.run + run() → output.text 提取."""
        ctx = ToolContext()
        ctx.trace_id = "trace-abc"
        ctx.subagent_registry = {"general-purpose": lambda **kw: _StubSubAgent()}
        r = _new(AgentRouter)
        out = r._execute({
            "description": "test spawn",
            "prompt": "do the thing",
            "subagent_type": "general-purpose",
        }, ctx)
        assert out == _StubSubAgent._STUB_TEXT

    def test_real_spawn_partial_verdict_prefixed(self):
        """PARTIAL/FAIL 的 Verdict 加 [sub-agent KIND] 前缀, 主 agent 看得见."""
        ctx = ToolContext()
        ctx.subagent_registry = {"general-purpose": lambda **kw: _StubFailingSubAgent()}
        r = _new(AgentRouter)
        out = r._execute({
            "description": "test partial",
            "prompt": "do the thing",
            "subagent_type": "general-purpose",
        }, ctx)
        # VerdictKind.value 是小写 ("partial" / "fail" / "pass")
        assert "[sub-agent partial]" in out.lower()
        assert "Budget exhausted" in out
        assert _StubFailingSubAgent._STUB_TEXT in out

    def test_required_fields_still_validated(self):
        ctx = ToolContext()
        ctx.subagent_registry = {"general-purpose": lambda **kw: _StubSubAgent()}
        r = _new(AgentRouter)
        with pytest.raises(ToolExecutionError, match="description"):
            r._execute({"prompt": "x"}, ctx)
        with pytest.raises(ToolExecutionError, match="prompt"):
            r._execute({"description": "x"}, ctx)


# ═══════════════════════════════════════════════════════════════════════
# 集成 — 真 build_default_subagent_registry + AgentRouter 调用
# ═══════════════════════════════════════════════════════════════════════


class TestEndToEndDryRun:
    """端到端: 真 registry + AgentRouter, 但用 dry_run 短路 LLM.

    验证 registry 跟 AgentRouter 接口完整对得上 (factory 签名 / 字段名).
    """

    def test_registry_with_router_dry_run(self, monkeypatch):
        monkeypatch.setenv("OMNI_AGENT_DRY_RUN", "1")
        bus = MemoryBus()
        reg = build_default_subagent_registry(bus=bus)
        ctx = ToolContext()
        ctx.subagent_registry = reg
        r = _new(AgentRouter)
        out = r._execute({
            "description": "test",
            "prompt": "search for X",
            "subagent_type": "Explore",
        }, ctx)
        data = json.loads(out)
        assert data["subagent_type"] == "Explore"
        assert data["dry_run"] is True
