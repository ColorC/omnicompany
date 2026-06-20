from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from pathlib import Path
from typing import Any

import aiohttp
import pytest


RUN_REAL_E2E = os.environ.get("OMNI_RUN_REAL_CC_E2E") == "1"
DASHBOARD = os.environ.get("OMNI_DASHBOARD_URL", "http://127.0.0.1:8210").rstrip("/")
REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = REPO_ROOT / "_scratch" / "e2e_real"


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not RUN_REAL_E2E,
        reason="set OMNI_RUN_REAL_CC_E2E=1 to run the real dashboard UI observer",
    ),
]


async def _create_session() -> str:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as http:
        async with http.post(
            f"{DASHBOARD}/api/cc/chat/sessions",
            json={"provider": "claude_code", "cwd": str(REPO_ROOT)},
        ) as response:
            body = await response.text()
            assert response.status == 200, f"create session failed: {response.status} {body}"
            data = json.loads(body)
            return data["id"]


async def _delete_session(sid: str) -> None:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as http:
        try:
            async with http.delete(f"{DASHBOARD}/api/cc/chat/sessions/{sid}") as response:
                await response.text()
        except Exception:
            pass


def _layout_url(sid: str) -> str:
    layout = {
        "tabs": [{"type": "cc_session", "id": sid, "title": f"long-observer {sid[-6:]}"}],
        "active": f"cc_session:{sid}",
    }
    encoded = base64.b64encode(json.dumps(layout).encode("utf-8")).decode("ascii")
    return f"{DASHBOARD}/?layout={encoded}"


async def _install_ws_observer(page: Any) -> None:
    await page.add_init_script(
        """
(() => {
  const originalWS = window.WebSocket;
  window.__omniLongObserver = window.__omniLongObserver || {
    ws: [],
    dom: [],
    fetches: [],
    console: [],
  };
  window.WebSocket = class OmniObservedWebSocket extends originalWS {
    constructor(url, protocols) {
      super(url, protocols);
      const rec = { url: String(url), openedAt: Date.now(), sent: [], received: [] };
      window.__omniLongObserver.ws.push(rec);
      this.addEventListener('message', (event) => {
        let data = event.data;
        try { data = JSON.parse(event.data); } catch {}
        rec.received.push({ at: Date.now(), data });
      });
      const send = this.send.bind(this);
      this.send = (data) => {
        let payload = data;
        try { payload = JSON.parse(data); } catch {}
        rec.sent.push({ at: Date.now(), data: payload });
        return send(data);
      };
    }
  };
  Object.assign(window.WebSocket, originalWS);

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const url = String(args[0]?.url || args[0]);
    const startedAt = Date.now();
    const response = await originalFetch(...args);
    if (url.includes('/api/providers/sessions/') || url.includes('/api/cc/chat/')) {
      const clone = response.clone();
      let body = '';
      try { body = await clone.text(); } catch {}
      window.__omniLongObserver.fetches.push({
        at: startedAt,
        url,
        status: response.status,
        body: body.slice(0, 20000),
      });
    }
    return response;
  };
})();
        """
    )


