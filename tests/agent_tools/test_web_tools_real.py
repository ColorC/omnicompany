"""WebFetch / WebSearch 真接通 e2e (2026-05-05 立).

真 e2e:
  - WebFetch: 起本地 HTTP server, 真 GET, 验 HTML 抽文 / JSON / 错误分类
  - WebSearch: dry_run 验过滤 + 错误分支
  - 真 DuckDuckGo 调用标 network, 默认 skip

不验:
  - 跨域 redirect 跟进 (urllib 自动处理)
  - 真 HTTPS 证书 (由系统 CA 处理)
"""
from __future__ import annotations

import http.server
import json
import os
import socketserver
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.agent.routers.web_fetch import WebFetchRouter
from omnicompany.packages.services._core.agent.routers.web_search import WebSearchRouter
from omnicompany.packages.services._core.agent.routers.single_tool import (
    ToolContext,
    ToolExecutionError,
)


def _new(cls):
    return cls.__new__(cls)


# ═══════════════════════════════════════════════════════════════════════
# 本地 HTTP server fixture (真 e2e — 不依赖外网)
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def local_http_server():
    """起本地 HTTP server, yield (port, server)."""
    routes: dict[str, tuple[int, str, bytes]] = {
        "/html": (200, "text/html; charset=utf-8", (
            b"<!DOCTYPE html><html><head><title>T</title>"
            b"<script>var x=1;</script></head>"
            b"<body><h1>Heading</h1><p>Para 1</p><p>Para 2</p>"
            b"<style>body{color:red;}</style>"
            b"<div>Block content</div></body></html>"
        )),
        "/json": (200, "application/json", b'{"key": "value", "n": 42}'),
        "/text": (200, "text/plain", b"plain text content"),
        "/404": (404, "text/plain", b"not found"),
        "/500": (500, "text/plain", b"server error"),
        "/large": (200, "text/plain", b"x" * 600_000),  # > 500KB 触发截断
    }

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path in routes:
                code, ctype, body = routes[self.path]
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args, **kwargs) -> None:
            pass  # 静音

    httpd = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        httpd.shutdown()
        httpd.server_close()


# ═══════════════════════════════════════════════════════════════════════
# WebFetch 真 e2e
# ═══════════════════════════════════════════════════════════════════════


class TestWebFetchE2E:
    def test_html_strips_to_text(self, local_http_server):
        port = local_http_server
        r = _new(WebFetchRouter)
        out = r._execute({"url": f"http://127.0.0.1:{port}/html"}, ToolContext())
        # 头部 metadata
        assert "status=200" in out
        assert "html" in out.lower()
        # 正文抽文 (script 跟 style 应被剥)
        assert "Heading" in out
        assert "Para 1" in out
        assert "Para 2" in out
        assert "Block content" in out
        # script / style 内容不该出现
        assert "var x=1" not in out
        assert "color:red" not in out

    def test_json_returned_as_is(self, local_http_server):
        port = local_http_server
        r = _new(WebFetchRouter)
        out = r._execute({"url": f"http://127.0.0.1:{port}/json"}, ToolContext())
        assert "status=200" in out
        # JSON 原样
        assert '"key": "value"' in out
        assert '"n": 42' in out

    def test_plaintext_returned_as_is(self, local_http_server):
        port = local_http_server
        r = _new(WebFetchRouter)
        out = r._execute({"url": f"http://127.0.0.1:{port}/text"}, ToolContext())
        assert "plain text content" in out

    def test_404_raises(self, local_http_server):
        port = local_http_server
        r = _new(WebFetchRouter)
        with pytest.raises(ToolExecutionError, match="HTTP 404"):
            r._execute({"url": f"http://127.0.0.1:{port}/404"}, ToolContext())

    def test_500_raises(self, local_http_server):
        port = local_http_server
        r = _new(WebFetchRouter)
        with pytest.raises(ToolExecutionError, match="HTTP 500"):
            r._execute({"url": f"http://127.0.0.1:{port}/500"}, ToolContext())

    def test_500kb_truncation(self, local_http_server):
        port = local_http_server
        r = _new(WebFetchRouter)
        out = r._execute({"url": f"http://127.0.0.1:{port}/large"}, ToolContext())
        assert "TRUNCATED" in out
        # 物理截断后 body <= 500KB
        body = out.split("]\n\n", 1)[1] if "]\n\n" in out else out
        assert len(body) <= 510_000  # 含解码 padding 误差

    def test_invalid_scheme(self):
        r = _new(WebFetchRouter)
        with pytest.raises(ToolExecutionError, match="unsupported scheme"):
            r._execute({"url": "ftp://example.com/x"}, ToolContext())

    def test_no_url_raises(self):
        r = _new(WebFetchRouter)
        with pytest.raises(ToolExecutionError, match="url is required"):
            r._execute({}, ToolContext())

    def test_dns_failure_raises(self):
        r = _new(WebFetchRouter)
        # 用一个明显不存在的 .invalid TLD (RFC 6761 保留)
        with pytest.raises(ToolExecutionError, match="URL error|fetch failed"):
            r._execute({"url": "http://this-host-must-not-exist-xyz123.invalid/"}, ToolContext())


