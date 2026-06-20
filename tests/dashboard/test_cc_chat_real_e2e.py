from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import aiohttp
import pytest
import websockets


RUN_REAL_E2E = os.environ.get("OMNI_RUN_REAL_CC_E2E") == "1"
DASHBOARD = os.environ.get("OMNI_DASHBOARD_URL", "http://127.0.0.1:8210").rstrip("/")
REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = REPO_ROOT / "_scratch" / "e2e_real"
GUIDANCE_MARKER = "OMNI_E2E_GUIDANCE_SEEN"


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.skipif(
        not RUN_REAL_E2E,
        reason="set OMNI_RUN_REAL_CC_E2E=1 to run the real dashboard E2E",
    ),
]


def _ws_base() -> str:
    if DASHBOARD.startswith("https://"):
        return "wss://" + DASHBOARD[len("https://") :]
    if DASHBOARD.startswith("http://"):
        return "ws://" + DASHBOARD[len("http://") :]
    raise AssertionError(f"unsupported dashboard URL: {DASHBOARD}")


def _frame_text(frame: dict[str, Any]) -> str:
    parts: list[str] = []
    content = frame.get("content")
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            for key in ("text", "thinking", "content"):
                value = block.get(key)
                if isinstance(value, str):
                    parts.append(value)
    for key in ("message", "error", "summary"):
        value = frame.get(key)
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


def _has_tool_use(frame: dict[str, Any]) -> bool:
    content = frame.get("content")
    return isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "tool_use"
        for block in content
    )


def _has_bash_tool_use(frame: dict[str, Any]) -> bool:
    content = frame.get("content")
    if not isinstance(content, list):
        return False
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name = str(block.get("name", "")).lower()
        if name == "bash":
            return True
    return False


async def _recv_frame(ws: Any, frames: list[dict[str, Any]], artifact: Path, label: str) -> dict[str, Any]:
    raw = await ws.recv()
    try:
        frame = json.loads(raw)
    except Exception:
        frame = {"kind": "non_json", "raw": raw}
    frames.append(frame)
    with artifact.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"label": label, "ts": time.time(), "frame": frame}, ensure_ascii=False) + "\n")
    kind = frame.get("kind")
    text = _frame_text(frame).replace("\n", " ")[:140]
    print(
        f"[real-e2e] {label}: kind={kind!r} "
        f"tool_use={_has_tool_use(frame)} bash={_has_bash_tool_use(frame)} text={text!r}"
    )
    return frame


