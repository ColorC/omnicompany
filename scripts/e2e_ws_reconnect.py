# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""真重连 e2e: 强制 close ws, 等 wsAutoReconnect 重连, 验 snapshot 替换不复读."""
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8210/chat-standalone"

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_context(viewport={"width": 1100, "height": 900}).new_page()

    # 注入: 暴露 WebSocket instances 给测试访问
    page.add_init_script("""
    window.__omniWsInstances = []
    const origWs = window.WebSocket
    window.WebSocket = function(...args) {
      const ws = new origWs(...args)
      window.__omniWsInstances.push(ws)
      return ws
    }
    Object.setPrototypeOf(window.WebSocket, origWs)
    window.WebSocket.prototype = origWs.prototype
    """)

    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    page.click('[data-testid="chat-standalone-new-session"]')
    page.wait_for_timeout(3000)

    page.locator('textarea').first.fill("hello before reconnect")
    page.locator('textarea').first.press("Control+Enter")
    page.wait_for_function(
        "document.querySelectorAll('.chat-message').length >= 2",
        timeout=60_000,
    )
    page.wait_for_timeout(4000)

    msgs_before = page.evaluate("""() =>
      Array.from(document.querySelectorAll('.chat-message')).map(m => ({
        role: m.className.includes('user') ? 'user' : 'assistant',
        text: (m.textContent || '').trim().slice(0, 60),
      }))
    """)
    print(f"[1] 重连前: {len(msgs_before)} 条 chat-message")
    for m in msgs_before: print(f"  {m['role']}: {m['text']!r}")

    # 强制 close 所有 ws — 触发 wsAutoReconnect
    closed_count = page.evaluate("""() => {
      const wss = window.__omniWsInstances.filter(w => w.readyState === 1)  // OPEN
      wss.forEach(w => w.close(1006, 'forced for test'))  // 1006 = abnormal, 触发重连
      return wss.length
    }""")
    print(f"\n[2] 强制 close {closed_count} 个 ws, 等 wsAutoReconnect ...")
    page.wait_for_timeout(5000)  # backoff 1s 重连 + snapshot 复制时间

    msgs_after = page.evaluate("""() =>
      Array.from(document.querySelectorAll('.chat-message')).map(m => ({
        role: m.className.includes('user') ? 'user' : 'assistant',
        text: (m.textContent || '').trim().slice(0, 60),
      }))
    """)
    print(f"\n[3] 重连后: {len(msgs_after)} 条 chat-message")
    for m in msgs_after: print(f"  {m['role']}: {m['text']!r}")

    # 关键验: 重连前后 chat-message 数应该一致 (snapshot 幂等)
    if len(msgs_before) == len(msgs_after):
        print(f"\n=== PASS · 幂等 (重连前后 {len(msgs_before)} 条) ===")
    else:
        print(f"\n=== FAIL · 重连导致复读! 前 {len(msgs_before)} 后 {len(msgs_after)} ===")

    # 再发条消息验
    print("\n[4] 重连后再发条消息看是否正常")
    page.locator('textarea').first.fill("after reconnect")
    page.locator('textarea').first.press("Control+Enter")
    try:
        page.wait_for_function(
            f"document.querySelectorAll('.chat-message').length > {len(msgs_after) + 1}",
            timeout=60_000,
        )
    except Exception:
        pass
    page.wait_for_timeout(3000)
    msgs_final = page.evaluate("""() =>
      Array.from(document.querySelectorAll('.chat-message')).map(m => ({
        role: m.className.includes('user') ? 'user' : 'assistant',
        text: (m.textContent || '').trim().slice(0, 60),
      }))
    """)
    print(f"[5] 最终: {len(msgs_final)} 条 chat-message")
    has_after = any('after reconnect' in m['text'] for m in msgs_final)
    print(f"   含 'after reconnect' 用户消息: {has_after}")

    b.close()
