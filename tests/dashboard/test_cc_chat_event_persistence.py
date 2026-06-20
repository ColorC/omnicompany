from __future__ import annotations

from typing import Any

import pytest

from omnicompany.dashboard.ccdaemon import chat


class FakeProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.options: dict[str, Any] = {}
        self.prompts: list[str] = []

    async def send_prompt(self, prompt: str, options: dict[str, Any] | None = None) -> None:
        if self.fail:
            raise RuntimeError("provider refused input")
        self.prompts.append(prompt)


def test_chat_rename_persists_metadata_and_event(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    written: dict[str, Any] = {}
    emitted: list[dict[str, Any]] = []

    monkeypatch.setattr(chat, "_read_meta_store", lambda: {})
    monkeypatch.setattr(chat, "_write_meta_store", lambda store: written.update(store))
    monkeypatch.setattr(
        chat,
        "_emit_chat_event",
        lambda **kwargs: emitted.append(kwargs) or "evt_1",
    )

    mgr = chat.CcChatSessionManager()
    sess = chat.CcChatSession(id="sess_rename", cwd=str(tmp_path), started_at=1.0, provider="codex")
    mgr._sessions[sess.id] = sess

    result = mgr.rename(sess.id, "short custom title")

    assert result["name"] == "short custom title"
    assert written[sess.id]["name"] == "short custom title"
    assert emitted[-1]["event_type"] == "chat.session.renamed"
    assert emitted[-1]["payload"]["name"] == "short custom title"


def test_chat_metadata_patch_persists_model_and_permission_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    written: dict[str, Any] = {}
    emitted: list[dict[str, Any]] = []

    monkeypatch.setattr(chat, "_read_meta_store", lambda: {})
    monkeypatch.setattr(chat, "_write_meta_store", lambda store: written.update(store))
    monkeypatch.setattr(
        chat,
        "_emit_chat_event",
        lambda **kwargs: emitted.append(kwargs) or f"evt_{len(emitted)}",
    )

    provider = FakeProvider()
    mgr = chat.CcChatSessionManager()
    sess = chat.CcChatSession(
        id="sess_controls",
        cwd=str(tmp_path),
        started_at=1.0,
        provider="codex",
        provider_impl=provider,
    )
    mgr._sessions[sess.id] = sess

    result = mgr.patch_metadata(
        sess.id,
        favorite=True,
        model="gpt-test-model",
        permission_mode="bypassPermissions",
    )

    assert result == {
        "session_id": sess.id,
        "archived": False,
        "favorite": True,
        "model": "gpt-test-model",
        "permission_mode": "bypassPermissions",
        "effective": "next_user_turn",
    }
    assert written[sess.id]["model"] == "gpt-test-model"
    assert written[sess.id]["permission_mode"] == "bypassPermissions"
    assert provider.options["model"] == "gpt-test-model"
    assert provider.options["permission_mode"] == "bypassPermissions"
    assert emitted[-1]["event_type"] == "chat.session.metadata.updated"
    assert emitted[-1]["payload"]["permission_mode"] == "bypassPermissions"


def test_chat_metadata_patch_can_clear_model(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    written: dict[str, Any] = {}
    monkeypatch.setattr(chat, "_read_meta_store", lambda: {})
    monkeypatch.setattr(chat, "_write_meta_store", lambda store: written.update(store))
    monkeypatch.setattr(chat, "_emit_chat_event", lambda **kwargs: "evt_clear")

    provider = FakeProvider()
    provider.options["model"] = "gpt-test-model"
    mgr = chat.CcChatSessionManager()
    sess = chat.CcChatSession(
        id="sess_clear_model",
        cwd=str(tmp_path),
        started_at=1.0,
        provider="codex",
        provider_impl=provider,
        model="gpt-test-model",
    )
    mgr._sessions[sess.id] = sess

    result = mgr.patch_metadata(sess.id, model=None)

    assert result["model"] == "(local default)"
    assert written[sess.id]["model"] == "(local default)"
    assert "model" not in provider.options


def test_chat_metadata_patch_rejects_invalid_permission_mode(tmp_path) -> None:
    mgr = chat.CcChatSessionManager()
    sess = chat.CcChatSession(id="sess_bad_mode", cwd=str(tmp_path), started_at=1.0, provider="codex")
    mgr._sessions[sess.id] = sess

    with pytest.raises(ValueError, match="invalid permission_mode"):
        mgr.patch_metadata(sess.id, permission_mode="ask-every-time")

    assert sess.current_permission_mode == "default"


def test_chat_restore_loads_persisted_model_and_permission_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        chat,
        "_read_meta_store",
        lambda: {
            "sess_restored": {
                "kind": "chat",
                "id": "sess_restored",
                "cwd": str(tmp_path),
                "started_at": 1.0,
                "provider": "codex",
                "name": "restored",
                "model": "(local default)",
                "permission_mode": "acceptEdits",
            }
        },
    )

    mgr = chat.CcChatSessionManager()
    sess = mgr.get("sess_restored")

    assert sess is not None
    assert sess.model is None
    assert sess.current_permission_mode == "acceptEdits"


@pytest.mark.asyncio
async def test_user_prompt_is_not_accepted_or_saved_when_provider_send_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    emitted: list[dict[str, Any]] = []
    monkeypatch.setattr(
        chat,
        "_emit_chat_event",
        lambda **kwargs: emitted.append(kwargs) or f"evt_{len(emitted)}",
    )

    mgr = chat.CcChatSessionManager()
    sess = chat.CcChatSession(
        id="sess_fail",
        cwd=str(tmp_path),
        started_at=1.0,
        provider="codex",
        provider_impl=FakeProvider(fail=True),
    )

    await mgr.submit_user_prompt(sess, "please do work")

    event_types = [event["event_type"] for event in emitted]
    assert "chat.input.user.requested" in event_types
    assert "chat.input.user.accepted" not in event_types
    assert sess.history_summary == []
    assert [msg.get("kind") for msg in sess.event_history] == ["error"]
    assert sess.event_history[0]["content"] == "provider refused input"


@pytest.mark.asyncio
async def test_user_prompt_is_saved_only_after_provider_accepts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    emitted: list[dict[str, Any]] = []
    monkeypatch.setattr(
        chat,
        "_emit_chat_event",
        lambda **kwargs: emitted.append(kwargs) or f"evt_{len(emitted)}",
    )

    provider = FakeProvider()
    mgr = chat.CcChatSessionManager()
    sess = chat.CcChatSession(
        id="sess_ok",
        cwd=str(tmp_path),
        started_at=1.0,
        provider="codex",
        provider_impl=provider,
    )

    await mgr.submit_user_prompt(sess, "please do work")

    event_types = [event["event_type"] for event in emitted]
    assert event_types.index("chat.input.user.requested") < event_types.index("chat.input.user.accepted")
    assert provider.prompts
    assert sess.history_summary == [{"role": "user", "text": "please do work"}]
    assert sess.event_history[-1]["role"] == "user"
    assert sess.event_history[-1]["content"] == "please do work"
