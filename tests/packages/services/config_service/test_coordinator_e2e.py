# [OMNI] origin=claude-code domain=tests/config_service ts=2026-04-24T00:00:00Z type=e2e
"""CS-Agent Coordinator 端到端测试 · mock Feishu · 真 LLM.

**分级**:
  - 快 (默认跑): classifier + casual_reply 路径 · ~3s/case
  - slow (pytest -m slow): agent loop 类 (query/change) · ~15-60s/case

**真的东西** (按 L1 铁律):
  - LLM 调用全部真 (qwen-flash classifier, gemini-flash-lite casual, qwen-3.6-plus agent)
  - Bash / grep / glob / read_file 真执行 (agent 会真扫 scm / SDK)
  - Feishu 被 mock 拦 · **不真发消息**
  - ThreadStore 用 tmp_path sqlite (每 test fresh)

**运行**:
  pytest tests/packages/services/config_service/                    # 快路径
  pytest tests/packages/services/config_service/ -m slow            # 含 agent loop
  pytest tests/packages/services/config_service/ -m "slow or not slow"  # 全跑
"""
from __future__ import annotations

import pytest


# ═════════════════════════════════════════════════════════════════
# 快速路径 (case 5-10 · 不跑 agent loop · <5s/case)
# ═════════════════════════════════════════════════════════════════


def test_bot_self_skip(coordinator, mock_notifier, msg_factory):
    """#9 · bot 自己发的消息 · 0 API 调用."""
    msg = msg_factory("任何内容", sender_open_id="ou_bot_mock")
    coordinator.handle_message_sync(msg)
    assert mock_notifier.calls == []


def test_non_user_sender_skip(coordinator, mock_notifier, msg_factory):
    """sender_type != user · 0 API 调用."""
    msg = msg_factory("帮我查表", sender_type="app")
    coordinator.handle_message_sync(msg)
    assert mock_notifier.calls == []


def test_emoji_first_ack(coordinator, mock_notifier, msg_factory):
    """#8 · emoji reaction 必在其他任何 API 之前."""
    msg = msg_factory("你好")
    coordinator.handle_message_sync(msg)
    methods = mock_notifier.methods()
    assert len(methods) >= 1
    assert methods[0] == "add_reaction", (
        f"emoji ack 必须第一个 · 实际顺序: {methods}"
    )
    # message_id 对得上
    first = mock_notifier.first("add_reaction")
    assert first is not None
    assert first["message_id"] == msg.message_id
    assert first["emoji_type"] == "OK"


def test_ambiguous_casual_p2p(coordinator, mock_notifier, msg_factory):
    """#5 · 闲聊 p2p · casual_reply 含自我介绍 · 不冷漠."""
    msg = msg_factory("你好")
    coordinator.handle_message_sync(msg)
    # 应走 send_text (非话题)
    send_texts = mock_notifier.find("send_text")
    assert len(send_texts) >= 1, f"应发 text · 实际 calls: {mock_notifier.methods()}"
    content = send_texts[0]["text"]
    # 应是友好 · 含config_table助手自我介绍
    assert any(k in content for k in ("CS-Agent", "config_table", "助手", "帮")), \
        f"casual_reply 应有config_table助手自我介绍 · 实际: {content!r}"
    # 不是冷漠模板
    assert "这个需求不在" not in content
    # 应在话题外 · 不走 send_in_thread
    assert mock_notifier.find("send_in_thread") == []


def test_ambiguous_casual_in_thread(coordinator, mock_notifier, msg_factory):
    """#6 · 闲聊在话题里 · 走 send_in_thread 不走 p2p text."""
    msg = msg_factory("你好", thread_id="omt_pre_existing")
    coordinator.handle_message_sync(msg)
    # 关键: thread_id 有 → 应走 send_in_thread 不 send_text
    in_threads = mock_notifier.find("send_in_thread")
    texts = mock_notifier.find("send_text")
    assert len(in_threads) >= 1, (
        f"thread_id 带 · 应 send_in_thread · 实际 methods: {mock_notifier.methods()}"
    )
    assert len(texts) == 0, f"话题里不应走 p2p text · 实际: {texts}"
    # 锚点 = 用户消息 id
    assert in_threads[0]["anchor_message_id"] == msg.message_id


def test_unsupported_casual(coordinator, mock_notifier, msg_factory):
    """#7 · 超域需求 · casual_reply 友好不冷漠."""
    msg = msg_factory("帮我订个午饭")
    coordinator.handle_message_sync(msg)
    texts = mock_notifier.find("send_text")
    assert len(texts) >= 1
    content = texts[0]["text"]
    # 不是硬邦邦官话
    assert "这个需求不在 CS-Agent 能做的范围" not in content, \
        f"不应是老硬编码官话 · 实际: {content!r}"
    # 应该提到config_table/配置 (说明自己是干啥的)
    assert any(k in content for k in ("config_table", "配置", "字段", "CS-Agent", "助手")), \
        f"casual_reply 应提及自己身份/能力 · 实际: {content!r}"


def test_empty_text(coordinator, mock_notifier, msg_factory):
    """#10 · 空消息 · classifier 会 fast-path 返 unsupported · casual_reply 回."""
    msg = msg_factory("")
    coordinator.handle_message_sync(msg)
    # 应至少有 emoji + casual reply
    methods = mock_notifier.methods()
    assert "add_reaction" in methods
    # 空消息 classifier 直接给 unsupported · 走 casual_reply
    assert any(m in ("send_text", "send_in_thread") for m in methods), \
        f"空消息也应回 · 实际: {methods}"


