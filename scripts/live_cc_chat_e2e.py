from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
import websockets


@dataclass
class TurnResult:
    label: str
    expected: str
    text: str
    first_text_seconds: float | None
    total_seconds: float


def ws_url_for(base_url: str, session_id: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/api/cc/chat/sessions/{session_id}/ws"


def provider_tag(provider: str) -> str:
    return provider.upper().replace("-", "_")


def extract_text(frame: dict[str, Any]) -> str:
    if frame.get("kind") == "assistant":
        out: list[str] = []
        for block in frame.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                out.append(str(block.get("text") or ""))
        return "".join(out)
    if frame.get("kind") == "stream_event":
        event = frame.get("event") or {}
        delta = event.get("delta") or {}
        if event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
            return str(delta.get("text") or "")
    return ""


async def recv_json(ws: websockets.WebSocketClientProtocol, timeout_seconds: float) -> dict[str, Any]:
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout_seconds)
    return json.loads(raw)


async def create_session(
    client: httpx.AsyncClient,
    base_url: str,
    provider: str,
    cwd: str,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"provider": provider, "cwd": cwd}
    if model:
        body["model"] = model
    response = await client.post(
        f"{base_url}/api/cc/chat/sessions",
        json=body,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


async def delete_session(client: httpx.AsyncClient, base_url: str, session_id: str) -> None:
    try:
        await client.delete(f"{base_url}/api/cc/chat/sessions/{session_id}", timeout=30)
    except Exception:
        pass


async def patch_metadata(
    client: httpx.AsyncClient,
    base_url: str,
    session_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    response = await client.patch(
        f"{base_url}/api/cc/chat/sessions/{session_id}/metadata",
        json=body,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


async def fetch_session_meta(
    client: httpx.AsyncClient,
    base_url: str,
    session_id: str,
) -> dict[str, Any]:
    response = await client.get(
        f"{base_url}/api/cc/chat/sessions",
        params={"pinned_id": session_id, "include_archived": "true"},
        timeout=60,
    )
    response.raise_for_status()
    for item in response.json().get("items") or []:
        if item.get("id") == session_id:
            return item
    raise AssertionError(f"session {session_id} missing from list response")


async def fetch_history(client: httpx.AsyncClient, base_url: str, session_id: str) -> list[dict[str, Any]]:
    response = await client.get(f"{base_url}/api/cc/chat/sessions/{session_id}/history", timeout=60)
    response.raise_for_status()
    data = response.json()
    return list(data.get("messages") or [])


async def wait_initial_snapshot(ws: websockets.WebSocketClientProtocol) -> None:
    frame = await recv_json(ws, 30)
    if frame.get("kind") != "snapshot":
        raise AssertionError(f"expected initial snapshot, got {frame}")


async def run_marker_turn(
    ws: websockets.WebSocketClientProtocol,
    provider: str,
    run_id: str,
    label: str,
    timeout_seconds: float,
    *,
    permission_mode: str | None = "bypassPermissions",
) -> TurnResult:
    expected = f"OMNI_E2E_{provider_tag(provider)}_{run_id}_{label}"
    prompt = (
        "E2E ordering test. Do not use tools. "
        f"Reply with exactly this single line and nothing else: {expected}"
    )
    started = time.perf_counter()
    first_text_at: float | None = None
    chunks: list[str] = []

    frame: dict[str, Any] = {
        "type": "user.message",
        "content": prompt,
    }
    if permission_mode is not None:
        frame["permissionMode"] = permission_mode
    await ws.send(json.dumps(frame))

    while True:
        incoming = await recv_json(ws, timeout_seconds)
        kind = incoming.get("kind")
        text = extract_text(incoming)
        if text:
            if first_text_at is None:
                first_text_at = time.perf_counter()
            chunks.append(text)
        if kind == "error":
            raise AssertionError(f"{provider} turn {label} error frame: {incoming}")
        if kind == "result":
            if incoming.get("is_error"):
                raise AssertionError(f"{provider} turn {label} result error: {incoming}")
            break

    ended = time.perf_counter()
    full_text = "".join(chunks)
    if expected not in full_text:
        raise AssertionError(
            f"{provider} turn {label} missing expected marker {expected!r}; got {full_text!r}"
        )
    return TurnResult(
        label=label,
        expected=expected,
        text=full_text,
        first_text_seconds=None if first_text_at is None else first_text_at - started,
        total_seconds=ended - started,
    )


def verify_history_order(provider: str, messages: list[dict[str, Any]], results: list[TurnResult]) -> None:
    text_messages = [
        msg for msg in messages
        if msg.get("kind") == "text" and str(msg.get("content") or "").strip()
    ]
    cursor = 0
    for result in results:
        found = False
        while cursor < len(text_messages):
            content = str(text_messages[cursor].get("content") or "")
            cursor += 1
            if result.expected in content:
                found = True
                break
        if not found:
            raise AssertionError(f"{provider} history is missing ordered marker {result.expected}")


async def wait_for_status(
    ws: websockets.WebSocketClientProtocol,
    expected_text: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.perf_counter() + timeout_seconds
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise AssertionError(f"timed out waiting for status {expected_text!r}")
        frame = await recv_json(ws, remaining)
        if frame.get("kind") == "error":
            raise AssertionError(f"error while waiting for status {expected_text!r}: {frame}")
        if frame.get("kind") == "status" and frame.get("text") == expected_text:
            return frame


async def wait_for_result(
    ws: websockets.WebSocketClientProtocol,
    provider: str,
    label: str,
    timeout_seconds: float,
    *,
    allow_error: bool = False,
) -> dict[str, Any]:
    deadline = time.perf_counter() + timeout_seconds
    last_error: dict[str, Any] | None = None
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise AssertionError(f"{provider} {label} timed out waiting for result; last_error={last_error}")
        frame = await recv_json(ws, remaining)
        kind = frame.get("kind")
        if kind == "error":
            if allow_error:
                last_error = frame
                continue
            raise AssertionError(f"{provider} {label} error frame: {frame}")
        if kind == "result":
            if frame.get("is_error") and not allow_error:
                raise AssertionError(f"{provider} {label} result error: {frame}")
            return frame


async def run_long_ordering(
    args: argparse.Namespace,
    client: httpx.AsyncClient,
    provider: str,
    run_id: str,
) -> dict[str, Any]:
    session = await create_session(client, args.base_url, provider, args.cwd)
    session_id = str(session["id"])
    results: list[TurnResult] = []
    try:
        async with websockets.connect(ws_url_for(args.base_url, session_id), open_timeout=30) as ws:
            await wait_initial_snapshot(ws)
            for turn in range(1, args.long_turns + 1):
                label = f"LONG_{turn:02d}"
                results.append(await run_marker_turn(ws, provider, run_id, label, args.timeout_seconds))
        history = await fetch_history(client, args.base_url, session_id)
        verify_history_order(provider, history, results)
    finally:
        if not args.keep_sessions:
            await delete_session(client, args.base_url, session_id)
    return {
        "scenario": "long_ordering",
        "provider": provider,
        "session_id": session_id,
        "turn_count": len(results),
        "turns": [
            {
                "label": r.label,
                "expected": r.expected,
                "first_text_seconds": r.first_text_seconds,
                "total_seconds": r.total_seconds,
            }
            for r in results
        ],
    }


async def run_interrupt_recovery(
    args: argparse.Namespace,
    client: httpx.AsyncClient,
    provider: str,
    run_id: str,
) -> dict[str, Any]:
    session = await create_session(client, args.base_url, provider, args.cwd)
    session_id = str(session["id"])
    try:
        async with websockets.connect(ws_url_for(args.base_url, session_id), open_timeout=30) as ws:
            await wait_initial_snapshot(ws)
            await ws.send(json.dumps({
                "type": "user.message",
                "permissionMode": "bypassPermissions",
                "content": (
                    "E2E interrupt test. Use a shell tool to run this command and then report it: "
                    "powershell -NoProfile -Command \"Start-Sleep -Seconds 20; "
                    f"Write-Output OMNI_E2E_{provider_tag(provider)}_{run_id}_INTERRUPT_SHOULD_NOT_FINISH\". "
                    "If interrupted, do not retry the command."
                ),
            }))
            await asyncio.sleep(args.interrupt_after_seconds)
            await ws.send(json.dumps({"type": "user.interrupt"}))
            interrupted = await wait_for_result(
                ws,
                provider,
                "interrupt",
                args.timeout_seconds,
                allow_error=True,
            )
            recovery = await run_marker_turn(
                ws,
                provider,
                run_id,
                "RECOVERY_AFTER_INTERRUPT",
                args.timeout_seconds,
            )
    finally:
        if not args.keep_sessions:
            await delete_session(client, args.base_url, session_id)
    return {
        "scenario": "interrupt_recovery",
        "provider": provider,
        "session_id": session_id,
        "interrupted_stop_reason": interrupted.get("stop_reason"),
        "interrupted_is_error": interrupted.get("is_error"),
        "recovery_expected": recovery.expected,
        "recovery_total_seconds": recovery.total_seconds,
    }


async def run_permission_switch(
    args: argparse.Namespace,
    client: httpx.AsyncClient,
    provider: str,
    run_id: str,
) -> dict[str, Any]:
    session = await create_session(client, args.base_url, provider, args.cwd)
    session_id = str(session["id"])
    try:
        async with websockets.connect(ws_url_for(args.base_url, session_id), open_timeout=30) as ws:
            await wait_initial_snapshot(ws)
            await ws.send(json.dumps({
                "type": "session.permission_mode",
                "permissionMode": args.switch_permission_mode,
            }))
            ack = await wait_for_status(ws, "permission_mode_updated", 30)
            meta = await fetch_session_meta(client, args.base_url, session_id)
            if meta.get("permission_mode") != args.switch_permission_mode:
                raise AssertionError(f"permission mode was not persisted: {meta}")
            turn = await run_marker_turn(
                ws,
                provider,
                run_id,
                "AFTER_PERMISSION_SWITCH",
                args.timeout_seconds,
                permission_mode=None,
            )
    finally:
        if not args.keep_sessions:
            await delete_session(client, args.base_url, session_id)
    return {
        "scenario": "permission_switch",
        "provider": provider,
        "session_id": session_id,
        "ack_permissionMode": ack.get("permissionMode"),
        "persisted_permission_mode": args.switch_permission_mode,
        "turn_expected": turn.expected,
    }


def model_for_provider(args: argparse.Namespace, provider: str) -> str:
    if provider == "codex":
        return args.codex_switch_model
    return args.claude_switch_model


async def run_model_switch(
    args: argparse.Namespace,
    client: httpx.AsyncClient,
    provider: str,
    run_id: str,
) -> dict[str, Any]:
    next_model = model_for_provider(args, provider)
    session = await create_session(client, args.base_url, provider, args.cwd)
    session_id = str(session["id"])
    results: list[TurnResult] = []
    try:
        async with websockets.connect(ws_url_for(args.base_url, session_id), open_timeout=30) as ws:
            await wait_initial_snapshot(ws)
            results.append(await run_marker_turn(ws, provider, run_id, "BEFORE_MODEL_SWITCH", args.timeout_seconds))
            await ws.send(json.dumps({"type": "session.model", "model": next_model}))
            ack = await wait_for_status(ws, "model_updated", 30)
            meta = await fetch_session_meta(client, args.base_url, session_id)
            if meta.get("model") != next_model:
                raise AssertionError(f"model was not persisted: expected={next_model!r} meta={meta}")
            results.append(await run_marker_turn(ws, provider, run_id, "AFTER_MODEL_SWITCH", args.timeout_seconds))
        history = await fetch_history(client, args.base_url, session_id)
        verify_history_order(provider, history, results)
    finally:
        if not args.keep_sessions:
            await delete_session(client, args.base_url, session_id)
    return {
        "scenario": "model_switch",
        "provider": provider,
        "session_id": session_id,
        "ack_model": ack.get("model"),
        "persisted_model": next_model,
        "turns": [{"label": r.label, "expected": r.expected, "total_seconds": r.total_seconds} for r in results],
    }


async def run_provider(args: argparse.Namespace, provider: str, run_id: str) -> dict[str, Any]:
    selected = {s.strip() for s in args.scenarios.split(",") if s.strip()}
    scenario_fns = {
        "long": run_long_ordering,
        "interrupt": run_interrupt_recovery,
        "permission": run_permission_switch,
        "model": run_model_switch,
    }
    unknown = selected - set(scenario_fns)
    if unknown:
        raise ValueError(f"unknown scenarios: {sorted(unknown)}")

    async with httpx.AsyncClient() as client:
        scenarios: list[dict[str, Any]] = []
        for name, fn in scenario_fns.items():
            if name in selected:
                scenarios.append(await fn(args, client, provider, run_id))
    return {
        "provider": provider,
        "scenarios": scenarios,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Live OmniChat Claude/Codex conversation e2e.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8210")
    parser.add_argument("--cwd", default="/workspace/omnicompany")
    parser.add_argument("--providers", default="claude_code,codex")
    parser.add_argument("--scenarios", default="long,interrupt,permission,model")
    parser.add_argument("--long-turns", type=int, default=12)
    parser.add_argument("--timeout-seconds", type=float, default=240)
    parser.add_argument("--interrupt-after-seconds", type=float, default=3)
    parser.add_argument("--switch-permission-mode", default="bypassPermissions")
    parser.add_argument("--claude-switch-model", default="sonnet")
    parser.add_argument("--codex-switch-model", default="gpt-5.5")
    parser.add_argument("--keep-sessions", action="store_true")
    args = parser.parse_args()

    run_id = uuid.uuid4().hex[:8].upper()
    report = {
        "run_id": run_id,
        "base_url": args.base_url,
        "cwd": args.cwd,
        "scenarios": args.scenarios,
        "long_turns": args.long_turns,
        "providers": [],
    }
    for provider in [p.strip() for p in args.providers.split(",") if p.strip()]:
        report["providers"].append(await run_provider(args, provider, run_id))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
