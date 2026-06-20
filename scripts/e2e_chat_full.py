# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""全面 e2e Playwright 验 ChatStandalone 6 项, 用户 2026-05-12 反馈触发.

不止"组件 mount", 而是真发消息真看 DOM, 真打 / 看 slash 候选, 真观 ctx, 真捕 postMessage.
"""
from playwright.sync_api import sync_playwright


URL = "http://127.0.0.1:8210/chat-standalone"


def run() -> dict[str, str]:
    results: dict[str, str] = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1100, "height": 900})
        page = ctx.new_page()
        # 立 cap_response 抓 commands/list (fetch 在 CcChatPanel mount 时就发, 晚挂会错过)
        cmd_responses = []
        def cap_response(r):
            if '/api/commands/list' in r.url:
                cmd_responses.append({'status': r.status, 'url': r.url})
        page.on('response', cap_response)
        post_msgs: list = []
        # 监听 ChatStandalone postMessage 到 top (extension 的桥)
        page.add_init_script("""
        window.__capturedPostMessages = []
        const origPost = window.postMessage
        window.postMessage = function(...args) {
          if (args[0] && args[0].__omnichat) {
            window.__capturedPostMessages.push(JSON.parse(JSON.stringify(args[0])))
          }
          return origPost.apply(window, args)
        }
        """)
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # 1. 创 claude_code session
        page.click('[data-testid="chat-standalone-new-session"]')
        page.wait_for_timeout(3000)
        results["session_created"] = "PASS" if page.locator('[data-cc-chat-panel]').count() else "FAIL"

        # 2. 发 hi, 验**用户消息显示** + **回复显示** + **thinking 卡数**
        page.locator('textarea').first.fill("hi")
        page.wait_for_timeout(300)
        page.locator('textarea').first.press("Control+Enter")
        try:
            page.wait_for_function(
                "document.querySelectorAll('.chat-message').length >= 2",
                timeout=60_000,
            )
        except Exception:
            pass
        page.wait_for_timeout(2000)

        # 抓所有 chat-message DOM 结构
        msgs = page.evaluate("""
        () => {
          return Array.from(document.querySelectorAll('.chat-message')).map((m, i) => ({
            idx: i,
            classes: m.className,
            text: (m.textContent || '').trim().slice(0, 150),
            hasThinking: m.textContent?.includes('Thought for'),
          }))
        }
        """)
        user_msgs = [m for m in msgs if 'user' in m['classes']]
        assistant_msgs = [m for m in msgs if 'assistant' in m['classes']]
        thinking_count = sum(1 for m in msgs if m.get('hasThinking'))

        print(f"--- chat 消息 (共 {len(msgs)} 条) ---")
        for m in msgs:
            role = 'user' if 'user' in m['classes'] else ('assistant' if 'assistant' in m['classes'] else '?')
            print(f"  [{m['idx']}] {role}: {m['text']!r}")
        print(f"用户消息数: {len(user_msgs)} (期望 >=1)")
        print(f"assistant 消息数: {len(assistant_msgs)} (期望 >=1)")
        print(f"thinking 卡数: {thinking_count} (期望 0 或 1, 不应多张)")
        results["user_msg_shown"] = "PASS" if user_msgs else "FAIL: 用户消息没显示, 被吞掉"
        results["assistant_msg_shown"] = "PASS" if assistant_msgs else "FAIL"
        results["thinking_dedup"] = "PASS" if thinking_count <= 1 else f"FAIL: {thinking_count} 张 thinking"

        # 3. postMessage 状态被捕获
        captured = page.evaluate("() => window.__capturedPostMessages || []")
        print(f"--- postMessage 捕 {len(captured)} 条 ---")
        for c in captured[:5]:
            print(f"  {c}")
        states = [c.get('state') for c in captured]
        has_processing = 'processing' in states
        has_idle = 'idle' in states
        results["postmsg_processing"] = "PASS" if has_processing else "FAIL: 没发 processing"
        results["postmsg_idle"] = "PASS" if has_idle else "FAIL: 没发 idle"

        # 4. slash 命令弹出 — 打 / 看候选
        page.locator('textarea').first.click()
        page.locator('textarea').first.fill("")
        page.wait_for_timeout(300)
        page.locator('textarea').first.type("/", delay=100)
        page.wait_for_timeout(2000)

        diagnostic = page.evaluate("""
        () => {
          const menu = document.querySelector('.command-menu')
          const itemsInMenu = menu ? menu.querySelectorAll('button, [role="option"], .command-group').length : 0
          // 试找文字 'compact' / 'clear' 出现在 DOM
          const textHits = Array.from(document.querySelectorAll('*')).filter(e =>
            e.children.length === 0 && /^(compact|clear|init|resume)/i.test(e.textContent || '')
          ).length
          return { menuExist: !!menu, itemsInMenu, textHits }
        }
        """)
        print(f"--- slash diagnostic ---")
        print(f"  /api/commands/list HTTP: {cmd_responses}")
        print(f"  .command-menu exists: {diagnostic['menuExist']}")
        print(f"  items in menu: {diagnostic['itemsInMenu']}")
        print(f"  /^(compact|clear|init|resume)/ 文字命中: {diagnostic['textHits']}")
        results["slash_menu"] = "PASS" if diagnostic['itemsInMenu'] > 0 else f"FAIL: items={diagnostic['itemsInMenu']} exist={diagnostic['menuExist']}"

        # 5.0 token budget % 真更新 (composer 底栏 0.0% 不应永远 0%)
        page.locator('textarea').first.fill("")
        page.wait_for_timeout(500)
        token_pct_text = page.evaluate("""
        () => {
          // composer 底栏 TokenUsagePie 旁边显示 X.X%
          const els = Array.from(document.querySelectorAll('*')).filter(e =>
            e.children.length === 0 && /\\d+\\.\\d+%/.test(e.textContent || '')
          )
          return els.map(e => e.textContent?.trim()).slice(0, 5)
        }
        """)
        print(f"--- 底栏百分比文本: {token_pct_text} ---")
        not_all_zero = any(p != '0.0%' for p in token_pct_text)
        results["token_pct_updates"] = "PASS" if not_all_zero else f"FAIL: 全 0.0% (没 status token_budget?)"

        # 5. ctx 面板唤出有数据
        page.locator('textarea').first.fill("")
        page.click('[data-testid="chat-standalone-context-toggle"]')
        page.wait_for_timeout(2500)
        ctx_count = page.locator('[data-ctx-section]').count()
        results["ctx_panel"] = "PASS" if ctx_count > 0 else "FAIL"

        b.close()
    return results


if __name__ == "__main__":
    results = run()
    print("\n=== 结果汇总 ===")
    fails = 0
    for k, v in results.items():
        marker = "✓" if v.startswith("PASS") else "✗"
        print(f"  {marker} {k}: {v}")
        if not v.startswith("PASS"):
            fails += 1
    print(f"\n{len(results) - fails}/{len(results)} PASS")
