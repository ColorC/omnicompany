# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""验 MessageComponent 在 dark class 激活后字颜色变浅."""
from playwright.sync_api import sync_playwright


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_context(viewport={"width": 975, "height": 900}).new_page()
    page.goto("http://127.0.0.1:8210/chat-standalone", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)

    # 起 session 让 chat 渲染
    page.click('[data-testid="chat-standalone-new-session"]')
    page.wait_for_timeout(2000)

    # 验 <html class="dark"> 真生效
    html_cls = page.evaluate("() => document.documentElement.className")
    print(f"<html> class = {html_cls!r}")

    # 找一个 MessageComponent 内带 dark:text-* 的元素, 测真渲染色
    page.fill('[data-cc-input]', "hi")
    page.click('[data-cc-send]')
    page.wait_for_timeout(8000)  # 等 assistant 回复出来

    # 找 assistant 消息块, dump 几个文字元素的 color
    samples = page.evaluate("""
    () => {
      const out = [];
      const messages = document.querySelectorAll('.chat-message');
      messages.forEach((m, idx) => {
        const role = m.className.includes('user') ? 'user' : 'assistant';
        // 找 m 内带文字的元素
        const texts = m.querySelectorAll('div, p, span');
        texts.forEach((t) => {
          const txt = t.textContent?.trim().slice(0, 30);
          if (!txt || t.children.length > 0) return;
          const c = getComputedStyle(t);
          out.push({ msgIdx: idx, role, txt, color: c.color, bgColor: c.backgroundColor, classes: t.className });
        });
      });
      return out.slice(0, 10);
    }
    """)
    for s in samples:
        print(s)
    b.close()
