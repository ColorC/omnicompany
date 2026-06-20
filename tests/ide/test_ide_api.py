"""Tests for IDE API — SSE events, REST endpoints, session management.

E2E test: backend publishes events → SSE delivers → REST returns history.
"""

import asyncio
import json
import tempfile
import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from omnicompany.bus.sqlite import SQLiteBus
from omnicompany.protocol.events import FactoryEvent, EventMetadata
from omnicompany.dashboard.controlplane.ide_session import BusAdapter, IDESession, IDESessionManager


# ═══════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    # Move 8 (2026-04-21): SQLiteBus 把任何 data/ 外的 db_path 重导向到 unified
    # data/events.db。直接传 tmp_db 路径会被忽略 → 全部测试共用真仓 data/events.db,
    # trace 互相串台 (count 断言随机失败)。OMNICOMPANY_DB_DIR 是官方测试隔离钩子
    # (core.config.resolve_unified_db_path: "仅作为根目录覆盖（用于测试/隔离）"),
    # 指到 tmp_path 让 unified 路径落进本用例独占的临时目录。
    monkeypatch.setenv("OMNICOMPANY_DB_DIR", str(tmp_path))
    return tmp_path / "test_ide.db"


@pytest_asyncio.fixture
async def bus(tmp_db):
    b = SQLiteBus(tmp_db)
    await b.connect()
    yield b
    await b.close()


@pytest.fixture
def app(bus):
    """Create a test FastAPI app with IDE routes."""
    from omnicompany.dashboard.controlplane.ide import ide_router
    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.include_router(ide_router, prefix="/api/v2")
    test_app.state.ide_bus = bus
    test_app.state.ide_session_manager = IDESessionManager(bus, use_mock=True)
    return test_app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ═══════════════════════════════════════════════════════════
# BusAdapter Tests
# ═══════════════════════════════════════════════════════════


class TestBusAdapter:
    """Test BusAdapter converts emit() → FactoryEvent."""

    @pytest.mark.asyncio
    async def test_emit_creates_factory_event(self, bus):
        adapter = BusAdapter(bus, trace_id="test-trace-001", source="test.agent")

        # Use emit() as AgentNodeLoop would
        adapter.emit("agent.tool.call", {"tool": "bash", "args": {"command": "ls"}})

        # Give the create_task a moment to complete
        await asyncio.sleep(0.1)

        # Verify event was published
        events = await bus.read_trace("test-trace-001")
        assert len(events) == 1
        assert events[0].event_type == "agent.tool.call"
        assert events[0].source == "test.agent"
        assert events[0].payload["tool"] == "bash"

    @pytest.mark.asyncio
    async def test_emit_extracts_metadata(self, bus):
        adapter = BusAdapter(bus, trace_id="test-trace-002")

        adapter.emit("agent_loop.llm_call", {
            "model": "claude-3-opus",
            "prompt_tokens": 500,
            "completion_tokens": 100,
        })
        await asyncio.sleep(0.1)

        events = await bus.read_trace("test-trace-002")
        assert len(events) == 1
        assert events[0].metadata is not None
        assert events[0].metadata.model == "claude-3-opus"
        assert events[0].metadata.prompt_tokens == 500


# ═══════════════════════════════════════════════════════════
# IDESession Tests
# ═══════════════════════════════════════════════════════════


class TestIDESession:
    """Test IDESession lifecycle."""

    @pytest.mark.asyncio
    async def test_submit_publishes_task_intent(self, bus):
        session = IDESession("trace-100", bus)
        event_id = await session.submit("Build a hello world app")

        events = await bus.read_trace("trace-100")
        assert len(events) == 1
        assert events[0].event_type == "task.intent"
        assert events[0].payload["instruction"] == "Build a hello world app"

    @pytest.mark.asyncio
    async def test_mock_agent_run(self, bus):
        session = IDESession("trace-200", bus, use_mock=True)
        await session.submit("Test task")
        await session.run_agent("Test task")

        # Wait for mock agent to complete
        await asyncio.sleep(2.0)

        events = await bus.read_trace("trace-200")
        event_types = [e.event_type for e in events]

        # Should have: task.intent, state.change(running), think, llm.response,
        # tool.call, tool.result, task.finish, state.change(finished)
        assert "task.intent" in event_types
        assert "agent.think" in event_types
        assert "agent.llm.response" in event_types
        assert "agent.tool.call" in event_types
        assert "agent.tool.result" in event_types
        assert "task.finish" in event_types
        assert session.status == "finished"

    @pytest.mark.asyncio
    async def test_cancel(self, bus):
        session = IDESession("trace-300", bus)

        # Run a slow mock agent by patching it (just test cancel mechanism)
        async def slow_agent():
            session.status = "running"
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                session.status = "cancelled"
                raise

        session._task = asyncio.create_task(slow_agent())
        await asyncio.sleep(0.05)

        await session.cancel()
        assert session.status == "cancelled"


# ═══════════════════════════════════════════════════════════
# IDESessionManager Tests
# ═══════════════════════════════════════════════════════════


class TestIDESessionManager:

    @pytest.mark.asyncio
    async def test_get_or_create(self, bus):
        mgr = IDESessionManager(bus)
        s1 = mgr.get_or_create("trace-a")
        s2 = mgr.get_or_create("trace-a")
        assert s1 is s2

    @pytest.mark.asyncio
    async def test_list_sessions(self, bus):
        mgr = IDESessionManager(bus)
        mgr.create("trace-x")
        mgr.create("trace-y")
        sessions = mgr.list_sessions()
        assert len(sessions) == 2


