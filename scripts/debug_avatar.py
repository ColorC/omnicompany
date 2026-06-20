# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""排查 MessageComponent 头像为什么不显示."""
from playwright.sync_api import sync_playwright


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_context(viewport={"width": 975, "height": 900}).new_page()
    page.goto("http://127.0.0.1:8210/chat-standalone", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    page.click('[data-testid="chat-standalone-new-session"]')
    page.wait_for_timeout(2000)
    page.fill('[data-cc-input]', "hi")
    page.click('[data-cc-send]')
    page.wait_for_timeout(8000)

    info = page.evaluate("""
    () => {
      const out = [];
      // 找带 'rounded-full' 的元素 (头像通常 rounded-full)
      const avatars = document.querySelectorAll('[class*="rounded-full"]');
      avatars.forEach((a, idx) => {
        const r = a.getBoundingClientRect();
        const cs = getComputedStyle(a);
        out.push({
          idx,
          text: a.textContent?.trim().slice(0, 5),
          class: a.className,
          rect: { x: r.x, y: r.y, w: r.width, h: r.height },
          display: cs.display,
          visibility: cs.visibility,
          opacity: cs.opacity,
        });
      });
      return out;
    }
    """)
    print(f"找到 {len(info)} 个 rounded-full 元素:")
    for a in info:
        print(f"  [{a['idx']}] text={a['text']!r} display={a['display']} rect={a['rect']}")
        print(f"      class={a['class'][:120]}")
    b.close()
