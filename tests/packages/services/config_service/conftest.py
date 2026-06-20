# [OMNI] origin=claude-code domain=tests/config_service ts=2026-04-24T00:00:00Z type=test_infra
"""pytest fixtures 共享 · mock notifier + 构造 coordinator + FeishuIncomingMessage 工厂."""
from __future__ import annotations

import itertools

import pytest

from omnicompany.packages.services.config_service.coordinator import (
    ConfigServiceCoordinator,
)
from omnicompany.packages.services.config_service.feishu.message import (
    FeishuIncomingMessage,
)
from omnicompany.runtime.buses import WebBus
from tests.packages.services.config_service.mocks import MockFeishuNotifier


@pytest.fixture
def mock_notifier() -> MockFeishuNotifier:
    return MockFeishuNotifier()


@pytest.fixture
def coordinator(mock_notifier: MockFeishuNotifier, tmp_path, monkeypatch) -> ConfigServiceCoordinator:
    """Coordinator 实例 · notifier 已 mock · threads.db 用临时 tmp_path."""
    db_path = tmp_path / "threads.db"
    monkeypatch.setenv("OMNI_CS_AGENT_THREAD_DB", str(db_path))
    # test 跳过审批流 (不 HumanBus.ask · 直接 finalize 完成态卡) · 避免 pytest 卡 1h
    monkeypatch.setenv("OMNI_CS_AGENT_SKIP_APPROVAL", "1")
    # WebBus 仍真 (IntentClassifier / agent loop 内部调 LLM 走 WebBus audit, 不走 Feishu)
    real_web_bus = WebBus()
    c = ConfigServiceCoordinator(
        notifier=mock_notifier,           # ← 关键 mock
        web_bus=real_web_bus,
        bot_open_id="ou_bot_mock",
    )
    return c


_msg_counter = itertools.count(1)


def make_msg(
    text: str,
    *,
    thread_id: str = "",
    sender_open_id: str = "ou_user_test",
    sender_type: str = "user",
    chat_type: str = "p2p",
    message_type: str = "text",
) -> FeishuIncomingMessage:
    n = next(_msg_counter)
    return FeishuIncomingMessage(
        message_id=f"om_test_{n:08x}",
        chat_id=f"oc_test_{n:08x}",
        chat_type=chat_type,
        message_type=message_type,
        sender_open_id=sender_open_id,
        sender_type=sender_type,
        tenant_key="mock-tenant",
        create_time_ms=0,
        text=text,
        raw_content="",
        thread_id=thread_id,
    )


@pytest.fixture
def msg_factory():
    """返 make_msg 函数 · test 里 `msg_factory(text, ...)` 构造消息."""
    return make_msg
