# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""验头像按 provider 切换 (claude session → claude svg, codex session → codex svg)."""
from playwright.sync_api import sync_playwright


def get_assistant_avatar_src(page) -> str:
    """找 assistant 消息的头像 img src."""
    return page.evaluate("""
    () => {
      // assistant 头像通常是 .rounded-full img, user 头像是 'U' 文字
      const imgs = document.querySelectorAll('[class*="rounded-full"] img');
      for (const img of imgs) {
        if (img.src.includes('-icon.svg') || img.src.includes('codex')) {
          return img.src;
        }
      }
      return '(no avatar img found)';
    }
    """)


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 975, "height": 900})

    # Gate 1: claude_code session → 头像应为 claude-ai-icon.svg
    page1 = ctx.new_page()
    page1.goto("http://127.0.0.1:8210/chat-standalone", wait_until="domcontentloaded")
    page1.wait_for_timeout(1500)
    # 默认 provider=claude_code
    page1.click('[data-testid="chat-standalone-new-session"]')
    page1.wait_for_timeout(2000)
    page1.fill('[data-cc-input]', "hi")
    page1.click('[data-cc-send]')
    page1.wait_for_timeout(8000)
    avatar1 = get_assistant_avatar_src(page1)
    print(f"[gate1] claude_code session 头像: {avatar1}")
    if "claude" in avatar1.lower():
        print("        ✓ 含 'claude'")
    else:
        print("        ✗ FAIL 不含 'claude'")

    # Gate 2: codex session → 头像应为 codex.svg
    page2 = ctx.new_page()
    page2.goto("http://127.0.0.1:8210/chat-standalone", wait_until="domcontentloaded")
    page2.wait_for_timeout(1500)
    # 切到 codex
    page2.select_option('[data-testid="chat-standalone-provider-select"]', 'codex')
    page2.wait_for_timeout(500)
    page2.click('[data-testid="chat-standalone-new-session"]')
    page2.wait_for_timeout(3000)
    page2.fill('[data-cc-input]', "say hi")
    page2.click('[data-cc-send]')
    page2.wait_for_timeout(15000)  # codex 第一次 cold start 慢
    avatar2 = get_assistant_avatar_src(page2)
    print(f"[gate2] codex session 头像: {avatar2}")
    if "codex" in avatar2.lower():
        print("        ✓ 含 'codex'")
    else:
        print("        ✗ FAIL 不含 'codex'")

    b.close()
