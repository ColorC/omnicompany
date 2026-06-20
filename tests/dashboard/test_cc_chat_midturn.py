from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from omnicompany.dashboard.ccdaemon.chat import CcChatSession, CcChatSessionManager


class RecordingClaudeClient:
    def __init__(self) -> None:
        self.query_calls: list[Any] = []
        self.written_messages: list[dict[str, Any]] = []
        self.receive_response_calls = 0
        self.interrupt_calls = 0
        self.release_receive = asyncio.Event()

    async def query(self, prompt: Any, session_id: str = "default") -> None:
        self.query_calls.append({"prompt": prompt, "session_id": session_id})
        if not isinstance(prompt, str):
            async for msg in prompt:
                self.written_messages.append(msg)

    async def receive_response(self):
        self.receive_response_calls += 1
        await self.release_receive.wait()
        if False:
            yield None

    async def interrupt(self) -> None:
        self.interrupt_calls += 1


@pytest.mark.asyncio
async def test_running_claude_prompt_interrupts_and_runs_after_current_receive_finishes() -> None:
    manager = CcChatSessionManager()
    client = RecordingClaudeClient()
    sess = CcChatSession(
        id="omni-session",
        cwd="/workspace/omnicompany",
        started_at=time.time(),
        client=client,  # type: ignore[arg-type]
        claude_session_id="claude-real-session",
    )

    await manager.submit_user_prompt(sess, "first long request")
    await asyncio.sleep(0)

    first_consumer = sess.current_receive_task
    assert first_consumer is not None
    assert not first_consumer.done()
    assert client.receive_response_calls == 1
    # 首条消息会被前缀注入 plan 上下文 (无 plan 时注入 "No active plan" 提示)
    assert client.query_calls[0]["prompt"].endswith("first long request")
    assert client.query_calls[0]["session_id"] == "claude-real-session"

    await manager.submit_user_prompt(sess, "please steer the running turn")
    await asyncio.sleep(0)

    assert sess.current_receive_task is first_consumer
    assert client.receive_response_calls == 1
    assert client.interrupt_calls == 1
    assert len(client.query_calls) == 1
    assert sess.pending_interrupt_prompts == ["please steer the running turn"]

    client.release_receive.set()
    await asyncio.wait_for(first_consumer, timeout=1)
    await asyncio.sleep(0)
    assert len(client.query_calls) == 2
    # 第二条消息 plan 未变, 不再注入, 原始 prompt 直传
    assert client.query_calls[1]["prompt"] == "please steer the running turn"
    assert client.query_calls[1]["session_id"] == "claude-real-session"
    assert sess.pending_interrupt_prompts == []
    assert any(
        msg.get("kind") == "text"
        and msg.get("role") == "user"
        and msg.get("content") == "please steer the running turn"
        for msg in sess.event_history
    )


@pytest.mark.asyncio
async def test_stale_in_flight_without_running_consumer_starts_next_prompt() -> None:
    manager = CcChatSessionManager()
    client = RecordingClaudeClient()
    client.release_receive.set()
    sess = CcChatSession(
        id="omni-session",
        cwd="/workspace/omnicompany",
        started_at=time.time(),
        client=client,  # type: ignore[arg-type]
        claude_session_id="claude-real-session",
    )
    sess.in_flight_turn = True
    sess.current_receive_task = None

    await manager.submit_user_prompt(sess, "continue")
    await asyncio.sleep(0)

    assert client.interrupt_calls == 0
    assert len(client.query_calls) == 1
    assert client.query_calls[0]["prompt"].endswith("continue")
    assert client.query_calls[0]["session_id"] == "claude-real-session"
    assert sess.pending_interrupt_prompts == []


@pytest.mark.asyncio
async def test_explicit_claude_interrupt_does_not_cancel_receive_task() -> None:
    manager = CcChatSessionManager()
    client = RecordingClaudeClient()
    sess = CcChatSession(
        id="omni-session",
        cwd="/workspace/omnicompany",
        started_at=time.time(),
        client=client,  # type: ignore[arg-type]
        claude_session_id="claude-real-session",
    )

    await manager.submit_user_prompt(sess, "long request")
    await asyncio.sleep(0)
    receive_task = sess.current_receive_task
    assert receive_task is not None
    assert not receive_task.done()

    await manager.interrupt(sess)
    await asyncio.sleep(0)

    assert client.interrupt_calls == 1
    assert sess.current_receive_task is receive_task
    assert not receive_task.cancelled()
    assert not receive_task.done()

    client.release_receive.set()
    await asyncio.wait_for(receive_task, timeout=1)


@pytest.mark.asyncio
async def test_sequential_claude_prompt_starts_new_consumer_after_previous_finishes() -> None:
    manager = CcChatSessionManager()
    client = RecordingClaudeClient()
    sess = CcChatSession(
        id="omni-session",
        cwd="/workspace/omnicompany",
        started_at=time.time(),
        client=client,  # type: ignore[arg-type]
    )

    client.release_receive.set()
    await manager.submit_user_prompt(sess, "first")
    first_consumer = sess.current_receive_task
    assert first_consumer is not None
    await asyncio.wait_for(first_consumer, timeout=1)
    await asyncio.sleep(0)
    assert sess.current_receive_task is None

    client.release_receive = asyncio.Event()
    await manager.submit_user_prompt(sess, "second")
    await asyncio.sleep(0)

    assert len(client.query_calls) == 2
    # 第二条消息 plan 未变, 不再注入
    assert client.query_calls[1]["prompt"] == "second"
    assert client.written_messages == []
    assert client.receive_response_calls == 2
    second_consumer = sess.current_receive_task
    assert second_consumer is not None
    assert second_consumer is not first_consumer

    client.release_receive.set()
    await asyncio.wait_for(second_consumer, timeout=1)