# ═════════════════════════════════════════════════════════════════
# 慢路径 (case 1-4 · agent loop · ~15-60s/case)
# ═════════════════════════════════════════════════════════════════


@pytest.mark.slow
def test_query_p2p_streaming_card(coordinator, mock_notifier, msg_factory):
    """#1 · p2p query · 应走 streaming card + reply_in_thread=True 建话题."""
    msg = msg_factory("TavernPool 的 PoolType 字段取值有哪些?")
    coordinator.handle_message_sync(msg)
    methods = mock_notifier.methods()
    # 必有 emoji + reply_message(reply_in_thread=True) 建话题 + 至少 1 次 PATCH finalize
    assert "add_reaction" in methods
    replies = [c for c in mock_notifier.calls
               if c["method"] == "reply_message" and c.get("reply_in_thread")]
    assert len(replies) >= 1, f"query 应 reply_in_thread=True 建话题 · 实际: {methods}"
    # 应有 PATCH (流式更新 + finalize)
    assert "patch_message" in methods, f"应有流式卡 PATCH · 实际: {methods}"


@pytest.mark.slow
def test_query_in_thread_no_session(coordinator, mock_notifier, msg_factory):
    """#2 · p2p query 带 thread_id 但 session 不存在 · 应仍归属话题.

    当前实现: session 不存在 · 走 _handle_query_streaming · reply_in_thread=True
    对用户消息做 reply · 协作平台实际会 "归属原话题" (smoke 实测确认).
    """
    msg = msg_factory(
        "Tavern 表怎么加characters?",
        thread_id="omt_pre_existing_xxx",
    )
    coordinator.handle_message_sync(msg)
    methods = mock_notifier.methods()
    assert "add_reaction" in methods
    # 走了 streaming card (reply_message 或 send_in_thread · 取决于架构路径)
    assert any(m in ("reply_message", "send_in_thread") for m in methods), \
        f"话题中 query 应归属话题 · 实际: {methods}"


@pytest.mark.slow
def test_change_p2p_produces_plan(coordinator, mock_notifier, msg_factory):
    """#3 · change 请求 · plan markdown 应含 7 section."""
    msg = msg_factory("给 Tavern 加characters 119/116/113")
    coordinator.handle_message_sync(msg)
    methods = mock_notifier.methods()
    assert "add_reaction" in methods
    # finalize PATCH 的最后一张卡应含 7 section 内容
    patches = mock_notifier.find("patch_message")
    assert len(patches) >= 1, f"change 应产卡 · 实际: {methods}"
    # 看最后一张卡 (finalize) 的 markdown 内容是否含 section 标题
    last_card = patches[-1]["card"]
    # card 是 dict · 递归抽所有 markdown content
    all_text = _flatten_card_text(last_card)
    for section in ("业务", "目标表", "预期文件"):
        assert section in all_text, (
            f"plan 缺少 section '{section}' · 实际内容: {all_text[:300]}"
        )


@pytest.mark.slow
def test_change_thread_followup_carries_previous_plan(
    coordinator, mock_notifier, msg_factory,
):
    """#4 · 续轮带 previous_plan · 要求先跑一次首轮建 session, 再续轮.

    此 case 有两条消息 · 流程: change_new → change_thread_followup.
    仅验续轮能正确识别 + 不崩 + 发到同话题.
    """
    # 首轮
    msg1 = msg_factory("给 Tavern 加characters 119")
    coordinator.handle_message_sync(msg1)
    # thread_id 从 reply_message 返回拿
    reply1 = next((c for c in mock_notifier.calls
                   if c["method"] == "reply_message" and c.get("reply_in_thread")), None)
    assert reply1 is not None, f"首轮应建话题 · methods: {mock_notifier.methods()}"
    thread_id = reply1["returned_thread_id"]

    # 续轮 · 同话题
    mock_notifier.clear()
    msg2 = msg_factory("再加 116", thread_id=thread_id)
    coordinator.handle_message_sync(msg2)
    methods = mock_notifier.methods()
    # 续轮应走 send_in_thread 路径 (anchor_msg_id=首条 msg.message_id)
    in_threads = mock_notifier.find("send_in_thread")
    patches = mock_notifier.find("patch_message")
    # 至少其一 (StreamingCard start 走 send_in_thread · 后面 PATCH 更新)
    assert in_threads or patches, (
        f"续轮应归属话题 (send_in_thread 或 patch) · 实际: {methods}"
    )


# ═════════════════════════════════════════════════════════════════
# helpers
# ═════════════════════════════════════════════════════════════════


def _flatten_card_text(card: dict) -> str:
    """递归gacha_draw里所有 markdown content 拼成 string · 用于断言 section 存在."""
    if not isinstance(card, dict):
        return ""
    parts: list[str] = []
    # header title
    hdr = card.get("header") or {}
    if isinstance(hdr, dict):
        t = (hdr.get("title") or {}).get("content") if isinstance(hdr.get("title"), dict) else ""
        if t:
            parts.append(str(t))
    # body elements (recurse)
    def _walk(obj):
        if isinstance(obj, dict):
            if obj.get("tag") in ("markdown", "plain_text", "text"):
                c = obj.get("content") or obj.get("text") or ""
                if c:
                    parts.append(str(c))
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)
    _walk(card.get("body") or {})
    return "\n".join(parts)