async def _recv_until(
    ws: Any,
    frames: list[dict[str, Any]],
    artifact: Path,
    *,
    label: str,
    timeout: float,
    predicate: Any,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = max(0.1, deadline - time.monotonic())
        try:
            frame = await asyncio.wait_for(_recv_frame(ws, frames, artifact, label), timeout=min(3.0, remaining))
        except asyncio.TimeoutError:
            continue
        if predicate(frame):
            return frame
    return None


async def _create_session(http: aiohttp.ClientSession, *, provider: str = "claude_code") -> str:
    async with http.post(
        f"{DASHBOARD}/api/cc/chat/sessions",
        json={"provider": provider, "cwd": str(REPO_ROOT)},
    ) as response:
        body = await response.text()
        assert response.status == 200, f"create session failed: {response.status} {body}"
        data = json.loads(body)
        assert data.get("id"), f"create session response missing id: {data}"
        return data["id"]


async def _delete_session(http: aiohttp.ClientSession, sid: str) -> None:
    try:
        async with http.delete(f"{DASHBOARD}/api/cc/chat/sessions/{sid}") as response:
            await response.text()
    except Exception:
        pass


async def test_real_claude_midturn_guidance_uses_same_origin_ws() -> None:
    """Real dashboard E2E: same-origin API, real Claude Code, mid-turn guidance."""

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    artifact = ARTIFACT_DIR / f"claude_midturn_{stamp}.jsonl"
    frames: list[dict[str, Any]] = []

    first_prompt = (
        "This is an OmniCompany real E2E test. Run exactly this read-only PowerShell command and wait for it: "
        'powershell -NoProfile -Command "Start-Sleep -Seconds 12; Write-Output OMNI_E2E_SLEEP_DONE". '
        "After the command returns, briefly report the output. Do not edit files."
    )
    guidance_prompt = (
        "Mid-turn guidance for the current run: stop expanding the previous answer. "
        f"Reply with exactly `{GUIDANCE_MARKER}` and no other words."
    )

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
        async with http.get(f"{DASHBOARD}/api/cc/chat/health") as response:
            assert response.status == 200, f"dashboard health failed: {response.status} {await response.text()}"

        sid = await _create_session(http)
        print(f"[real-e2e] session={sid} artifact={artifact}")
        try:
            ws_url = f"{_ws_base()}/api/cc/chat/sessions/{sid}/ws"
            async with websockets.connect(ws_url, ping_interval=None, open_timeout=10) as ws:
                snapshot = await _recv_frame(ws, frames, artifact, "snapshot")
                assert snapshot.get("kind") == "snapshot", f"first frame must be snapshot, got {snapshot}"

                await ws.send(json.dumps({
                    "type": "user.message",
                    "content": first_prompt,
                    "permissionMode": "bypassPermissions",
                }))
                print("[real-e2e] sent first prompt")

                tool_frame = await _recv_until(
                    ws,
                    frames,
                    artifact,
                    label="before-guidance",
                    timeout=60,
                    predicate=_has_bash_tool_use,
                )
                assert tool_frame is not None, f"did not observe a real Bash tool_use before guidance; see {artifact}"

                await ws.send(json.dumps({
                    "type": "user.message",
                    "content": guidance_prompt,
                    "permissionMode": "bypassPermissions",
                }))
                guidance_sent_at = len(frames)
                print("[real-e2e] sent mid-turn guidance")

                marker_frame = await _recv_until(
                    ws,
                    frames,
                    artifact,
                    label="after-guidance",
                    timeout=90,
                    predicate=lambda frame: GUIDANCE_MARKER in _frame_text(frame)
                    or GUIDANCE_MARKER in json.dumps(frame, ensure_ascii=False),
                )

                after_guidance = frames[guidance_sent_at:]
                assert after_guidance, f"no frames arrived after guidance was sent; see {artifact}"
                assert marker_frame is not None, (
                    f"did not observe assistant honoring mid-turn guidance marker {GUIDANCE_MARKER}; "
                    f"captured {len(frames)} frames in {artifact}"
                )
        finally:
            await _delete_session(http, sid)


async def test_real_codex_midturn_prompt_aborts_running_turn_on_same_origin_ws() -> None:
    """Real dashboard E2E: same-origin API, real Codex provider, in-flight second prompt."""

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    artifact = ARTIFACT_DIR / f"codex_midturn_{stamp}.jsonl"
    frames: list[dict[str, Any]] = []
    marker = "OMNI_CODEX_MIDTURN_ACCEPTED"
    first_prompt = (
        "This is an OmniCompany real Codex E2E interrupt test. Run exactly this read-only PowerShell "
        "command and wait for it: powershell -NoProfile -Command "
        '"Start-Sleep -Seconds 25; Write-Output OMNI_CODEX_SLEEP_DONE". '
        "After the command returns, briefly report the output. Do not edit files."
    )
    second_prompt = (
        "New user steering prompt while the previous Codex turn is still running: stop the previous wait "
        f"and reply with exactly `{marker}`. Do not run any command."
    )

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
        async with http.get(f"{DASHBOARD}/api/cc/chat/health") as response:
            assert response.status == 200, f"dashboard health failed: {response.status} {await response.text()}"

        sid = await _create_session(http, provider="codex")
        print(f"[real-e2e] codex session={sid} artifact={artifact}")
        try:
            ws_url = f"{_ws_base()}/api/cc/chat/sessions/{sid}/ws"
            async with websockets.connect(ws_url, ping_interval=None, open_timeout=10) as ws:
                snapshot = await _recv_frame(ws, frames, artifact, "codex-snapshot")
                assert snapshot.get("kind") == "snapshot", f"first frame must be snapshot, got {snapshot}"

                await ws.send(json.dumps({
                    "type": "user.message",
                    "content": first_prompt,
                    "permissionMode": "bypassPermissions",
                }))
                print("[real-e2e] sent codex first prompt")

                tool_frame = await _recv_until(
                    ws,
                    frames,
                    artifact,
                    label="codex-before-steer",
                    timeout=90,
                    predicate=_has_bash_tool_use,
                )
                assert tool_frame is not None, f"did not observe Codex Bash tool_use before steering; see {artifact}"
                tool_observed_at = len(frames)

                await ws.send(json.dumps({
                    "type": "user.message",
                    "content": second_prompt,
                    "permissionMode": "bypassPermissions",
                }))
                steer_sent_at = len(frames)
                print("[real-e2e] sent codex mid-turn steering prompt")

                marker_frame = await _recv_until(
                    ws,
                    frames,
                    artifact,
                    label="codex-after-steer",
                    timeout=120,
                    predicate=lambda frame: marker in _frame_text(frame)
                    or marker in json.dumps(frame, ensure_ascii=False),
                )
                after_steer = frames[steer_sent_at:]
                assert after_steer, f"no frames arrived after Codex steering prompt; see {artifact}"
                assert marker_frame is not None, (
                    f"Codex did not honor the in-flight steering marker {marker}; "
                    f"captured {len(frames)} frames in {artifact}"
                )
                assert tool_observed_at <= steer_sent_at < len(frames), (
                    f"steering was not sent after observing a running tool; see {artifact}"
                )
                serialized_after_steer = "\n".join(json.dumps(frame, ensure_ascii=False) for frame in after_steer)
                assert "OMNI_CODEX_SLEEP_DONE" not in serialized_after_steer, (
                    f"original sleep command completed after steering, so the turn was not truly interrupted; see {artifact}"
                )
        finally:
            await _delete_session(http, sid)


# ── Plan binding E2E ───────────────────────────────────────────────────────


async def _patch_plan_via_pty_route(http: aiohttp.ClientSession, sid: str, plan_id: str | None) -> dict:
    """Call the PTY route (same route SessionContextPanel uses) to patch plan."""
    async with http.patch(
        f"{DASHBOARD}/api/cc/sessions/{sid}/active_plan",
        json={"plan_id": plan_id},
    ) as response:
        body = await response.text()
        assert response.status == 200, f"patch_active_plan failed: {response.status} {body}"
        return json.loads(body)


async def test_real_plan_binding_visible_on_next_message() -> None:
    """Real E2E: bind plan via PTY route (SessionContextPanel path) → next chat message sees it.

    This is the core fix validation: the user switches a plan in the SessionContextPanel,
    then sends a message, and the LLM context includes the plan info.
    """
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    artifact = ARTIFACT_DIR / f"plan_binding_{stamp}.jsonl"
    frames: list[dict[str, Any]] = []

    # Use a real plan that exists in the repo
    plans_dir = REPO_ROOT / "docs" / "plans"
    # Find any existing plan dir
    candidate_plan: str | None = None
    for subdir in plans_dir.rglob("plan.md"):
        rel = subdir.parent.relative_to(plans_dir)
        candidate_plan = str(rel).replace("\\", "/")
        break
    assert candidate_plan, "no plan.md found in docs/plans/ — cannot run this test"

    plan_marker = candidate_plan.split("/")[-1]  # last segment for assertion

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
        async with http.get(f"{DASHBOARD}/api/cc/chat/health") as response:
            assert response.status == 200

        sid = await _create_session(http)
        print(f"[real-e2e] plan-binding session={sid} plan={candidate_plan}")
        try:
            # Step 1: Bind plan via the PTY route (same path as SessionContextPanel)
            patch_resp = await _patch_plan_via_pty_route(http, sid, candidate_plan)
            assert patch_resp.get("active_plan") == candidate_plan
            print(f"[real-e2e] plan bound: alive={patch_resp.get('alive')}")

            # Step 2: Send a message and check the LLM actually receives plan context
            ws_url = f"{_ws_base()}/api/cc/chat/sessions/{sid}/ws"
            async with websockets.connect(ws_url, ping_interval=None, open_timeout=10) as ws:
                snapshot = await _recv_frame(ws, frames, artifact, "snapshot")
                assert snapshot.get("kind") == "snapshot"

                # Ask claude to echo back what plan it sees
                test_prompt = (
                    "This is an automated E2E plan binding test. "
                    "Simply reply with the exact active plan id you see in your context. "
                    "If you see no plan, reply 'NO_PLAN_VISIBLE'. Do not use tools."
                )
                await ws.send(json.dumps({
                    "type": "user.message",
                    "content": test_prompt,
                    "permissionMode": "bypassPermissions",
                }))
                print("[real-e2e] sent plan probe prompt")

                # Wait for a response containing the plan marker
                result_frame = await _recv_until(
                    ws, frames, artifact,
                    label="plan-response",
                    timeout=60,
                    predicate=lambda f: f.get("kind") in ("result", "complete")
                    or plan_marker in _frame_text(f),
                )

                all_text = " ".join(_frame_text(f) for f in frames)
                assert "NO_PLAN_VISIBLE" not in all_text, (
                    f"Claude reported no plan visible after binding! See {artifact}"
                )
                assert plan_marker in all_text or candidate_plan in all_text, (
                    f"Claude's response doesn't reference the bound plan '{candidate_plan}'; "
                    f"see {artifact}"
                )
                print(f"[real-e2e] plan binding verified: plan marker found in response")
        finally:
            await _delete_session(http, sid)


async def test_real_plan_switch_midconversation() -> None:
    """Real E2E: start with no plan → switch plan → next message sees 'plan switched'."""
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    artifact = ARTIFACT_DIR / f"plan_switch_{stamp}.jsonl"
    frames: list[dict[str, Any]] = []

    plans_dir = REPO_ROOT / "docs" / "plans"
    candidate_plan: str | None = None
    for subdir in plans_dir.rglob("plan.md"):
        rel = subdir.parent.relative_to(plans_dir)
        candidate_plan = str(rel).replace("\\", "/")
        break
    assert candidate_plan

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
        async with http.get(f"{DASHBOARD}/api/cc/chat/health") as response:
            assert response.status == 200

        sid = await _create_session(http)
        print(f"[real-e2e] plan-switch session={sid}")
        try:
            ws_url = f"{_ws_base()}/api/cc/chat/sessions/{sid}/ws"
            async with websockets.connect(ws_url, ping_interval=None, open_timeout=10) as ws:
                snapshot = await _recv_frame(ws, frames, artifact, "snapshot")
                assert snapshot.get("kind") == "snapshot"

                # Turn 1: no plan yet
                await ws.send(json.dumps({
                    "type": "user.message",
                    "content": "E2E test turn 1. Reply briefly: do you see any active plan in your context? yes/no only.",
                    "permissionMode": "bypassPermissions",
                }))
                turn1_done = await _recv_until(
                    ws, frames, artifact, label="turn1",
                    timeout=60,
                    predicate=lambda f: f.get("kind") in ("result", "complete"),
                )
                assert turn1_done is not None, f"turn 1 did not complete; see {artifact}"

                # Switch plan mid-conversation
                await _patch_plan_via_pty_route(http, sid, candidate_plan)
                print(f"[real-e2e] plan switched to {candidate_plan}")

                # Turn 2: should see the plan
                await ws.send(json.dumps({
                    "type": "user.message",
                    "content": (
                        "E2E test turn 2 (after plan switch). "
                        "Reply with the active plan id from your context. "
                        "If no plan visible, reply 'NO_PLAN_VISIBLE'."
                    ),
                    "permissionMode": "bypassPermissions",
                }))
                turn2_done = await _recv_until(
                    ws, frames, artifact, label="turn2",
                    timeout=60,
                    predicate=lambda f: f.get("kind") in ("result", "complete"),
                )
                assert turn2_done is not None, f"turn 2 did not complete; see {artifact}"

                # Check turn 2 response references the plan
                turn2_text = " ".join(
                    _frame_text(f) for f in frames
                    if frames.index(f) > frames.index(turn1_done)
                )
                plan_marker = candidate_plan.split("/")[-1]
                assert "NO_PLAN_VISIBLE" not in turn2_text, (
                    f"plan switch not visible to LLM on turn 2; see {artifact}"
                )
                assert plan_marker in turn2_text or candidate_plan in turn2_text, (
                    f"turn 2 response doesn't reference switched plan; see {artifact}"
                )
                print("[real-e2e] plan switch mid-conversation verified")
        finally:
            await _delete_session(http, sid)