# ═══════════════════════════════════════════════════════════
# REST API Tests
# ═══════════════════════════════════════════════════════════


class TestIDEAPI:

    @pytest.mark.asyncio
    async def test_send_action(self, client):
        resp = await client.post("/api/v2/ide/send", json={
            "instruction": "Hello agent"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "trace_id" in data
        assert "event_id" in data

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, client):
        resp = await client.get("/api/v2/ide/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_sessions_after_send(self, client):
        await client.post("/api/v2/ide/send", json={"instruction": "test"})
        await asyncio.sleep(0.1)

        resp = await client.get("/api/v2/ide/sessions")
        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) == 1

    @pytest.mark.asyncio
    async def test_trace_history(self, client, bus):
        # Publish some events directly
        trace_id = "direct-trace-001"
        for i in range(3):
            await bus.publish(FactoryEvent(
                trace_id=trace_id,
                event_type="agent.think",
                source="test",
                payload={"thought": f"step {i}"},
            ))

        resp = await client.get(f"/api/v2/ide/trace/{trace_id}/history")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_trace_files(self, client, bus):
        trace_id = "file-trace-001"

        # Publish tool call + result
        call = FactoryEvent(
            trace_id=trace_id,
            event_type="agent.tool.call",
            source="test",
            payload={"tool": "str_replace_editor", "args": {
                "command": "str_replace",
                "path": "/src/main.py",
                "old_str": "print('hello')",
                "new_str": "print('world')",
            }},
        )
        await bus.publish(call)
        await bus.publish(FactoryEvent(
            trace_id=trace_id,
            parent_id=call.id,
            event_type="agent.tool.result",
            source="test",
            payload={"result": "ok"},
        ))

        resp = await client.get(f"/api/v2/ide/trace/{trace_id}/files")
        assert resp.status_code == 200
        files = resp.json()
        assert len(files) == 1
        assert files[0]["path"] == "/src/main.py"
        assert files[0]["action"] == "edit"
        assert files[0]["old_text"] == "print('hello')"
        assert files[0]["new_text"] == "print('world')"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, client):
        resp = await client.post("/api/v2/ide/cancel", json={"trace_id": "nope"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_full_e2e_flow(self, client, bus):
        """Full E2E: send message → mock agent runs → history returns all events."""
        # 1. Send message
        resp = await client.post("/api/v2/ide/send", json={
            "instruction": "E2E test instruction"
        })
        assert resp.status_code == 200
        trace_id = resp.json()["trace_id"]

        # 2. Wait for mock agent to complete
        await asyncio.sleep(2.5)

        # 3. Fetch history
        resp = await client.get(f"/api/v2/ide/trace/{trace_id}/history")
        assert resp.status_code == 200
        events = resp.json()

        # Should have multiple events from mock agent
        event_types = [e["event_type"] for e in events]
        assert "task.intent" in event_types
        assert "agent.llm.response" in event_types
        assert "agent.tool.call" in event_types
        assert "agent.tool.result" in event_types
        assert "task.finish" in event_types

        # 4. Verify session status
        resp = await client.get("/api/v2/ide/sessions")
        sessions = resp.json()
        assert any(s["trace_id"] == trace_id for s in sessions)


# ═══════════════════════════════════════════════════════════
# SQLiteBus.tail() Notification Tests
# ═══════════════════════════════════════════════════════════


class TestBusTailNotification:
    """Test that tail() wakes up immediately after publish()."""

    @pytest.mark.asyncio
    async def test_tail_wakes_on_publish(self, bus):
        received = []

        async def tail_reader():
            async for event in bus.tail():
                received.append(event)
                if len(received) >= 2:
                    break

        task = asyncio.create_task(tail_reader())

        # Publish with small delay
        await asyncio.sleep(0.05)
        await bus.publish(FactoryEvent(
            trace_id="tail-test",
            event_type="test.event",
            source="test",
            payload={"n": 1},
        ))

        await asyncio.sleep(0.05)
        await bus.publish(FactoryEvent(
            trace_id="tail-test",
            event_type="test.event",
            source="test",
            payload={"n": 2},
        ))

        # Should complete quickly (not wait for 0.5s poll)
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            task.cancel()
            pytest.fail("tail() did not receive events within 1s")

        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_tail_with_trace_filter(self, bus):
        received = []

        async def tail_reader():
            async for event in bus.tail(trace_id="target"):
                received.append(event)
                if len(received) >= 1:
                    break

        task = asyncio.create_task(tail_reader())
        await asyncio.sleep(0.05)

        # Publish to different trace (should be filtered)
        await bus.publish(FactoryEvent(
            trace_id="other",
            event_type="test.event",
            source="test",
            payload={},
        ))
        await asyncio.sleep(0.1)
        assert len(received) == 0  # Should not receive

        # Publish to target trace
        await bus.publish(FactoryEvent(
            trace_id="target",
            event_type="test.event",
            source="test",
            payload={},
        ))

        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            task.cancel()
            pytest.fail("tail(trace_id=target) did not receive filtered event")

        assert len(received) == 1
        assert received[0].trace_id == "target"
