# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""端到端验 ?panel=new 新版 ChatInterface 真能 chat: 发 'hi' 收到 Claude 回复并渲染."""
from playwright.sync_api import sync_playwright


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_context(viewport={"width": 1100, "height": 900}).new_page()

    pageerr = []
    page.on("pageerror", lambda e: pageerr.append(str(e)))

    page.goto("http://127.0.0.1:8210/chat-standalone?panel=new", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # 1. 新建 claude_code session
    page.click('[data-testid="chat-standalone-new-session"]')
    page.wait_for_timeout(3000)

    panel_count = page.locator('[data-cc-chat-panel]').count()
    textarea_count = page.locator('textarea').count()
    print(f"[1] panel={panel_count} textarea={textarea_count}")

    if textarea_count == 0:
        print("FAIL: 没 textarea, ChatComposer 没渲染")
        b.close()
        exit(1)

    # 2. 输入 'hi' 然后 Ctrl+Enter 发送 (sendByCtrlEnter=true)
    page.locator('textarea').first.fill("hi")
    page.wait_for_timeout(500)
    page.locator('textarea').first.press("Control+Enter")
    print("[2] 发了 'hi', 等回复 ...")

    # 3. 等 .chat-message 数 > 0 (上游 ChatInterface 用 .chat-message class 渲染)
    try:
        page.wait_for_function(
            "document.querySelectorAll('.chat-message').length >= 2",  # user msg + assistant msg
            timeout=60_000,
        )
        msg_count = page.locator('.chat-message').count()
        print(f"[3] 收到回复, .chat-message 数 = {msg_count}")
    except Exception as e:
        msg_count = page.locator('.chat-message').count()
        print(f"[3] TIMEOUT, .chat-message 数 = {msg_count}, err = {e!r}")

    # 4. 抓最后一条 assistant 消息文本看实际内容
    last_text = page.evaluate("""
    () => {
      const msgs = document.querySelectorAll('.chat-message');
      if (msgs.length === 0) return '(no messages)';
      const last = msgs[msgs.length - 1];
      return last.textContent?.trim().slice(0, 200) || '(empty)';
    }
    """)
    print(f"[4] 最后一条消息文本前 200 字符: {last_text!r}")

    # 5. 抓头像 (验 provider 头像也是 claude)
    avatar_src = page.evaluate("""
    () => {
      const imgs = document.querySelectorAll('[class*="rounded-full"] img');
      for (const img of imgs) {
        if (img.src.includes('claude') || img.src.includes('codex')) return img.src;
      }
      return '(no avatar)';
    }
    """)
    print(f"[5] 头像 src: {avatar_src}")

    print(f"\n[summary] pageerror={len(pageerr)} chat-message={msg_count}")
    if msg_count >= 2 and len(pageerr) == 0:
        print("=== PASS · 新版 panel 端到端 chat 真通了 ===")
    else:
        print("=== FAIL ===")
        for e in pageerr[:3]:
            print(f"  err: {e}")

    b.close()