async def _install_dom_observer(page: Any, sid: str) -> None:
    await page.evaluate(
        """
(sid) => {
  const obs = window.__omniLongObserver;
  const rootSelector = `[data-cc-chat-session-id="${sid}"]`;
  function snapshot(reason) {
    const root = document.querySelector(rootSelector);
    const pane = root?.querySelector('[data-cc-messages]');
    const rows = pane ? Array.from(pane.querySelectorAll('.chat-message')).map((node, index) => {
      const el = node;
      return {
        index,
        className: el.className,
        text: (el.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 1200),
        detailsCount: el.querySelectorAll('details').length,
        openDetailsCount: Array.from(el.querySelectorAll('details')).filter((d) => d.open).length,
        codeCount: el.querySelectorAll('code, pre').length,
      };
    }) : [];
    obs.dom.push({
      at: Date.now(),
      reason,
      rowCount: rows.length,
      detailsCount: rows.reduce((sum, row) => sum + row.detailsCount, 0),
      userTexts: rows.filter((row) => String(row.className).includes('user')).map((row) => row.text),
      toolRows: rows.filter((row) => {
        if (String(row.className).includes('user')) return false;
        return row.detailsCount > 0 || /\\b(Bash|PowerShell|Edit|Write|Read|Tool)\\b/i.test(row.text);
      }).map((row) => ({
        index: row.index,
        text: row.text,
        detailsCount: row.detailsCount,
      })),
      rows,
    });
  }
  window.__omniTakeSnapshot = snapshot;
  const wait = () => {
    const root = document.querySelector(rootSelector);
    const pane = root?.querySelector('[data-cc-messages]');
    if (!pane) {
      setTimeout(wait, 100);
      return;
    }
    snapshot('observer-start');
    new MutationObserver(() => snapshot('mutation')).observe(pane, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ['open', 'class'],
    });
    window.__omniSampler = setInterval(() => snapshot('interval'), 500);
  };
  wait();
}
        """,
        sid,
    )


