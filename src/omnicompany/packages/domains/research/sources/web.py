# [OMNI] origin=ai-ide domain=research/sources ts=2026-06-14T00:00:00Z type=source status=active
# [OMNI] summary="web 取数源:搜索(tavily/serper/ddg 自动按 key 选)+ 带 SSRF 守卫的抓取。失败可观测(日志,不静默)。"
# [OMNI] why="单一权威:搜索逻辑复用 WebSearchRouter 后端;抓取自带守卫(拒私网/环回/元数据+逐跳校验重定向),因 research 把不可信搜索结果/LLM产URL自动批量抓,是 SSRF 高发面。"
# [OMNI] tags=research,web,search,fetch,ssrf,reuse
"""web 取数源 —— 搜索(薄封装复用 WebSearchRouter)+ 带守卫的抓取。

搜索后端: OMNI_WEB_SEARCH_BACKEND 显式优先,否则按 key 自动 tavily>serper>ddg(免费 DDG 抓取已死)。
OMNI_WEB_SEARCH_DRY_RUN=1 离线 mock,供测通管线。
抓取自带 SSRF 守卫: 拒绝解析到私网/环回/链路本地/元数据地址、非 80/443 端口,并逐跳校验重定向落地。
失败走 logger.warning(不记 key),不再静默退化成"搜不到/抓不到"难定位。
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT = 30
_FETCH_MAX_BYTES = 500_000
_USER_AGENT = "OmniCompany-Research-WebFetch/1.0"


class _NoopBus:
    """占位 bus:SingleToolRouter init 硬要 bus!=None,但本封装不走 emit 审计路径。"""

    async def publish(self, event: Any) -> str:  # noqa: D401
        return "noop"

    def emit(self, *a: Any, **kw: Any) -> None:
        pass


# ── 搜索 ──────────────────────────────────────────────────────────────────
def _resolve_backend() -> str:
    """后端选择: 显式 env 优先;否则按 key 自动选 tavily>serper>duckduckgo。"""
    backend = os.environ.get("OMNI_WEB_SEARCH_BACKEND", "").lower()
    if backend:
        return backend
    if os.environ.get("TAVILY_API_KEY", "").strip():
        return "tavily"
    if os.environ.get("SERPER_API_KEY", "").strip():
        return "serper"
    return "duckduckgo"


def _search_tavily(query: str, num: int) -> list[dict]:
    """Tavily Search API(AI 原生检索,content 即 LLM 友好摘要)。"""
    import json
    import urllib.request

    key = os.environ.get("TAVILY_API_KEY", "").strip()
    payload = json.dumps({
        "api_key": key, "query": query, "max_results": min(max(1, num), 10),
        "search_depth": "basic",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.tavily.com/search", data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""),
         "snippet": r.get("content", ""), "raw_content": r.get("raw_content") or ""}
        for r in (data.get("results") or [])
    ]


def web_search(query: str, num: int = 8) -> list[dict]:
    """搜一个 query,返 [{title,url,snippet}]。后端 tavily/serper/duckduckgo 自动按 key 选。"""
    if os.environ.get("OMNI_WEB_SEARCH_DRY_RUN") == "1":
        return [
            {"title": f"Mock {i+1} · {query}", "url": f"https://example.com/{abs(hash(query)) % 9999}-{i+1}",
             "snippet": f"mock snippet {i+1} for {query}"}
            for i in range(min(num, 5))
        ]
    backend = _resolve_backend()
    try:
        if backend == "tavily":
            return _search_tavily(query, num)
        from omnicompany.packages.services._core.agent.routers.web_search import WebSearchRouter
        router = WebSearchRouter(bus=_NoopBus())
        if backend == "serper":
            return router._search_serper(query, num)
        return router._search_duckduckgo(query, num)
    except Exception as exc:  # noqa: BLE001 — 不炸管线;但要可观测(不记 key,只记类型/后端)
        logger.warning("web_search 失败 backend=%s err=%s: %r", backend, type(exc).__name__, str(exc)[:200])
        return []


# ── 抓取(带 SSRF 守卫)─────────────────────────────────────────────────────
def _ip_blocked(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # 解析不出的当不安全
    return bool(
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        or ip.is_multicast or ip.is_unspecified or str(ip) == "169.254.169.254"
    )


def _url_safe(url: str) -> bool:
    """URL 是否可安全抓取: http(s) + 端口 80/443 + host 解析的所有 IP 均为公网。"""
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    if p.port not in (None, 80, 443):
        return False
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    if not infos:
        return False
    return all(not _ip_blocked(info[4][0]) for info in infos)


class _GuardedRedirect(HTTPRedirectHandler):
    """逐跳校验重定向落地 host,挡住"公网页 302 到内网/元数据"的 SSRF。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        if not _url_safe(newurl):
            raise URLError(f"blocked unsafe redirect target: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def web_fetch(url: str, max_chars: int = 6000) -> str:
    """抓一个 url 转干净正文(截断)。带 SSRF 守卫;失败/被挡返空串并记日志。

    注: host→IP 校验与实际连接间存在 DNS rebinding 残留窗口,本场景(自动调研抓公开页)可接受。
    """
    if os.environ.get("OMNI_WEB_SEARCH_DRY_RUN") == "1":
        return f"[mock body for {url}] " + ("内容片段。" * 20)
    if not _url_safe(url):
        logger.warning("web_fetch 拒绝不安全 url(私网/环回/元数据/非80-443): %r", url[:200])
        return ""
    try:
        opener = build_opener(_GuardedRedirect)
        req = Request(url, headers={"User-Agent": _USER_AGENT})
        with opener.open(req, timeout=_FETCH_TIMEOUT) as resp:
            ctype = (resp.headers.get("Content-Type", "") or "").lower()
            raw = resp.read(_FETCH_MAX_BYTES)
    except Exception as exc:  # noqa: BLE001
        logger.warning("web_fetch 失败 err=%s: %r", type(exc).__name__, str(exc)[:200])
        return ""

    charset = "utf-8"
    if "charset=" in ctype:
        charset = ctype.split("charset=")[-1].split(";")[0].strip() or "utf-8"
    try:
        body = raw.decode(charset, errors="replace")
    except LookupError:
        body = raw.decode("utf-8", errors="replace")

    if "html" in ctype:
        # 复用上游的块级 HTML→text 抽取(同包,稳定),失败回退原文
        try:
            from omnicompany.packages.services._core.agent.routers.web_fetch import _TextExtractor
            ex = _TextExtractor()
            ex.feed(body)
            body = ex.extract()
        except Exception:  # noqa: BLE001
            pass
    return body[:max_chars]
