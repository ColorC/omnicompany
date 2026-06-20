"""BOSS SIGHT v2-01 P0-a: subagent recursive-spawn guards."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from omnicompany.core.caller_identity import CALLER_ENV, CALLER_SUBAGENT
from omnicompany.dashboard.ccdaemon import chat as chat_mod


@pytest.fixture(autouse=True)
def isolated_chat_meta(monkeypatch):
    monkeypatch.setattr(chat_mod, "_read_meta_store", lambda: {})
    monkeypatch.setattr(chat_mod, "_write_meta_store", lambda store: None)
    monkeypatch.setattr(chat_mod, "_emit_chat_event", lambda **kwargs: "evt_p0a")


def test_cli_subagent_cannot_call_worker_spawn(monkeypatch) -> None:
    """A subagent process must not be able to recursively spawn another worker."""
    from omnicompany.cli.main import cli

    result = CliRunner().invoke(
        cli,
        ["worker", "spawn", "test/plan", "do the next bounded task"],
        env={
            CALLER_ENV: CALLER_SUBAGENT,
            "OMNICOMPANY_SKIP_GUARDIAN_PRECHECK": "1",
        },
    )

    assert result.exit_code != 0
    assert "access denied" in result.output
    assert f"caller='{CALLER_SUBAGENT}'" in result.output


def test_cli_subagent_can_call_review_submit(monkeypatch) -> None:
    """Material submission is the allowed completion path for subagents."""
    from omnicompany.cli.main import cli
    from omnicompany.cli.commands import boss_sight as boss_sight_cli

    captured: dict[str, Any] = {}

    def fake_invoke(router_cls, args: dict[str, Any]) -> str:
        captured["router"] = router_cls.__name__
        captured["args"] = dict(args)
        return "material submitted: id=mat_test"

    monkeypatch.setattr(boss_sight_cli, "_invoke_router", fake_invoke)

    result = CliRunner().invoke(
        cli,
        [
            "review",
            "submit",
            "--kind",
            "markdown",
            "--tier",
            "important",
            "--title",
            "Test material",
            "--plan-id",
            "test/plan",
            "--content",
            "body",
        ],
        env={
            CALLER_ENV: CALLER_SUBAGENT,
            "OMNICOMPANY_SKIP_GUARDIAN_PRECHECK": "1",
        },
    )

    assert result.exit_code == 0, result.output
    assert "material submitted: id=mat_test" in result.output
    assert captured["router"] == "SubmitToReviewstageRouter"
    assert captured["args"]["source_plan_id"] == "test/plan"


@pytest.mark.asyncio
async def test_subagent_claude_session_injects_caller_env_and_bypasses_ui_permissions(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    class FakeOptions:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    class FakeClient:
        def __init__(self, options: FakeOptions) -> None:
            captured["options"] = options.kwargs

        async def connect(self) -> None:
            captured["connected"] = True

    monkeypatch.setattr(chat_mod.casdk, "ClaudeAgentOptions", FakeOptions)
    monkeypatch.setattr(chat_mod.casdk, "ClaudeSDKClient", FakeClient)

    mgr = chat_mod.CcChatSessionManager()
    sess = await mgr.create(
        cwd=str(tmp_path),
        provider="claude_code",
        caller_identity=CALLER_SUBAGENT,
    )

    assert sess.caller_identity == CALLER_SUBAGENT
    assert captured["connected"] is True
    assert captured["options"]["env"] == {CALLER_ENV: CALLER_SUBAGENT}
    assert captured["options"]["permission_mode"] == chat_mod.DEFAULT_PERMISSION_MODE


@pytest.mark.asyncio
async def test_restored_subagent_session_keeps_caller_env_on_runtime_start(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store = {
        "chat-restored": {
            "id": "chat-restored",
            "kind": "chat",
            "cwd": str(tmp_path),
            "started_at": 1,
            "provider": "claude_code",
            "provider_session_id": "claude-provider-session",
            "caller_identity": CALLER_SUBAGENT,
        }
    }
    monkeypatch.setattr(chat_mod, "_read_meta_store", lambda: store)
    captured: dict[str, Any] = {}

    class FakeOptions:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    class FakeClient:
        def __init__(self, options: FakeOptions) -> None:
            captured["options"] = options.kwargs

        async def connect(self) -> None:
            captured["connected"] = True

    monkeypatch.setattr(chat_mod.casdk, "ClaudeAgentOptions", FakeOptions)
    monkeypatch.setattr(chat_mod.casdk, "ClaudeSDKClient", FakeClient)

    mgr = chat_mod.CcChatSessionManager()
    sess = mgr.get("chat-restored")
    assert sess is not None
    assert sess.caller_identity == CALLER_SUBAGENT

    await mgr._ensure_runtime(sess)

    assert captured["connected"] is True
    assert captured["options"]["env"] == {CALLER_ENV: CALLER_SUBAGENT}
    assert captured["options"]["permission_mode"] == chat_mod.DEFAULT_PERMISSION_MODE


@pytest.mark.asyncio
async def test_subagent_live_limit_blocks_recursive_runaway(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(chat_mod, "MAX_LIVE_SUBAGENTS", 1)
    mgr = chat_mod.CcChatSessionManager()
    mgr._sessions["chat-existing"] = chat_mod.CcChatSession(
        id="chat-existing",
        cwd=str(tmp_path),
        started_at=1,
        provider="claude_code",
        caller_identity=CALLER_SUBAGENT,
    )

    with pytest.raises(RuntimeError, match="subagent 并发上限"):
        await mgr.create(
            cwd=str(tmp_path),
            provider="claude_code",
            caller_identity=CALLER_SUBAGENT,
        )


@pytest.mark.asyncio
async def test_subagent_codex_session_gets_guard_env_and_headless_permission(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from omnicompany.dashboard.ccdaemon.providers import codex as codex_mod

    captured: dict[str, Any] = {}

    class FakeCodexProvider:
        def __init__(self, options: dict[str, Any]) -> None:
            captured["options"] = dict(options)

        async def connect(self) -> None:
            captured["connected"] = True

        async def consume_messages(self):
            if False:
                yield {}

    monkeypatch.setattr(codex_mod, "CodexProvider", FakeCodexProvider)

    mgr = chat_mod.CcChatSessionManager()
    sess = await mgr.create(
        cwd=str(tmp_path),
        provider="codex",
        caller_identity=CALLER_SUBAGENT,
    )

    assert sess.caller_identity == CALLER_SUBAGENT
    assert captured["connected"] is True
    assert captured["options"]["permission_mode"] == chat_mod.DEFAULT_PERMISSION_MODE
    assert captured["options"]["env"][CALLER_ENV] == CALLER_SUBAGENT