async def _dump_artifact(page: Any, artifact: Path, label: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
    await page.evaluate("(label) => window.__omniTakeSnapshot && window.__omniTakeSnapshot(label)", label)
    data = await page.evaluate("window.__omniLongObserver")
    segments.append({"label": label, "at": time.time(), "data": data})
    artifact.write_text(json.dumps({"segments": segments}, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


async def _send_prompt(
    page: Any,
    sid: str,
    prompt: str,
    expected: str,
    turn: int,
    artifact: Path,
    screenshot: Path,
    segments: list[dict[str, Any]],
) -> None:
    tab = page.locator(f'[data-cc-chat-session-id="{sid}"]')
    await tab.locator("[data-cc-input]").fill(prompt)
    await tab.locator("[data-cc-send]").click()
    try:
        await tab.locator(".chat-message.assistant").filter(has_text=expected).wait_for(timeout=120_000)
        await page.wait_for_function(
            """
([turn]) => {
  const obs = window.__omniLongObserver;
  const recv = (obs?.ws || []).flatMap((w) => w.received || []);
  const bashUses = recv.filter((entry) => JSON.stringify(entry.data).includes('"name":"Bash"')).length;
  return bashUses >= turn;
}
            """,
            arg=[turn],
            timeout=120_000,
        )
    except Exception:
        await _dump_artifact(page, artifact, f"failure-waiting-for-{expected}", segments)
        await page.screenshot(path=str(screenshot), full_page=True)
        raise
    await _dump_artifact(page, artifact, f"after-{expected}", segments)


def _latest_dom(data: dict[str, Any]) -> dict[str, Any]:
    dom = data.get("dom") or []
    return dom[-1] if dom else {}


def _assert_user_messages_intact(data: dict[str, Any], expected_prompts: list[str], artifact: Path) -> None:
    latest = _latest_dom(data)
    user_texts = latest.get("userTexts") or []
    joined = "\n".join(user_texts)
    for prompt in expected_prompts:
        assert prompt in joined, (
            f"user message missing or mutated: {prompt!r}; latest user texts={user_texts!r}; artifact={artifact}"
        )
        assert joined.count(prompt) == 1, (
            f"user message duplicated: {prompt!r}; latest user texts={user_texts!r}; artifact={artifact}"
        )


def _assert_tools_survive(data: dict[str, Any], min_tools: int, artifact: Path) -> None:
    latest = _latest_dom(data)
    tool_rows = latest.get("toolRows") or []
    details_count = int(latest.get("detailsCount") or 0)
    assert details_count >= min_tools or len(tool_rows) >= min_tools, (
        f"tool panels disappeared or were not rendered; tool_rows={tool_rows!r}; "
        f"details_count={details_count}; artifact={artifact}"
    )


def _all_sent_frames(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ws in data.get("ws") or []:
        for entry in ws.get("sent") or []:
            payload = entry.get("data")
            if isinstance(payload, dict):
                out.append(payload)
    return out


async def _wait_for_ws_text(page: Any, text: str, timeout: int = 120_000) -> None:
    await page.wait_for_function(
        """
(text) => {
  const obs = window.__omniLongObserver;
  const recv = (obs?.ws || []).flatMap((w) => w.received || []);
  return recv.some((entry) => JSON.stringify(entry.data).includes(text));
}
        """,
        arg=text,
        timeout=timeout,
    )


@pytest.mark.asyncio
async def test_real_ui_long_run_records_dom_diffs_and_preserves_messages_and_tools() -> None:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"playwright not installed: {exc}")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    artifact = ARTIFACT_DIR / f"ui_long_observer_{stamp}.json"
    screenshot = ARTIFACT_DIR / f"ui_long_observer_{stamp}.png"
    sid = await _create_session()
    prompts: list[str] = []
    segments: list[dict[str, Any]] = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 920})
            page.on("console", lambda msg: print(f"[browser:{msg.type}] {msg.text}"))
            await _install_ws_observer(page)
            await page.add_init_script(
                f"""
(() => {{
  const sid = {json.dumps(sid)};
  localStorage.setItem('selected-provider', 'claude');
  localStorage.setItem(`permissionMode-${{sid}}`, 'bypassPermissions');
}})();
                """
            )
            await page.goto(_layout_url(sid), wait_until="domcontentloaded")
            await page.locator(f'[data-cc-chat-session-id="{sid}"]').wait_for(timeout=20_000)
            await page.locator(f'[data-cc-chat-session-id="{sid}"] [data-cc-messages]').wait_for(timeout=20_000)
            await _install_dom_observer(page, sid)

            for turn in range(1, 4):
                prompt = (
                    f"OMNI_USER_TURN_{turn}: You must use the Bash tool exactly once. "
                    f"Run this read-only command: powershell -NoProfile -Command "
                    f"\"Write-Output OMNI_TOOL_TURN_{turn}\". After the tool returns, "
                    f"reply with exactly OMNI_REPLY_TURN_{turn}. Do not edit files."
                )
                prompts.append(prompt)
                await _send_prompt(page, sid, prompt, f"OMNI_REPLY_TURN_{turn}", turn, artifact, screenshot, segments)
                data = await _dump_artifact(page, artifact, f"post-turn-{turn}-stable", segments)
                _assert_user_messages_intact(data, prompts, artifact)
                _assert_tools_survive(data, turn, artifact)

            await page.reload(wait_until="domcontentloaded")
            await page.locator(f'[data-cc-chat-session-id="{sid}"] [data-cc-messages]').wait_for(timeout=20_000)
            await _install_dom_observer(page, sid)
            await page.wait_for_timeout(5_000)
            data = await _dump_artifact(page, artifact, "after-page-reload", segments)
            await page.screenshot(path=str(screenshot), full_page=True)
            _assert_user_messages_intact(data, prompts, artifact)
            _assert_tools_survive(data, 3, artifact)
            await browser.close()
    finally:
        await _delete_session(sid)


@pytest.mark.asyncio
async def test_real_ui_midturn_guidance_changes_current_claude_turn() -> None:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"playwright not installed: {exc}")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    artifact = ARTIFACT_DIR / f"ui_midturn_guidance_{stamp}.json"
    screenshot = ARTIFACT_DIR / f"ui_midturn_guidance_{stamp}.png"
    sid = await _create_session()
    segments: list[dict[str, Any]] = []
    guidance_marker = "ui-midturn-guidance-accepted"
    page: Any | None = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 920})
            page.on("console", lambda msg: print(f"[browser:{msg.type}] {msg.text}"))
            await _install_ws_observer(page)
            await page.add_init_script(
                f"""
(() => {{
  const sid = {json.dumps(sid)};
  localStorage.setItem('selected-provider', 'claude');
  localStorage.setItem(`permissionMode-${{sid}}`, 'bypassPermissions');
}})();
                """
            )
            await page.goto(_layout_url(sid), wait_until="domcontentloaded")
            await page.locator(f'[data-cc-chat-session-id="{sid}"] [data-cc-messages]').wait_for(timeout=20_000)
            await _install_dom_observer(page, sid)

            tab = page.locator(f'[data-cc-chat-session-id="{sid}"]')
            first_prompt = (
                "For a dashboard latency check, please run exactly this read-only PowerShell command and wait "
                "for it: powershell -NoProfile -Command "
                "\"Start-Sleep -Seconds 10; Write-Output ui-midturn-tool-done\". "
                "After the command returns, briefly report the output."
            )
            guidance_prompt = (
                "Mid-run note from the user: after the command completes, please also include the phrase "
                f"`{guidance_marker}` in your final response."
            )

            await tab.locator("[data-cc-input]").fill(first_prompt)
            await tab.locator("[data-cc-send]").click()
            await tab.locator("[data-cc-interrupt]").wait_for(timeout=10_000)
            await _wait_for_ws_text(page, "ui-midturn-tool-done", timeout=120_000)

            await tab.locator("[data-cc-input]").fill(guidance_prompt)
            await tab.locator("[data-cc-send]").click()
            await _wait_for_ws_text(page, guidance_marker, timeout=120_000)
            await tab.locator(".chat-message.assistant").filter(has_text=guidance_marker).first.wait_for(timeout=30_000)

            data = await _dump_artifact(page, artifact, "after-midturn-guidance", segments)
            await page.screenshot(path=str(screenshot), full_page=True)
            sent = _all_sent_frames(data)
            user_sends = [f for f in sent if f.get("type") == "user.message"]
            assert len(user_sends) >= 2, f"expected two UI user.message sends; sent={sent!r}; artifact={artifact}"
            assert user_sends[0].get("content") == first_prompt, (
                f"first prompt missing or mutated in sent frame; sent={sent!r}; artifact={artifact}"
            )
            assert user_sends[1].get("content") == guidance_prompt, (
                f"mid-turn guidance missing or mutated in sent frame; sent={sent!r}; artifact={artifact}"
            )
            assert all(f.get("permissionMode") == "bypassPermissions" for f in user_sends[:2]), (
                f"UI did not pass bypass permission mode; sent={sent!r}; artifact={artifact}"
            )
            receive_entries = [
                entry
                for ws in data.get("ws") or []
                for entry in ws.get("received") or []
                if isinstance(entry, dict)
            ]
            second_sent_at = next(
                (
                    entry.get("at")
                    for ws in data.get("ws") or []
                    for entry in ws.get("sent") or []
                    if isinstance(entry.get("data"), dict)
                    and guidance_prompt in json.dumps(entry.get("data"), ensure_ascii=False)
                ),
                None,
            )
            tool_marker_at = next(
                (
                    entry.get("at")
                    for entry in receive_entries
                    if "ui-midturn-tool-done" in json.dumps(entry.get("data"), ensure_ascii=False)
                ),
                None,
            )
            guidance_seen_at = next(
                (
                    entry.get("at")
                    for entry in receive_entries
                    if guidance_marker in json.dumps(entry.get("data"), ensure_ascii=False)
                ),
                None,
            )
            assert (
                tool_marker_at is not None
                and second_sent_at is not None
                and guidance_seen_at is not None
                and tool_marker_at <= second_sent_at < guidance_seen_at
            ), (
                f"guidance was not sent as an in-flight steering event; tool_marker_at={tool_marker_at}, "
                f"second_sent_at={second_sent_at}, guidance_seen_at={guidance_seen_at}; artifact={artifact}"
            )
            assert guidance_marker in json.dumps(data, ensure_ascii=False), (
                f"assistant did not honor mid-turn guidance marker; artifact={artifact}"
            )
            await browser.close()
    except Exception:
        try:
            if page is not None:
                await _dump_artifact(page, artifact, "failure-midturn-guidance", segments)
                await page.screenshot(path=str(screenshot), full_page=True)
        except Exception:
            pass
        raise
    finally:
        await _delete_session(sid)
