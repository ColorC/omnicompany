# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=dogfood-live-display
"""headed dogfood — 看用户真实浏览体验. 发消息后 2 秒检查 chat-message 数, 不刷新.
确认: 流式显示 (stream_delta) 跟 finalize 是不是真显示."""
import time, json
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8210/chat-standalone"

with sync_playwright() as p:
    b = p.chromium.launch(headless=False, slow_mo=200)
    page = b.new_context(viewport={"width": 1200, "height": 900}).new_page()
    page.on('console', lambda m: print(f"[CONSOLE {m.type}] {m.text[:300]}") if m.type in ('error', 'warning') else None)
    page.on('pageerror', lambda e: print(f"[PAGEERROR] {e}"))

    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    # 切到 codex provider 后再 + 新 session
    page.select_option('[data-testid="chat-standalone-provider-select"]', 'codex')
    page.wait_for_timeout(500)
    page.click('[data-testid="chat-standalone-new-session"]')
    page.wait_for_timeout(3500)

    def snap(label):
        ts = page.evaluate("""() => Array.from(document.querySelectorAll('.chat-message')).map(m => ({
            role: m.className.includes('user') ? 'user' : m.className.includes('assistant') ? 'assistant' : '?',
            text: (m.textContent || '').trim().slice(0, 80),
        }))""")
        print(f"\n--- {label}, {len(ts)} msgs ---")
        for m in ts: print(f"  [{m['role']}] {m['text']!r}")
        return ts

    # 多轮发, 每轮发完后立即记 + 5 秒后再记, 看后续轮是不是不直接显示
    for i, q in enumerate(["hi", "1+1=?", "讲一句话总结"], 1):
        print(f"\n===== turn {i}: {q} =====")
        page.locator('textarea').first.fill(q)
        page.locator('textarea').first.press("Control+Enter")
        page.wait_for_timeout(500)
        snap(f"turn{i} t+0.5s")
        page.wait_for_timeout(3000)
        snap(f"turn{i} t+3.5s")
        page.wait_for_timeout(5000)
        snap(f"turn{i} t+8.5s")

    print("\n--- 等 5 秒 ---")
    page.wait_for_timeout(5_000)
    b.close()
