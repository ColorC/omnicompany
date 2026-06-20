"""第四波工具 canary 测试 (2026-05-04 立).

覆盖:
  - WebSearchRouter: 干跑模式 + 校验 + domain filter
  - WebBrowserRouter: 干跑模式 + 校验 + action 边界
  - VerifyPlanExecutionRouter: 干跑静态勾扫 + LLM 调用降级
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.agent.routers.single_tool import (
    ToolContext,
    ToolExecutionError,
)
from omnicompany.packages.services._core.agent.routers.web_search import WebSearchRouter
from omnicompany.packages.services._core.agent.routers.web_browser import WebBrowserRouter
from omnicompany.packages.services._core.agent.routers.verify_plan_execution import (
    VerifyPlanExecutionRouter,
)


def _new(cls):
    return cls.__new__(cls)


# ─── WebSearchRouter ──────────────────────────────────────────────


class TestWebSearchCanary:
    def test_dry_run(self, monkeypatch):
        monkeypatch.setenv("OMNI_WEB_SEARCH_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(WebSearchRouter)
        out = r._execute({"query": "omnicompany"}, ctx)
        assert "omnicompany" in out
        assert "Mock result 1" in out

    def test_query_required(self):
        ctx = ToolContext()
        r = _new(WebSearchRouter)
        with pytest.raises(ToolExecutionError, match="query"):
            r._execute({}, ctx)

    def test_num_results_clamp(self):
        ctx = ToolContext()
        r = _new(WebSearchRouter)
        with pytest.raises(ToolExecutionError, match="num_results"):
            r._execute({"query": "x", "num_results": 1000}, ctx)

    def test_domain_filter(self, monkeypatch):
        monkeypatch.setenv("OMNI_WEB_SEARCH_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(WebSearchRouter)
        # mock 返 example.com 域名 → blocked_domains 应排除
        out = r._execute({
            "query": "x", "blocked_domains": ["example.com"], "num_results": 5,
        }, ctx)
        # 全 mock 是 example.com → 全被 block → "no web results"
        assert "No web results" in out

    def test_unknown_backend_rejected(self, monkeypatch):
        monkeypatch.setenv("OMNI_WEB_SEARCH_BACKEND", "google")
        ctx = ToolContext()
        r = _new(WebSearchRouter)
        with pytest.raises(ToolExecutionError, match="backend"):
            r._execute({"query": "x"}, ctx)


# ─── WebBrowserRouter ─────────────────────────────────────────────


class TestWebBrowserCanary:
    def test_dry_run_navigate(self, monkeypatch):
        monkeypatch.setenv("OMNI_WEB_BROWSER_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(WebBrowserRouter)
        out = r._execute({
            "action": "navigate",
            "url": "https://example.com",
        }, ctx)
        data = json.loads(out)
        assert data["mode"] == "dry_run"
        assert data["action"] == "navigate"

    def test_invalid_action(self):
        ctx = ToolContext()
        r = _new(WebBrowserRouter)
        with pytest.raises(ToolExecutionError, match="action"):
            r._execute({"action": "fly"}, ctx)

    def test_dry_run_click(self, monkeypatch):
        monkeypatch.setenv("OMNI_WEB_BROWSER_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(WebBrowserRouter)
        out = r._execute({
            "action": "click",
            "selector": "button.submit",
        }, ctx)
        data = json.loads(out)
        assert data["action"] == "click"
        assert "submit" in data["args"]["selector"]


# ─── VerifyPlanExecutionRouter ────────────────────────────────────


class TestVerifyPlanExecutionCanary:
    def test_dry_run_static_scan(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OMNI_VERIFY_PLAN_DRY_RUN", "1")
        plan = tmp_path / "plan.md"
        plan.write_text(
            "# plan\n"
            "\n"
            "- [x] First task\n"
            "- [x] Second task\n"
            "- [ ] Third task\n"
            "- [ ] Fourth task\n",
            encoding="utf-8",
        )
        ctx = ToolContext()
        r = _new(VerifyPlanExecutionRouter)
        out = r._execute({
            "plan_path": str(plan),
            "evidence": "irrelevant in dry-run",
        }, ctx)
        data = json.loads(out)
        assert len(data["verified_done"]) == 2
        assert len(data["still_pending"]) == 2
        # 内容
        items_done = [v["item"] for v in data["verified_done"]]
        assert "First task" in items_done
        assert "Second task" in items_done

    def test_relative_path_rejected(self, monkeypatch):
        monkeypatch.setenv("OMNI_VERIFY_PLAN_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(VerifyPlanExecutionRouter)
        with pytest.raises(ToolExecutionError, match="absolute"):
            r._execute({
                "plan_path": "relative/plan.md",
                "evidence": "x",
            }, ctx)

    def test_missing_plan_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OMNI_VERIFY_PLAN_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(VerifyPlanExecutionRouter)
        with pytest.raises(ToolExecutionError, match="does not exist"):
            r._execute({
                "plan_path": str(tmp_path / "ghost.md"),
                "evidence": "x",
            }, ctx)

    def test_empty_evidence_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OMNI_VERIFY_PLAN_DRY_RUN", "1")
        plan = tmp_path / "plan.md"
        plan.write_text("- [x] x", encoding="utf-8")
        ctx = ToolContext()
        r = _new(VerifyPlanExecutionRouter)
        with pytest.raises(ToolExecutionError, match="evidence"):
            r._execute({
                "plan_path": str(plan),
                "evidence": "",
            }, ctx)


# ─── 集成 schema ─────────────────────────────────────────────────


class TestWave4Schemas:
    @pytest.mark.parametrize("router_cls,expected", [
        (WebSearchRouter, "WebSearch"),
        (WebBrowserRouter, "WebBrowser"),
        (VerifyPlanExecutionRouter, "VerifyPlanExecution"),
    ])
    def test_tool_names(self, router_cls, expected):
        assert router_cls.TOOL_NAME == expected
        assert router_cls.DESCRIPTION
        assert "properties" in router_cls.INPUT_SCHEMA
