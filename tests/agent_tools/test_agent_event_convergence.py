from __future__ import annotations

import json
import sqlite3
import asyncio
from pathlib import Path

import pytest

from omnicompany.bus.memory import MemoryBus
from omnicompany.dashboard.ccdaemon.providers.omni_agent import OmniAgentProvider
from omnicompany.packages.services._core.agent.event_bridge import publish_agent_event_sync
from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.tracing.intent_tracer import IntentTracer


def test_agent_event_bridge_sync_writes_factory_event(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNICOMPANY_DB_DIR", str(tmp_path / "db"))

    published = publish_agent_event_sync(
        trace_id="trace.bridge",
        event_type="agent.provider.session_created",
        source="agent.provider.test",
        payload={"provider": "test"},
        tags=["agent_event_bridge"],
    )

    assert published is not None
    conn = sqlite3.connect(str(published.db_path))
    try:
        row = conn.execute(
            "SELECT event_type, source, tags, data FROM events WHERE trace_id=?",
            ("trace.bridge",),
        ).fetchone()
    finally:
        conn.close()

    assert row[0] == "agent.provider.session_created"
    assert row[1] == "agent.provider.test"
    assert json.loads(row[2]) == ["agent_event_bridge"]
    assert json.loads(row[3])["payload"] == {"provider": "test"}


@pytest.mark.asyncio
async def test_intent_tracer_bridges_step_result_and_route_events(tmp_path: Path) -> None:
    bus = MemoryBus()
    tracer = IntentTracer(
        db_path=tmp_path / "intent_traces.db",
        trace_id="trace.intent",
        origin="unit",
        event_bus=bus,
    )

    _, step = tracer.record_step(
        "bash",
        {
            "input_types": ["user_request"],
            "output_types": ["shell_output"],
            "action_class": "execute",
            "desc": "Run a command",
        },
        {"command": "pwd"},
    )
    tracer.record_tool_result(step, "ok", True)
    tracer.record_route_decision(step, "node.shell", "MERGE", 0.8)
    await _drain_event_tasks()

    events = await bus.read_trace("trace.intent")
    assert [event.event_type for event in events] == [
        "intent.step",
        "intent.tool_result",
        "intent.route_decision",
    ]
    assert events[0].payload["node"] == "bash"
    assert events[1].payload["exit_ok"] is True
    assert events[2].payload["route_node_id"] == "node.shell"


@pytest.mark.asyncio
async def test_omni_agent_provider_bridges_hooks_to_eventbus() -> None:
    bus = MemoryBus()
    provider = OmniAgentProvider(
        {"agent_class": _FakeHookAgent, "agent_bus": bus, "model": "unit-model"}
    )

    await provider.connect()
    await provider.send_prompt("hello")

    messages = []
    async for message in provider.consume_messages():
        messages.append(message)
        if message["kind"] == "complete":
            break
    await provider.disconnect()

    trace_id = messages[0]["sessionId"]
    events = await bus.read_trace(trace_id)
    assert [event.event_type for event in events] == [
        "agent.provider.session_created",
        "agent.provider.tool_call",
        "agent.provider.tool_result",
        "agent.provider.complete",
    ]
    assert events[1].payload["tool"] == "read_file"
    assert events[2].payload["result"] == "file text"
    assert events[3].payload["exit_code"] == 0


class _FakeHookAgent:
    def __init__(self, *, bus, model=None) -> None:
        self.bus = bus
        self.model = model

    async def on_tool_dispatch_start(self, **kwargs) -> None:
        return None

    async def on_tool_dispatch_end(self, **kwargs) -> None:
        return None

    async def on_turn_end_async(self, **kwargs) -> None:
        return None

    async def run(self, input_data):
        trace_id = input_data["trace_id"]
        await self.on_tool_dispatch_start(
            tool_name="read_file",
            tool_args={"path": "README.md"},
            tool_use_id="tool-1",
            turn=0,
            trace_id=trace_id,
        )
        await self.on_tool_dispatch_end(
            tool_name="read_file",
            tool_use_id="tool-1",
            result="file text",
            is_error=False,
            turn=0,
            trace_id=trace_id,
        )
        await self.on_turn_end_async(
            turn=0,
            messages=[{"role": "assistant", "content": "done"}],
            trace_id=trace_id,
        )
        return Verdict(kind=VerdictKind.PASS, output={"final_text": ""})

    def abort(self) -> None:
        return None


async def _drain_event_tasks() -> None:
    await asyncio.sleep(0)
