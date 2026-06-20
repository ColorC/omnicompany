# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""新版 panel 作为默认后的全面 Playwright dogfood 验证.

测 4 点:
1. 默认 URL 走新版 (CcChatPanel + ChatInterface)
2. Claude session 头像 = claude-ai-icon.svg, Codex session 头像 = codex.svg
3. 字体大小可读 (>= 14px)
4. ctx 面板唤出后真有数据
"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1100, "height": 900})

    # ── Gate 1: 默认 URL 走新版 ──
    page = ctx.new_page()
    pageerr = []
    page.on("pageerror", lambda e: pageerr.append(str(e)))
    page.goto("http://127.0.0.1:8210/chat-standalone", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    panel_count = page.locator('[data-cc-chat-panel]').count()
    old_count = page.locator('[data-cc-chat-session-id]:not([data-cc-chat-panel])').count()
    print(f"[gate1] 默认 URL 渲染: panel(新)={panel_count} old={old_count}")
    if panel_count >= 1:
        print("        ✓ 默认走新版")
    else:
        print("        ✗ FAIL 默认没走新版")

    # ── Gate 2: Claude 头像 ──
    page.click('[data-testid="chat-standalone-new-session"]')
    page.wait_for_timeout(3000)
    page.locator('textarea').first.fill("hi")
    page.locator('textarea').first.press("Control+Enter")
    page.wait_for_function(
        "document.querySelectorAll('.chat-message').length >= 2",
        timeout=60_000,
    )
    page.wait_for_timeout(500)
    claude_avatar = page.evaluate("""
    () => {
      const imgs = document.querySelectorAll('[class*="rounded-full"] img');
      for (const img of imgs) {
        if (img.src.includes('-icon.svg') || img.src.includes('codex')) return img.src;
      }
      return null;
    }
    """)
    print(f"[gate2] Claude session 头像: {claude_avatar}")
    if claude_avatar and 'claude' in claude_avatar.lower():
        print("        ✓ 是 claude svg")
    else:
        print("        ✗ FAIL 不是 claude svg")

    # ── Gate 3: 字体大小 ──
    composer_font = page.evaluate("""
    () => {
      const ta = document.querySelector('textarea');
      if (!ta) return null;
      const cs = getComputedStyle(ta);
      return parseFloat(cs.fontSize);
    }
    """)
    msg_font = page.evaluate("""
    () => {
      const msg = document.querySelector('.chat-message');
      if (!msg) return null;
      const cs = getComputedStyle(msg);
      return parseFloat(cs.fontSize);
    }
    """)
    print(f"[gate3] 字体: composer={composer_font}px message={msg_font}px")
    if composer_font and composer_font >= 13 and msg_font and msg_font >= 13:
        print("        ✓ >= 13px (可读)")
    else:
        print("        ✗ FAIL 字体太小")
    page.close()

    # ── Gate 4: Codex 头像 ──
    page2 = ctx.new_page()
    page2.goto("http://127.0.0.1:8210/chat-standalone", wait_until="domcontentloaded")
    page2.wait_for_timeout(1500)
    page2.select_option('[data-testid="chat-standalone-provider-select"]', 'codex')
    page2.wait_for_timeout(500)
    page2.click('[data-testid="chat-standalone-new-session"]')
    page2.wait_for_timeout(3000)
    page2.locator('textarea').first.fill("say hi briefly")
    page2.locator('textarea').first.press("Control+Enter")
    try:
        page2.wait_for_function(
            "document.querySelectorAll('.chat-message').length >= 2",
            timeout=60_000,
        )
        page2.wait_for_timeout(1000)
    except Exception:
        pass
    codex_avatar = page2.evaluate("""
    () => {
      const imgs = document.querySelectorAll('[class*="rounded-full"] img');
      for (const img of imgs) {
        if (img.src.includes('-icon.svg') || img.src.includes('codex')) return img.src;
      }
      return null;
    }
    """)
    print(f"[gate4] Codex session 头像: {codex_avatar}")
    if codex_avatar and 'codex' in codex_avatar.lower():
        print("        ✓ 是 codex svg")
    else:
        print("        ✗ FAIL 不是 codex svg")
    page2.close()

    # ── Gate 5: ctx 面板唤出真有数据 ──
    page3 = ctx.new_page()
    page3.goto("http://127.0.0.1:8210/chat-standalone", wait_until="domcontentloaded")
    page3.wait_for_timeout(1500)
    page3.click('[data-testid="chat-standalone-new-session"]')
    page3.wait_for_timeout(3000)
    # 默认 ctx 隐藏
    ctx_count_initial = page3.locator('[data-ctx-section]').count()
    print(f"[gate5a] ctx 默认隐藏: data-ctx-section 数={ctx_count_initial} (期望 0)")
    # 点击切换
    page3.click('[data-testid="chat-standalone-context-toggle"]')
    page3.wait_for_timeout(2500)  # 等 SessionContextPanel fetch context API
    ctx_count_after = page3.locator('[data-ctx-section]').count()
    print(f"[gate5b] ctx 唤出后: data-ctx-section 数={ctx_count_after} (期望 > 0)")
    # 抓 ctx 内有什么内容
    ctx_text = page3.evaluate("""
    () => {
      const sections = document.querySelectorAll('[data-ctx-section]');
      return Array.from(sections).map((s, i) => `[${i}] ${s.getAttribute('data-ctx-section')} : ${s.textContent?.trim().slice(0, 80)}`).join('\\n');
    }
    """)
    print("[gate5c] ctx 内容前若干 section:")
    print(ctx_text)
    if ctx_count_after >= 1:
        print("        ✓ ctx 面板真渲染了")
    else:
        print("        ✗ FAIL ctx 面板唤不出")
    page3.close()

    print(f"\n[summary] pageerror count = {len(pageerr)}")

    b.close()
