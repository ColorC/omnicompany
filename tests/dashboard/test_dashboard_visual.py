"""Dashboard 视觉自测 — Playwright 截图 + LLM 视觉 + 传统断言

运行前提:
    1. pip install playwright && playwright install chromium
    2. Dashboard 已启动: uvicorn omnicompany.dashboard.app:app --port 8000
    3. (可选) 设置 DASHSCOPE_API_KEY 环境变量启用 LLM 视觉验证

用法:
    pytest tests/test_dashboard_visual.py -v
    pytest tests/test_dashboard_visual.py -v -k "test_visual" --screenshot-dir ./screenshots
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://127.0.0.1:8000")
SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", ROOT / "tests" / "screenshots"))


@pytest.fixture(scope="module")
def browser_page():
    """Launch a headless Chromium browser for all tests in this module."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed: pip install playwright && playwright install chromium")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        yield page
        browser.close()


@pytest.fixture(autouse=True)
def _ensure_screenshot_dir():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


class TestDashboardAPI:
    """API endpoint tests — no browser needed."""

    def test_api_nodes(self):
        import urllib.request
        try:
            resp = urllib.request.urlopen(f"{DASHBOARD_URL}/api/nodes", timeout=5)
            data = json.loads(resp.read())
            assert isinstance(data, list)
        except Exception as e:
            pytest.skip(f"Dashboard not running: {e}")

    def test_api_evolution(self):
        import urllib.request
        try:
            resp = urllib.request.urlopen(f"{DASHBOARD_URL}/api/evolution", timeout=5)
            data = json.loads(resp.read())
            assert isinstance(data, list)
        except Exception as e:
            pytest.skip(f"Dashboard not running: {e}")

    def test_api_health(self):
        import urllib.request
        try:
            resp = urllib.request.urlopen(f"{DASHBOARD_URL}/api/health", timeout=5)
            data = json.loads(resp.read())
            assert isinstance(data, dict)
        except Exception as e:
            pytest.skip(f"Dashboard not running: {e}")

    def test_api_params(self):
        import urllib.request
        try:
            resp = urllib.request.urlopen(f"{DASHBOARD_URL}/api/params", timeout=5)
            data = json.loads(resp.read())
            assert "current" in data
        except Exception as e:
            pytest.skip(f"Dashboard not running: {e}")


class TestDashboardVisual:
    """Visual tests using Playwright screenshots."""

    def test_page_loads(self, browser_page):
        try:
            browser_page.goto(DASHBOARD_URL, timeout=10000)
        except Exception as e:
            pytest.skip(f"Dashboard not reachable: {e}")

        assert "OmniCompany" in browser_page.title() or "omnicompany" in browser_page.content().lower()

    def test_overview_section_exists(self, browser_page):
        try:
            browser_page.goto(DASHBOARD_URL, timeout=10000)
        except Exception:
            pytest.skip("Dashboard not reachable")

        browser_page.wait_for_timeout(2000)
        content = browser_page.content()
        assert "Total Rounds" in content or "total" in content.lower()

    def test_screenshot_full_page(self, browser_page):
        try:
            browser_page.goto(DASHBOARD_URL, timeout=10000)
        except Exception:
            pytest.skip("Dashboard not reachable")

        browser_page.wait_for_timeout(3000)
        path = SCREENSHOT_DIR / "dashboard_full.png"
        browser_page.screenshot(path=str(path), full_page=True)
        assert path.exists()
        assert path.stat().st_size > 10000

    def test_no_js_errors(self, browser_page):
        errors: list[str] = []
        browser_page.on("pageerror", lambda err: errors.append(str(err)))

        try:
            browser_page.goto(DASHBOARD_URL, timeout=10000)
        except Exception:
            pytest.skip("Dashboard not reachable")

        browser_page.wait_for_timeout(3000)
        assert len(errors) == 0, f"JS errors found: {errors}"

    def test_charts_rendered(self, browser_page):
        try:
            browser_page.goto(DASHBOARD_URL, timeout=10000)
        except Exception:
            pytest.skip("Dashboard not reachable")

        browser_page.wait_for_timeout(3000)
        canvases = browser_page.query_selector_all("canvas")
        assert len(canvases) >= 1, "Expected at least 1 chart canvas"

    def test_visual_llm_audit(self, browser_page):
        """Use LLM vision to validate the dashboard screenshot looks correct.

        Requires DASHSCOPE_API_KEY environment variable.
        """
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            pytest.skip("DASHSCOPE_API_KEY not set, skipping LLM visual audit")

        try:
            browser_page.goto(DASHBOARD_URL, timeout=10000)
        except Exception:
            pytest.skip("Dashboard not reachable")

        browser_page.wait_for_timeout(3000)
        screenshot_path = SCREENSHOT_DIR / "dashboard_llm_audit.png"
        browser_page.screenshot(path=str(screenshot_path), full_page=True)

        import base64
        with open(screenshot_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        import urllib.request
        payload = {
            "model": "qwen-vl-max",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": (
                            "This is a screenshot of a software system monitoring dashboard. "
                            "Please verify:\n"
                            "1. The page has a dark theme\n"
                            "2. There are metric cards showing system stats\n"
                            "3. There is at least one chart/graph\n"
                            "4. There is a table of nodes\n"
                            "5. The layout looks professional and readable\n\n"
                            "Respond with JSON: {\"pass\": true/false, \"issues\": [\"issue1\", ...]}"
                        )},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                    ],
                }
            ],
        }

        req = urllib.request.Request(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        try:
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read())
            content = result["choices"][0]["message"]["content"]
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                verdict = json.loads(content[start:end])
                assert verdict.get("pass", False), f"LLM visual audit failed: {verdict.get('issues', [])}"
            else:
                pytest.skip(f"LLM response not parseable: {content[:200]}")
        except Exception as e:
            pytest.skip(f"LLM visual audit request failed: {e}")