# ═══════════════════════════════════════════════════════════════════════
# WebSearch — dry_run + 过滤逻辑 (不调外网)
# ═══════════════════════════════════════════════════════════════════════


class TestWebSearchDryRun:
    def test_dry_run_returns_mock_results(self, monkeypatch):
        monkeypatch.setenv("OMNI_WEB_SEARCH_DRY_RUN", "1")
        r = _new(WebSearchRouter)
        out = r._execute({"query": "test query"}, ToolContext())
        assert "test query" in out
        assert "Mock result" in out
        assert "[" in out and "](" in out  # markdown link

    def test_num_results_respected(self, monkeypatch):
        monkeypatch.setenv("OMNI_WEB_SEARCH_DRY_RUN", "1")
        r = _new(WebSearchRouter)
        out = r._execute({"query": "x", "num_results": 3}, ToolContext())
        # 数 mock 结果数量
        assert out.count("Mock result") == 3

    def test_blocked_domains_filter(self, monkeypatch):
        monkeypatch.setenv("OMNI_WEB_SEARCH_DRY_RUN", "1")
        r = _new(WebSearchRouter)
        out = r._execute({
            "query": "x",
            "num_results": 5,
            "blocked_domains": ["example.com"],
        }, ToolContext())
        # mock URLs 都是 example.com → 全被过滤
        assert "No web results" in out

    def test_allowed_domains_filter_pass(self, monkeypatch):
        monkeypatch.setenv("OMNI_WEB_SEARCH_DRY_RUN", "1")
        r = _new(WebSearchRouter)
        out = r._execute({
            "query": "x",
            "num_results": 5,
            "allowed_domains": ["example.com"],
        }, ToolContext())
        # mock URLs 都是 example.com → 全过
        assert "Mock result" in out

    def test_no_query_raises(self):
        r = _new(WebSearchRouter)
        with pytest.raises(ToolExecutionError, match="query is required"):
            r._execute({}, ToolContext())

    def test_invalid_num_results(self):
        r = _new(WebSearchRouter)
        with pytest.raises(ToolExecutionError, match="num_results"):
            r._execute({"query": "x", "num_results": 100}, ToolContext())

    def test_unknown_backend(self, monkeypatch):
        monkeypatch.setenv("OMNI_WEB_SEARCH_BACKEND", "unknown_xxx")
        # 确保不在 dry_run
        monkeypatch.delenv("OMNI_WEB_SEARCH_DRY_RUN", raising=False)
        r = _new(WebSearchRouter)
        with pytest.raises(ToolExecutionError, match="unknown backend"):
            r._execute({"query": "x"}, ToolContext())


# ═══════════════════════════════════════════════════════════════════════
# WebSearch 真 DuckDuckGo (network marker, 默认 skip)
# ═══════════════════════════════════════════════════════════════════════


class TestWebSearchRealNetwork:
    @pytest.mark.skipif(
        not os.environ.get("OMNI_WEB_NETWORK_TEST"),
        reason="real network test skipped by default. Set OMNI_WEB_NETWORK_TEST=1 to run.",
    )
    def test_duckduckgo_returns_results(self):
        r = _new(WebSearchRouter)
        out = r._execute({"query": "Python programming language", "num_results": 3}, ToolContext())
        # 有结果 (rate limit 时可能 empty)
        assert "Search results for" in out or "No web results" in out
