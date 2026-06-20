from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from omnicompany.dashboard.ccdaemon.providers import codex as codex_module
from omnicompany.dashboard.ccdaemon.providers.codex import CodexProvider


class BlockingStream:
    def __init__(self, signal: Any | None) -> None:
        self.signal = signal
        self.entered = asyncio.Event()
        self.events = self._events()

    async def _events(self):
        self.entered.set()
        if False:
            yield None
        if self.signal is None:
            await asyncio.Event().wait()
            return
        await self.signal.wait()
        raise RuntimeError("aborted by test")


class RecordingThread:
    id = "codex-thread"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.streams: list[BlockingStream] = []
        self.called = asyncio.Event()

    async def run_streamed(self, prompt: str, turn_options: dict[str, Any] | None = None) -> Any:
        stream = BlockingStream((turn_options or {}).get("signal"))
        self.calls.append({"prompt": prompt, "turn_options": turn_options, "stream": stream})
        self.streams.append(stream)
        self.called.set()
        return stream


class DelayedCompleteStream:
    def __init__(self, signal: Any | None) -> None:
        self.signal = signal
        self.release = asyncio.Event()
        self.events = self._events()

    async def _events(self):
        yield SimpleNamespace(type="turn.completed", usage=None)
        await self.release.wait()


class DelayedCompleteThread:
    id = "codex-thread"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.streams: list[DelayedCompleteStream] = []

    async def run_streamed(self, prompt: str, turn_options: dict[str, Any] | None = None) -> Any:
        stream = DelayedCompleteStream((turn_options or {}).get("signal"))
        self.calls.append({"prompt": prompt, "turn_options": turn_options, "stream": stream})
        self.streams.append(stream)
        return stream


async def _next_provider_message(provider: CodexProvider, *, kind: str | None = None) -> dict[str, Any]:
    for _ in range(20):
        msg = await asyncio.wait_for(provider._queue.get(), timeout=1)  # noqa: SLF001
        if kind is None or msg.get("kind") == kind:
            return msg
    raise AssertionError(f"provider did not emit kind={kind!r}")


async def _wait_for_calls(thread: RecordingThread, count: int) -> None:
    for _ in range(20):
        if len(thread.calls) >= count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"expected {count} run_streamed calls, got {len(thread.calls)}")


@pytest.mark.asyncio
async def test_codex_second_prompt_aborts_running_turn_and_starts_next_turn() -> None:
    pytest.importorskip("openai_codex_sdk.abort")

    provider = CodexProvider({"cwd": "."})
    thread = RecordingThread()
    provider._connected = True  # noqa: SLF001
    provider._codex = object()  # noqa: SLF001
    provider._thread = thread  # noqa: SLF001

    await provider.send_prompt("first long turn")
    await _wait_for_calls(thread, 1)
    first_signal = thread.calls[0]["turn_options"]["signal"]
    assert first_signal.aborted is False

    await provider.send_prompt("second steering turn")
    await _wait_for_calls(thread, 2)

    first_complete = await _next_provider_message(provider, kind="complete")
    assert first_complete == {
        "kind": "complete",
        "sessionId": "codex-thread",
        "aborted": True,
    }
    assert first_signal.aborted is True
    assert first_signal.reason == "user sent a new Codex prompt"
    assert [call["prompt"] for call in thread.calls] == ["first long turn", "second steering turn"]

    second_signal = thread.calls[1]["turn_options"]["signal"]
    assert second_signal.aborted is False

    await provider.disconnect()


@pytest.mark.asyncio
async def test_codex_second_prompt_after_complete_does_not_abort_previous_turn() -> None:
    pytest.importorskip("openai_codex_sdk.abort")

    provider = CodexProvider({"cwd": "."})
    thread = DelayedCompleteThread()
    provider._connected = True  # noqa: SLF001
    provider._codex = object()  # noqa: SLF001
    provider._thread = thread  # noqa: SLF001

    await provider.send_prompt("first completed turn")
    first_complete = await _next_provider_message(provider, kind="complete")
    assert first_complete == {
        "kind": "complete",
        "sessionId": "codex-thread",
        "exitCode": 0,
    }
    first_signal = thread.calls[0]["turn_options"]["signal"]
    assert first_signal.aborted is False

    await provider.send_prompt("second turn after result")
    await _wait_for_calls(thread, 2)

    assert first_signal.aborted is False
    assert [call["prompt"] for call in thread.calls] == ["first completed turn", "second turn after result"]

    await provider.disconnect()


@pytest.mark.asyncio
async def test_codex_interrupt_aborts_running_turn() -> None:
    pytest.importorskip("openai_codex_sdk.abort")

    provider = CodexProvider({"cwd": "."})
    thread = RecordingThread()
    provider._connected = True  # noqa: SLF001
    provider._codex = object()  # noqa: SLF001
    provider._thread = thread  # noqa: SLF001

    await provider.send_prompt("running turn")
    await _wait_for_calls(thread, 1)
    signal = thread.calls[0]["turn_options"]["signal"]

    await provider.interrupt()
    complete = await _next_provider_message(provider, kind="complete")

    assert complete == {
        "kind": "complete",
        "sessionId": "codex-thread",
        "aborted": True,
    }
    assert signal.aborted is True
    assert signal.reason == "user interrupted Codex"

    await provider.disconnect()


@pytest.mark.asyncio
async def test_codex_first_event_wait_emits_heartbeat_without_abort(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("openai_codex_sdk.abort")
    monkeypatch.setattr(codex_module, "CODEX_EVENT_HEARTBEAT_SEC", 0.01)
    monkeypatch.setattr(codex_module, "CODEX_IDLE_HARD_TIMEOUT_SEC", 0)

    provider = CodexProvider({"cwd": "."})
    thread = RecordingThread()
    provider._connected = True  # noqa: SLF001
    provider._codex = object()  # noqa: SLF001
    provider._thread = thread  # noqa: SLF001

    await provider.send_prompt("long silent turn")
    await _wait_for_calls(thread, 1)
    signal = thread.calls[0]["turn_options"]["signal"]

    heartbeat = await _next_provider_message(provider, kind="status")
    while heartbeat.get("text") != "codex_waiting_for_first_event":
        heartbeat = await _next_provider_message(provider, kind="status")

    assert signal.aborted is False
    await provider.disconnect()
