"""主 agent 集成测试 — Wave 3 / Wave 5+7 真上线验证 (2026-05-05 立).

之前的测试 (Wave 3 / 5 / 5b) 都是单元测试 (用 _StubLoop / 直接 _execute), 没在真主
agent 上验证. 这次验证 NativeIdeAgent.build_tool_context 真注入了:
  - read_files set (Wave 5+7 Read→Edit 状态机能起作用)
  - subagent_registry dict (Wave 3 真 spawn 能起作用)

不验:
  - 真 LLM 调用 (留 Wave 5 收尾)
  - dashboard 真启 (sqlite + assistant_db 等基础设施)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.bus.memory import MemoryBus


def _build_native_agent(tmp_path) -> Any:
    """构造一个最小 NativeIdeAgent 实例 (无外部依赖)."""
    from omnicompany.dashboard.native_agent import NativeIdeAgent

    bus = MemoryBus()
    agent = NativeIdeAgent(cwd=str(tmp_path), bus=bus)
    return agent, bus


# ═══════════════════════════════════════════════════════════════════════
# build_tool_context 注入验证
# ═══════════════════════════════════════════════════════════════════════


class TestNativeIdeAgentToolCtxInjection:
    def test_read_files_injected(self, tmp_path):
        """Wave 5+7 真上线: build_tool_context 必含 read_files set."""
        agent, _ = _build_native_agent(tmp_path)
        ctx = agent.build_tool_context(input_data={}, turn=0, trace_id="t-1")
        assert "read_files" in ctx
        assert isinstance(ctx["read_files"], set)
        # 跨工具调用同一引用
        assert ctx["read_files"] is agent._read_files

    def test_subagent_registry_injected(self, tmp_path):
        """Wave 3 真上线: build_tool_context 必含 subagent_registry dict."""
        agent, _ = _build_native_agent(tmp_path)
        ctx = agent.build_tool_context(input_data={}, turn=0, trace_id="t-1")
        assert "subagent_registry" in ctx
        registry = ctx["subagent_registry"]
        assert isinstance(registry, dict)
        # 默认 registry 含 3 种 sub-agent
        assert "general-purpose" in registry
        assert "Explore" in registry
        assert "Plan" in registry

    def test_subagent_factories_callable(self, tmp_path):
        """每个 factory 必 callable, 否则 AgentRouter 调时拒绝."""
        agent, _ = _build_native_agent(tmp_path)
        ctx = agent.build_tool_context(input_data={}, turn=0, trace_id="t-1")
        registry = ctx["subagent_registry"]
        for name, factory in registry.items():
            assert callable(factory), f"{name!r} factory not callable"

    def test_existing_fields_preserved(self, tmp_path):
        """修加 read_files / subagent_registry 不破原有字段."""
        agent, _ = _build_native_agent(tmp_path)
        ctx = agent.build_tool_context(input_data={}, turn=0, trace_id="t-1")
        # 原有字段都还在
        assert ctx["cwd"] == str(tmp_path)
        assert ctx["project_root"] == str(tmp_path)
        assert ctx["origin"] == "ai-ide"
        assert ctx["agent_name"] == "NativeIdeAgent"
        assert ctx["domain"] == "dashboard"
        assert ctx["allowed_bash_roots"] == (str(tmp_path),)
        assert ctx["allowed_write_roots"] == (str(tmp_path),)

    def test_subagent_registry_cached_across_calls(self, tmp_path):
        """build_tool_context 多次调用时 subagent_registry 应是同一引用 (减少 factory 重建)."""
        agent, _ = _build_native_agent(tmp_path)
        ctx1 = agent.build_tool_context(input_data={}, turn=0, trace_id="t-1")
        ctx2 = agent.build_tool_context(input_data={}, turn=1, trace_id="t-2")
        assert ctx1["subagent_registry"] is ctx2["subagent_registry"]

    def test_read_files_shared_across_turns(self, tmp_path):
        """read_files set 跨多 turn 同引用, FileRead 第 turn 0 加进去, FileEdit
        第 turn 5 还能看到."""
        agent, _ = _build_native_agent(tmp_path)
        ctx0 = agent.build_tool_context(input_data={}, turn=0, trace_id="t-1")
        ctx5 = agent.build_tool_context(input_data={}, turn=5, trace_id="t-1")
        assert ctx0["read_files"] is ctx5["read_files"]

        # 模拟 turn 0 FileRead 加 abs_path
        ctx0["read_files"].add("/some/path/file.py")
        # turn 5 FileEdit 看 ctx 应有该 abs_path
        assert "/some/path/file.py" in ctx5["read_files"]


# ═══════════════════════════════════════════════════════════════════════
# 集成: AgentRouter 真用主 agent 注入的 registry
# ═══════════════════════════════════════════════════════════════════════


class TestAgentRouterUsesMainAgentRegistry:
    """主 agent 的 ctx 通过 SingleToolRouter._build_ctx 喂给 AgentRouter._execute."""

    def test_agent_router_finds_subagent(self, tmp_path, monkeypatch):
        """模拟 AgentRouter 通过 ctx 调到主 agent 注册的 factory.

        干跑模式 (OMNI_AGENT_DRY_RUN=1) — 不真起 LLM, 验 wiring.
        """
        from omnicompany.packages.services._core.agent.routers.single_tool import ToolContext
        from omnicompany.packages.services._core.agent.routers.agent_spawn import AgentRouter

        agent, _ = _build_native_agent(tmp_path)
        ctx_data = agent.build_tool_context(input_data={}, turn=0, trace_id="t-1")

        # 把 dict 转成 ToolContext 模拟 SingleToolRouter._build_ctx 的 setattr
        ctx = ToolContext()
        for k, v in ctx_data.items():
            setattr(ctx, k, v)

        # 验 ctx.subagent_registry 真有值 (回去 AgentRouter 不会再报 "no subagent_registry")
        assert getattr(ctx, "subagent_registry", None) is not None

        # 干跑 AgentRouter._execute, 不真 spawn
        monkeypatch.setenv("OMNI_AGENT_DRY_RUN", "1")
        r = AgentRouter.__new__(AgentRouter)
        out = r._execute({
            "description": "test integration",
            "prompt": "hi sub-agent",
            "subagent_type": "Explore",
        }, ctx)
        # dry_run 输出 JSON 含 subagent_type
        assert "Explore" in out
        assert "dry_run" in out
