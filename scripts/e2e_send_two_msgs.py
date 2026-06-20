# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""e2e: 连发两条用户消息, 验都显示出来.

用户 2026-05-12 反馈: 第二条以后消息看不到.
"""
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8210/chat-standalone"

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_context(viewport={"width": 1100, "height": 900}).new_page()

    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    page.click('[data-testid="chat-standalone-new-session"]')
    page.wait_for_timeout(3000)

    # ── 发第一条 ──
    page.locator('textarea').first.fill("first message hello")
    page.locator('textarea').first.press("Control+Enter")
    page.wait_for_function(
        "document.querySelectorAll('.chat-message').length >= 2",
        timeout=60_000,
    )
    page.wait_for_timeout(4000)

    msgs1 = page.evaluate("""
    () => Array.from(document.querySelectorAll('.chat-message')).map((m, i) => ({
      idx: i,
      role: m.className.includes('user') ? 'user' : (m.className.includes('assistant') ? 'assistant' : '?'),
      text: (m.textContent || '').trim().slice(0, 80),
    }))
    """)
    print("=== 第一条发完 chat 列表 ===")
    for m in msgs1:
        print(f"  [{m['idx']}] {m['role']}: {m['text']!r}")
    print(f"用户消息数: {sum(1 for m in msgs1 if m['role'] == 'user')}")

    # ── 发第二条 ──
    page.wait_for_timeout(1000)
    page.locator('textarea').first.fill("second message world")
    page.locator('textarea').first.press("Control+Enter")
    # 等第二个 assistant 出现 (总 4 条: 2 user + 2 assistant)
    try:
        page.wait_for_function(
            "document.querySelectorAll('.chat-message').length >= 4",
            timeout=60_000,
        )
    except Exception as e:
        print(f"WAIT TIMEOUT for 4 msgs: {e}")
    page.wait_for_timeout(4000)

    msgs2 = page.evaluate("""
    () => Array.from(document.querySelectorAll('.chat-message')).map((m, i) => ({
      idx: i,
      role: m.className.includes('user') ? 'user' : (m.className.includes('assistant') ? 'assistant' : '?'),
      text: (m.textContent || '').trim().slice(0, 80),
    }))
    """)
    print("\n=== 第二条发完 chat 列表 ===")
    for m in msgs2:
        print(f"  [{m['idx']}] {m['role']}: {m['text']!r}")
    user_count = sum(1 for m in msgs2 if m['role'] == 'user')
    print(f"用户消息数: {user_count} (期望 2)")

    # 验"first message" 跟 "second message" 都还在
    has_first = any('first message' in m['text'] for m in msgs2)
    has_second = any('second message' in m['text'] for m in msgs2)
    print(f"含 'first message' 用户消息: {has_first}")
    print(f"含 'second message' 用户消息: {has_second}")
    if has_first and has_second:
        print("\n=== PASS ===")
    else:
        print(f"\n=== FAIL: first={has_first}, second={has_second} ===")

    b.close()
