"""聊天去返回: ccdaemon 直发上游 wire NormalizedMessage 的转换函数单测。

证规格 diff 出的字段错位都已修正 (error→content / input→toolInput / result→content /
text 加 role / session_created 加 sessionId), 以及信封补全 (id/sessionId/provider)。
规格: docs/plans/dashboard/[2026-05-23]BOSS-SIGHT/聊天重建_特性保留与清理清单.md
"""
from __future__ import annotations

import json

import pytest

from omnicompany.dashboard.ccdaemon.chat import (
    CcChatSession,
    _finalize_nm,
    _message_to_normalized,
    _nm_provider,
    _provider_nm_to_wire,
)


def _sess(provider: str = "claude_code") -> CcChatSession:
    return CcChatSession(id="chat-test123", cwd=".", started_at=0.0, provider=provider)


# ── _finalize_nm: 信封补全 ────────────────────────────────────────────────

def test_finalize_fills_envelope():
    sess = _sess()
    nm = _finalize_nm({"kind": "text", "role": "assistant", "content": "hi"}, sess)
    assert nm["sessionId"] == "chat-test123"  # wrapper id, 不暴露 claude UUID
    assert nm["provider"] == "claude"          # claude_code → claude
    assert nm["id"].startswith("text_")
    assert nm["timestamp"]


def test_finalize_stream_delta_random_id_not_streaming_key():
    sess = _sess()
    nm = _finalize_nm({"kind": "stream_delta", "content": "x"}, sess)
    assert not nm["id"].startswith("__streaming_")  # __streaming_ 是前端 store 私有 key


def test_finalize_preserves_existing_id():
    sess = _sess()
    nm = _finalize_nm({"kind": "tool_use", "id": "tool_x_use", "toolId": "x"}, sess)
    assert nm["id"] == "tool_x_use"  # 稳定 id 保留供 snapshot 去重


def test_nm_provider_mapping():
    assert _nm_provider(_sess("claude_code")) == "claude"
    assert _nm_provider(_sess("codex")) == "codex"
    assert _nm_provider(_sess("controller")) == "controller"


# ── _provider_nm_to_wire: 字段名规整 (路径 B) ─────────────────────────────

def test_wire_text_adds_role():
    nm = _provider_nm_to_wire({"kind": "text", "content": "hi"})
    assert nm["role"] == "assistant"


def test_wire_tool_use_input_to_toolInput():
    nm = _provider_nm_to_wire({"kind": "tool_use", "toolId": "t", "toolName": "Bash", "input": {"cmd": "ls"}})
    assert nm["toolInput"] == {"cmd": "ls"}
    assert "input" not in nm


def test_wire_tool_result_result_to_content_str():
    nm = _provider_nm_to_wire({"kind": "tool_result", "toolId": "t", "result": "ok", "isError": False})
    assert nm["content"] == "ok"
    assert "result" not in nm


def test_wire_tool_result_nonstr_json_dumps():
    nm = _provider_nm_to_wire({"kind": "tool_result", "toolId": "t", "result": {"a": 1}})
    assert nm["content"] == json.dumps({"a": 1}, ensure_ascii=False)


def test_wire_error_to_content():
    nm = _provider_nm_to_wire({"kind": "error", "error": "boom"})
    assert nm["content"] == "boom"
    assert "error" not in nm


def test_wire_session_created_adds_sessionId():
    nm = _provider_nm_to_wire({"kind": "session_created", "newSessionId": "s1"})
    assert nm["sessionId"] == "s1"


# ── _message_to_normalized: SDK 消息 → wire NM (路径 A) ───────────────────
# 用真 SDK 对象构造; 若 SDK 版本字段不符则跳过 (字段逻辑已被上面 wire 测试覆盖大半)。

def _casdk():
    import claude_agent_sdk as casdk
    return casdk


def test_msg_assistant_text_thinking_tooluse():
    casdk = _casdk()
    try:
        msg = casdk.AssistantMessage(
            content=[casdk.TextBlock(text="hello"),
                     casdk.ThinkingBlock(thinking="ponder", signature=""),
                     casdk.ToolUseBlock(id="t1", name="Bash", input={"cmd": "ls"})],
            model="claude-x", parent_tool_use_id=None, error=None, usage={},
        )
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"SDK AssistantMessage 构造签名不符, 跳过: {e}")
    out = _message_to_normalized(msg, _sess())
    kinds = [n["kind"] for n in out]
    assert kinds == ["text", "thinking", "tool_use"]
    assert out[0] == {"kind": "text", "role": "assistant", "content": "hello"}
    assert out[1] == {"kind": "thinking", "content": "ponder"}
    tu = out[2]
    assert tu["toolName"] == "Bash" and tu["toolInput"] == {"cmd": "ls"}
    assert "input" not in tu  # 必须是 toolInput 不是 input
    assert tu["id"] == "tool_chat-test123_t1_use"


def test_msg_user_tool_result():
    casdk = _casdk()
    try:
        msg = casdk.UserMessage(
            content=[casdk.ToolResultBlock(tool_use_id="t1", content="done", is_error=False)],
            parent_tool_use_id=None, uuid="u1", tool_use_result=None,
        )
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"SDK UserMessage 构造签名不符, 跳过: {e}")
    out = _message_to_normalized(msg, _sess())
    assert len(out) == 1
    tr = out[0]
    assert tr["kind"] == "tool_result" and tr["content"] == "done" and tr["isError"] is False
    assert "result" not in tr  # 必须是 content 不是 result
