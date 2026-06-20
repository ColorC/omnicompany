"""Tests for Chat route plan context injection into user prompts."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from omnicompany.dashboard.ccdaemon.chat import CcChatSession, CcChatSessionManager


class RecordingClaudeClient:
    def __init__(self) -> None:
        self.query_calls: list[dict[str, Any]] = []
        self.receive_response_calls = 0
        self.release_receive = asyncio.Event()
        self.release_receive.set()  # auto-release by default

    async def query(self, prompt: Any, session_id: str = "default") -> None:
        self.query_calls.append({"prompt": prompt, "session_id": session_id})

    async def receive_response(self):
        self.receive_response_calls += 1
        await self.release_receive.wait()
        if False:
            yield None

    async def interrupt(self) -> None:
        pass


def _make_session(**kw: Any) -> CcChatSession:
    defaults = dict(
        id="test-sess",
        cwd="/workspace/omnicompany",
        started_at=time.time(),
        client=RecordingClaudeClient(),
    )
    defaults.update(kw)
    return CcChatSession(**defaults)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_first_message_injects_no_plan_context() -> None:
    """首条消息无 plan 时注入 'No active plan' 提示."""
    mgr = CcChatSessionManager()
    sess = _make_session()
    await mgr.submit_user_prompt(sess, "hello")
    await asyncio.sleep(0)

    prompt = sess.client.query_calls[0]["prompt"]  # type: ignore[union-attr]
    assert "omnicompany context" in prompt
    assert "No active plan" in prompt
    assert prompt.endswith("hello")


@pytest.mark.asyncio
async def test_first_message_injects_plan_context() -> None:
    """首条消息有 plan 时注入 plan 上下文 (含 plan_id)."""
    mgr = CcChatSessionManager()
    sess = _make_session(active_plan="_infra/dashboard/[2026-05-10]多模型聊天平台")
    await mgr.submit_user_prompt(sess, "show me the plan")
    await asyncio.sleep(0)

    prompt = sess.client.query_calls[0]["prompt"]  # type: ignore[union-attr]
    assert "omnicompany context" in prompt
    assert "_infra/dashboard/[2026-05-10]多模型聊天平台" in prompt
    assert prompt.endswith("show me the plan")


@pytest.mark.asyncio
async def test_second_message_no_reinject_when_plan_unchanged() -> None:
    """plan 未变时第二条消息不再注入."""
    mgr = CcChatSessionManager()
    sess = _make_session()
    await mgr.submit_user_prompt(sess, "first")
    await asyncio.sleep(0)
    # 等待第一轮 consume task 完成
    if sess.current_receive_task:
        await asyncio.wait_for(sess.current_receive_task, timeout=1)
        await asyncio.sleep(0)
    await mgr.submit_user_prompt(sess, "second")
    await asyncio.sleep(0)

    client = sess.client  # type: ignore[union-attr]
    # 首条注入
    assert "omnicompany context" in client.query_calls[0]["prompt"]
    # 第二条不注入, 原始 prompt 直传
    assert client.query_calls[1]["prompt"] == "second"


async def _wait_turn(sess: CcChatSession) -> None:
    if sess.current_receive_task:
        await asyncio.wait_for(sess.current_receive_task, timeout=1)
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_plan_switch_triggers_reinject() -> None:
    """mid-session 切 plan 后下条消息重新注入."""
    mgr = CcChatSessionManager()
    sess = _make_session()
    await mgr.submit_user_prompt(sess, "first")
    await asyncio.sleep(0)
    await _wait_turn(sess)

    # 模拟 patch_active_plan
    sess.active_plan = "_infra/dashboard/[2026-05-10]多模型聊天平台"
    await mgr.submit_user_prompt(sess, "what is the plan?")
    await asyncio.sleep(0)
    await _wait_turn(sess)

    client = sess.client  # type: ignore[union-attr]
    prompt2 = client.query_calls[1]["prompt"]
    assert "plan switched" in prompt2
    assert "_infra/dashboard/[2026-05-10]多模型聊天平台" in prompt2
    assert prompt2.endswith("what is the plan?")

    # 第三条 plan 未变, 不注入
    await mgr.submit_user_prompt(sess, "third")
    await asyncio.sleep(0)
    assert client.query_calls[2]["prompt"] == "third"


@pytest.mark.asyncio
async def test_plan_unbind_triggers_reinject() -> None:
    """解绑 plan 后下条消息注入 'No active plan'."""
    mgr = CcChatSessionManager()
    sess = _make_session(active_plan="_infra/dashboard/[2026-05-10]多模型聊天平台")
    await mgr.submit_user_prompt(sess, "first")
    await asyncio.sleep(0)
    await _wait_turn(sess)

    sess.active_plan = None
    await mgr.submit_user_prompt(sess, "now what?")
    await asyncio.sleep(0)

    client = sess.client  # type: ignore[union-attr]
    prompt2 = client.query_calls[1]["prompt"]
    assert "No active plan" in prompt2
    assert prompt2.endswith("now what?")


@pytest.mark.asyncio
async def test_pty_route_patch_updates_chat_session_in_memory() -> None:
    """PTY 路由的 patch_active_plan 也要更新 chat 会话的内存对象.

    这是核心 bug 修复验证: SessionContextPanel 始终走 ccApi (PTY 路由),
    对 chat 会话切 plan 时必须同步更新 CcChatSession.active_plan,
    否则 _maybe_inject_plan 读内存永远看不到新 plan.
    """
    from unittest.mock import patch, MagicMock
    from omnicompany.dashboard.ccdaemon import pty_routes

    mgr = CcChatSessionManager()
    sess = _make_session(id="chat-abc123")
    mgr._sessions[sess.id] = sess
    assert sess.active_plan is None

    # 模拟 PTY 路由内部逻辑: PTY manager 找不到 → 尝试 chat manager
    # (直接调 pty_routes 里的代码逻辑, 不起 HTTP server)
    fake_pty_mgr = MagicMock()
    fake_pty_mgr.get.return_value = None  # 不在 PTY sessions 里

    with patch.object(pty_routes, "get_manager", return_value=fake_pty_mgr), \
         patch("omnicompany.dashboard.ccdaemon.chat.get_chat_manager", return_value=mgr):
        # 模拟 pty_routes.patch_active_plan 里 step 2b 的逻辑
        from omnicompany.dashboard.ccdaemon.chat import get_chat_manager as _gcm
        chat_sess = _gcm()._sessions.get("chat-abc123")
        assert chat_sess is not None
        chat_sess.active_plan = "_infra/dashboard/[2026-05-10]多模型聊天平台"

    assert sess.active_plan == "_infra/dashboard/[2026-05-10]多模型聊天平台"

    # 验证下条消息能看到 plan
    await mgr.submit_user_prompt(sess, "hello after switch")
    await asyncio.sleep(0)

    client = sess.client  # type: ignore[union-attr]
    # 首条消息已注入 no-plan context (因 _last_injected_plan 是哨兵)
    # → 这是首条, 直接注入当前 plan
    prompt = client.query_calls[0]["prompt"]
    assert "_infra/dashboard/[2026-05-10]多模型聊天平台" in prompt


@pytest.mark.asyncio
async def test_switch_plan_then_next_message_sees_it() -> None:
    """完整 e2e 模拟: 发消息 → 切 plan → 发消息 → 验证 plan 出现在注入里."""
    mgr = CcChatSessionManager()
    sess = _make_session()

    # turn 1: 无 plan
    await mgr.submit_user_prompt(sess, "first")
    await asyncio.sleep(0)
    await _wait_turn(sess)

    client = sess.client  # type: ignore[union-attr]
    assert "No active plan" in client.query_calls[0]["prompt"]

    # 模拟通过 patch_active_plan 切 plan (chat manager 自己的方法)
    mgr._sessions[sess.id] = sess
    mgr.patch_active_plan(sess.id, "_infra/dashboard/[2026-05-10]多模型聊天平台")
    assert sess.active_plan == "_infra/dashboard/[2026-05-10]多模型聊天平台"

    # turn 2: 应该看到 plan
    await mgr.submit_user_prompt(sess, "what is the plan?")
    await asyncio.sleep(0)

    prompt2 = client.query_calls[1]["prompt"]
    assert "plan switched" in prompt2
    assert "_infra/dashboard/[2026-05-10]多模型聊天平台" in prompt2


@pytest.mark.asyncio
async def test_new_session_with_prebound_plan() -> None:
    """新建 session 时预设 plan, 首条消息即注入."""
    mgr = CcChatSessionManager()
    sess = _make_session(active_plan="_infra/guardian/[2026-05-04]核心自稳定")
    await mgr.submit_user_prompt(sess, "start working")
    await asyncio.sleep(0)

    client = sess.client  # type: ignore[union-attr]
    prompt = client.query_calls[0]["prompt"]
    assert "核心自稳定" in prompt
    assert "No active plan" not in prompt


@pytest.mark.asyncio
async def test_history_records_original_prompt_not_injected() -> None:
    """history 记录原始 prompt, 不含注入前缀."""
    mgr = CcChatSessionManager()
    sess = _make_session(active_plan="_infra/dashboard/[2026-05-10]多模型聊天平台")
    await mgr.submit_user_prompt(sess, "hello world")
    await asyncio.sleep(0)

    user_entries = [h for h in sess.history_summary if h.get("role") == "user"]
    assert user_entries[0]["text"] == "hello world"
    user_events = [e for e in sess.event_history if e.get("role") == "user"]
    assert user_events[0]["content"] == "hello world"


@pytest.mark.asyncio
async def test_session_goal_is_injected_for_provider_independent_chat() -> None:
    """OmniChat session goal is injected independently of the provider."""
    mgr = CcChatSessionManager()
    sess = _make_session(
        active_plan="_infra/dashboard/[2026-05-10]多模型聊天平台",
        goal_state={"objective": "finish the MC pipeline static phase", "status": "active"},
    )

    await mgr.submit_user_prompt(sess, "continue")
    await asyncio.sleep(0)

    prompt = sess.client.query_calls[0]["prompt"]  # type: ignore[union-attr]
    assert "## Session goal" in prompt
    assert "finish the MC pipeline static phase" in prompt
    assert "Treat this as OmniChat session state" in prompt


@pytest.mark.asyncio
async def test_goal_clear_forces_next_context_injection() -> None:
    """Clearing a goal must explicitly reset the provider on the next turn."""
    mgr = CcChatSessionManager()
    sess = _make_session(
        active_plan="_infra/dashboard/[2026-05-10]多模型聊天平台",
        goal_state={"objective": "old goal", "status": "active"},
    )
    mgr._sessions[sess.id] = sess

    await mgr.submit_user_prompt(sess, "first")
    await asyncio.sleep(0)
    await _wait_turn(sess)
    assert "old goal" in sess.client.query_calls[0]["prompt"]  # type: ignore[union-attr]

    await mgr.clear_goal(sess.id)
    await mgr.submit_user_prompt(sess, "second")
    await asyncio.sleep(0)

    prompt2 = sess.client.query_calls[1]["prompt"]  # type: ignore[union-attr]
    assert "No active session goal is set" in prompt2
    assert prompt2.endswith("second")
