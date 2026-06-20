# [OMNI] origin=claude-code domain=tests/services/agent ts=2026-04-18
"""Toy 用例验证：packages/services/agent 的 AgentNodeLoop 全链路 bus 事件齐全。

对应 plan.md §7 阶段 A 验收标准：
"新 Router 骨架能跑通一个 toy 用例（一个简单 agent 走完 1 turn LLM call + 1 次 tool call）"

并对齐 §10.5.1 E2：
"events.db 查 trace_id 能找齐 10 类事件"

LLM 用 monkeypatch 替换成 stub（不调真实 API，省钱快）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from omnicompany.bus.memory import MemoryBus
from omnicompany.packages.services.agent import AgentNodeLoop, ListDirRouter
from omnicompany.runtime.agent.agent_loop_config import (
    LoopConfig, CompactConfig, RetryConfig,
)


# ═══════════════════════════════════════════════════════════════════
# Stub LLM response objects（对齐 Anthropic Response shape）
# ═══════════════════════════════════════════════════════════════════

@dataclass
class _StubTextBlock:
    type: str
    text: str


@dataclass
class _StubToolUseBlock:
    type: str
    id: str
    name: str
    input: dict


@dataclass
class _StubUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _StubResponse:
    content: list
    stop_reason: str = "end_turn"
    model: str = "stub-model"
    usage: _StubUsage = None


def _make_turn_0_resp() -> _StubResponse:
    """Turn 0: LLM 决定调 list_dir 工具。"""
    return _StubResponse(
        content=[
            _StubTextBlock(type="text", text="I'll list the directory first."),
            _StubToolUseBlock(
                type="tool_use", id="tool_0", name="list_dir",
                input={"path": "."},
            ),
        ],
        stop_reason="tool_use",
        usage=_StubUsage(input_tokens=100, output_tokens=20),
    )


def _make_turn_1_resp() -> _StubResponse:
    """Turn 1: LLM 看到工具结果后调 finish。"""
    return _StubResponse(
        content=[
            _StubTextBlock(type="text", text="Done. Here is a summary."),
            _StubToolUseBlock(
                type="tool_use", id="tool_1", name="finish",
                input={"result": "Toy run complete. 1 tool call executed."},
            ),
        ],
        stop_reason="tool_use",
        usage=_StubUsage(input_tokens=120, output_tokens=30),
    )


class _StubLLM:
    """最小 LLMClient stub — 按 turn 数返回不同 response。"""

    def __init__(self, model: str = "stub-model", tools: list = None, **kwargs):
        self.model = model
        self.tools = tools or []
        self.call_count = 0

    def call(self, messages, system="", caller="", **kwargs):
        self.call_count += 1
        if self.call_count == 1:
            return _make_turn_0_resp()
        return _make_turn_1_resp()


# ═══════════════════════════════════════════════════════════════════
# Toy AgentNodeLoop 子类
# ═══════════════════════════════════════════════════════════════════

class _ToyLoop(AgentNodeLoop):
    NODE_PROMPT = "You are a toy agent. Explore the filesystem and finish."
    TOOL_ROUTERS = [ListDirRouter]
    LOOP_CONFIG = LoopConfig(
        max_turns=5,
        context_window=50_000,
        retry=RetryConfig(max_retries=1),
        compact=CompactConfig(aging_threshold=10, max_messages=50),
    )


# ═══════════════════════════════════════════════════════════════════
# 主测试
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_agent_loop_toy_run(monkeypatch):
    """验证全链路 bus 事件齐全 + Verdict=PASS。"""
    # 用 stub LLM 替换真实 LLMClient
    from omnicompany.packages.services._core.agent.routers import llm_call as lc_mod
    monkeypatch.setattr(lc_mod, "LLMClient", _StubLLM)

    bus = MemoryBus()
    loop = _ToyLoop(model="stub-model", bus=bus)

    verdict = await loop.run({
        "task": "list the current dir and finish",
        "trace_id": "toy_trace_42",
    })

    # 1. Verdict 级别（VerdictKind.PASS.value == "pass"）
    assert verdict.kind.value == "pass", f"Expected pass, got {verdict.kind.value}: {verdict.diagnosis}"

    # 2. bus 事件齐全（trace_id 过滤）
    events = [e for e in bus._events if e.trace_id == "toy_trace_42"]
    event_types = {e.event_type for e in events}

    required = {
        # Agent-level signals
        "agent.loop.start",
        "agent.turn.start",
        "agent.turn.end",
        "agent.loop.finish",
        # Router input/output（每个 Router 至少一对）
        "router.prompt_builder.input",
        "router.prompt_builder.output",
        "router.context_compact.input",
        "router.context_compact.output",
        "router.llm_call.input",
        "router.llm_call.output",
        "router.tool_dispatch.input",
        "router.tool_dispatch.output",
        "router.tool_list_dir.input",
        "router.tool_list_dir.output",
        "router.extract_result.input",
        "router.extract_result.output",
    }
    missing = required - event_types
    assert not missing, f"Missing event types: {sorted(missing)}"

    # 3. 关键约束：每个 Router 都至少发了 input + output 配对
    for rn in ("prompt_builder", "context_compact", "llm_call",
               "tool_dispatch", "tool_list_dir", "extract_result"):
        inputs = [e for e in events if e.event_type == f"router.{rn}.input"]
        outputs = [e for e in events if e.event_type == f"router.{rn}.output"]
        assert inputs, f"no input event for {rn}"
        assert outputs, f"no output event for {rn}"

    # 4. trace_id 贯穿
    for e in events:
        assert e.trace_id == "toy_trace_42"

    # 5. 工具调用真的发生了（list_dir 被 dispatched）
    tool_outs = [
        e for e in events
        if e.event_type == "router.tool_list_dir.output"
    ]
    assert tool_outs, "list_dir tool Router output missing"
    assert tool_outs[0].payload["data"]["tool_name"] == "list_dir"

    # 6. final verdict 包含 trace_id
    assert "trace_id" in verdict.output or verdict.output.get("verdict_kind") == "pass"

    print(f"\n[TOY RUN] verdict={verdict.kind.value}, events={len(events)}, "
          f"types={len(event_types)}, trace_id=toy_trace_42")
    print(f"[TOY RUN] event types found: {sorted(event_types)}")


@pytest.mark.asyncio
async def test_agent_loop_rejects_no_bus():
    """bus=None 必须 RuntimeError。"""
    with pytest.raises(RuntimeError, match="EventBus"):
        _ToyLoop(model="stub-model", bus=None)


if __name__ == "__main__":
    # 允许直接跑：python tests/test_services_agent_loop_toy.py
    async def _main():
        class _M:
            def setattr(self, obj, attr, val):
                setattr(obj, attr, val)
        m = _M()
        await test_agent_loop_toy_run(m)
    asyncio.run(_main())
