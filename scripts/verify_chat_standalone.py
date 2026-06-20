# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
#!/usr/bin/env python3
# [OMNI] origin=ai-ide ts=2026-05-10 type=script
# [OMNI] material_id="material:scripts.verify_chat_standalone.playwright_route_assertion.py"
"""Playwright 验 /chat-standalone 路由真生效, 不是 curl 自欺.

两门验:
  1. /chat-standalone → 必有 [data-testid="chat-standalone-root"] + 顶栏 "Omni Chat" 文字
  2. /                → 必无 [data-testid="chat-standalone-root"] (走 App 完整外壳)

上轮事故就是 main.tsx edit 后没 rebuild, bundle 没分流逻辑, curl /chat-standalone
拿 200 + index.html 永远成立但 JS 实际渲染整页 dashboard. Playwright 启 chromium
真跑 JS, 读 DOM, 才能看到 SPA 路由真行为.
"""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


BASE_URL = "http://127.0.0.1:8210"


def main() -> int:
    failures: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        # ── Gate 1: /chat-standalone → 裸 chat 根挂上 ──
        page = context.new_page()
        page.goto(f"{BASE_URL}/chat-standalone", wait_until="domcontentloaded", timeout=30_000)
        try:
            page.wait_for_selector('[data-testid="chat-standalone-root"]', timeout=10_000)
            print("[gate1] /chat-standalone: chat-standalone-root 挂上 ✓")
        except PlaywrightTimeout:
            failures.append("gate1: /chat-standalone 没渲染 chat-standalone-root (路由分流没生效)")

        try:
            brand = page.locator('[data-testid="chat-standalone-brand"]').inner_text(timeout=3_000)
            if brand.strip() == "Omni Chat":
                print(f"[gate1] 顶栏 brand 文字 = {brand!r} ✓")
            else:
                failures.append(f"gate1: 顶栏 brand 应为 'Omni Chat', 实为 {brand!r}")
        except PlaywrightTimeout:
            failures.append("gate1: 顶栏 brand selector 没找到")

        # 顺带验"+ 新 session"按钮在 (证明完整 ChatStandalone 渲染, 不是骨架)
        try:
            page.wait_for_selector('[data-testid="chat-standalone-new-session"]', timeout=3_000)
            print("[gate1] '+ 新 session' 按钮在 ✓")
        except PlaywrightTimeout:
            failures.append("gate1: '+ 新 session' 按钮没渲染")

        # 建一个 session 让 CcChatEditor 渲染出来, 然后验右侧 SessionContextPanel 不在
        # (用 [data-ctx-section] 这个 SessionContextPanel 内部 selector 计数 = 0)
        try:
            page.click('[data-testid="chat-standalone-new-session"]', timeout=3_000)
            page.wait_for_timeout(2_000)  # 等 session 创出来 + CcChatEditor mount
            ctx_count = page.locator('[data-ctx-section]').count()
            if ctx_count == 0:
                print(f"[gate1] 右侧 SessionContextPanel 不渲染 (data-ctx-section count={ctx_count}) ✓")
            else:
                failures.append(f"gate1: hideContextPanel 没生效, SessionContextPanel 还在 (data-ctx-section count={ctx_count})")
        except PlaywrightTimeout:
            failures.append("gate1: 点 '+ 新 session' 按钮失败 (3s 超时)")

        page.close()

        # ── Gate 2: / → 完整 dashboard, 不该有 chat-standalone-root ──
        page2 = context.new_page()
        page2.goto(f"{BASE_URL}/", wait_until="domcontentloaded", timeout=30_000)
        # 等几秒让 App 渲染完
        page2.wait_for_timeout(2_000)
        # chat-standalone-root 应该不存在
        count = page2.locator('[data-testid="chat-standalone-root"]').count()
        if count == 0:
            print(f"[gate2] / : chat-standalone-root 不存在 ✓")
        else:
            failures.append(f"gate2: / 路径渲染了 chat-standalone-root (count={count}, 应该=0). 分流条件错")

        page2.close()
        browser.close()

    if failures:
        print("\n=== FAIL ===")
        for f in failures:
            print(f"  · {f}")
        return 1

    print("\n=== PASS · 两门全过 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
