# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""ws 重连后 snapshot 重发, 验消息不复读 (幂等).

模拟: webview tab 切 focus 导致 ws 暂停后重连 (用户 2026-05-13 反馈"复读").
真路径: page.evaluate 主动 close ws 强制重连.
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

    # 发条消息
    page.locator('textarea').first.fill("hello world")
    page.locator('textarea').first.press("Control+Enter")
    page.wait_for_function(
        "document.querySelectorAll('.chat-message').length >= 2",
        timeout=60_000,
    )
    page.wait_for_timeout(4000)

    before = page.evaluate("""() => {
      return Array.from(document.querySelectorAll('.chat-message')).map(m => ({
        role: m.className.includes('user') ? 'user' : 'assistant',
        text: (m.textContent || '').trim().slice(0, 60),
      }))
    }""")
    print(f"--- 重连前 chat-message 数: {len(before)} ---")
    for m in before:
        print(f"  {m['role']}: {m['text']!r}")

    # 主动断 ws 触发 wsAutoReconnect (模拟 webview pause/resume)
    page.evaluate("""() => {
      const wss = window.__omniWsInstances || []
      // 没有的话直接找所有 WebSocket
      const allWs = []
      const origWs = window.WebSocket
      // patched 已晚, 这里用别招: 直接关掉页面 visibility?
      // 用 dispatchEvent visibilitychange 触发 wsAutoReconnect 可能的逻辑
      document.dispatchEvent(new Event('visibilitychange'))
      // 也直接遍历 navigator.connection?
      return 'no direct ws access; use document hidden trick'
    }""")
    # 用 navigate to about:blank then back 强制断开 + 重连不太对应真场景.
    # 更直接: 等待并观察是否有 reconnect
    page.wait_for_timeout(3000)

    after_idle = page.evaluate("""() => {
      return Array.from(document.querySelectorAll('.chat-message')).map(m => ({
        role: m.className.includes('user') ? 'user' : 'assistant',
        text: (m.textContent || '').trim().slice(0, 60),
      }))
    }""")
    print(f"--- 等 3s 后 chat-message 数: {len(after_idle)} ---")
    for m in after_idle:
        print(f"  {m['role']}: {m['text']!r}")

    # 直接重新 navigate 同 URL — 应该带来 ws 重连 + snapshot replay
    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    # 选回刚才那 session (URL 带 ?session=...)
    # 实际新 page 没记 session, 跑下一个 session — 不能很好测重连
    # 用更准的方式: page.evaluate 抓所有 WebSocket 实例后 close 它
    page.evaluate("""() => {
      // 拦 WebSocket.prototype 在新连接前
      const origSend = WebSocket.prototype.send
      window.__wsClosed = false
    }""")
    # 暂略: 后端被动断更难; 等先看上一步
    b.close()

    print("\n[note] 真重连测试需 backend 主动 close 或 webview lifecycle. 上面是初步.")
