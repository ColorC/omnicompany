# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""一次性脚本: 看 chat-standalone 各层 bounding box, 找哪层没拉宽."""
from playwright.sync_api import sync_playwright


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_context(viewport={"width": 975, "height": 900}).new_page()
    page.goto("http://127.0.0.1:8210/chat-standalone", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    selectors = [
        ("html", "html"),
        ("body", "body"),
        ("#root", "#root"),
        ("chat-standalone-root", '[data-testid="chat-standalone-root"]'),
        ("standalone topbar (first child)", '[data-testid="chat-standalone-root"] > div:first-child'),
        ("standalone body (second child)", '[data-testid="chat-standalone-root"] > div:nth-child(2)'),
        ("CcChatEditor root", '[data-cc-chat-session-id]'),
        ("CcChatEditor body (2nd child of root)", '[data-cc-chat-session-id] > div:nth-child(2)'),
        ("messages container", '[data-cc-messages]'),
        ("composer textarea", '[data-cc-input]'),
    ]
    for label, sel in selectors:
        try:
            box = page.locator(sel).first.bounding_box()
            cs = page.locator(sel).first.evaluate(
                "el => { const c = getComputedStyle(el); return { w: c.width, mw: c.maxWidth, fb: c.flexBasis, flex: c.flex, display: c.display, fd: c.flexDirection, ai: c.alignItems }; }"
            )
            print(f"{label:48s} bbox={box}")
            print(f"{' ':48s} computed={cs}")
        except Exception as e:
            print(f"{label}: ERROR {e}")
    b.close()
