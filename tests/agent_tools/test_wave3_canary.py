"""第三波工具 canary 测试 (2026-05-04 立).

覆盖:
  - TodoWriteRouter: 校验 + 落盘 + in_progress 单例
  - AskUserQuestionRouter: 干跑模式 + 校验
  - SleepRouter: 干跑 instant 模式 + 上限边界
  - ConfigToolRouter: list / get / set + secret 拒绝 + 白名单
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
from omnicompany.packages.services._core.agent.routers.todo_write import TodoWriteRouter
from omnicompany.packages.services._core.agent.routers.ask_user_question import (
    AskUserQuestionRouter,
)
from omnicompany.packages.services._core.agent.routers.sleep import SleepRouter
from omnicompany.packages.services._core.agent.routers.config_tool import ConfigToolRouter


def _new(cls):
    return cls.__new__(cls)


# ─── TodoWriteRouter ──────────────────────────────────────────────


class TestTodoWriteCanary:
    def test_basic_create(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(TodoWriteRouter)
        out = r._execute({
            "todos": [
                {"content": "Run tests", "activeForm": "Running tests", "status": "in_progress"},
                {"content": "Build docs", "activeForm": "Building docs", "status": "pending"},
            ],
        }, ctx)
        assert "Todos updated" in out
        # 落盘
        f = tmp_path / ".omni" / "agent_todos.json"
        assert f.exists()
        data = json.loads(f.read_text(encoding="utf-8"))
        assert len(data["todos"]) == 2

    def test_multiple_in_progress_rejected(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(TodoWriteRouter)
        with pytest.raises(ToolExecutionError, match="ONE todo"):
            r._execute({
                "todos": [
                    {"content": "A", "activeForm": "Aing", "status": "in_progress"},
                    {"content": "B", "activeForm": "Bing", "status": "in_progress"},
                ],
            }, ctx)

    def test_invalid_status_rejected(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(TodoWriteRouter)
        with pytest.raises(ToolExecutionError, match="status must be"):
            r._execute({
                "todos": [{"content": "X", "activeForm": "Xing", "status": "in_flight"}],
            }, ctx)

    def test_missing_content_rejected(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(TodoWriteRouter)
        with pytest.raises(ToolExecutionError, match="content"):
            r._execute({
                "todos": [{"activeForm": "Xing", "status": "pending"}],
            }, ctx)

    def test_empty_list_clears(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(TodoWriteRouter)
        out = r._execute({"todos": []}, ctx)
        assert "cleared" in out.lower()


# ─── AskUserQuestionRouter ────────────────────────────────────────


class TestAskUserQuestionCanary:
    def test_dry_run_returns_first_option(self, monkeypatch):
        monkeypatch.setenv("ASK_USER_QUESTION_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(AskUserQuestionRouter)
        out = r._execute({
            "question": "选哪个?",
            "options": [
                {"label": "甲", "description": "选甲"},
                {"label": "乙", "description": "选乙"},
            ],
        }, ctx)
        data = json.loads(out)
        assert data["answer"] == "甲"
        assert data["mode"] == "dry_run"

    def test_too_few_options(self):
        ctx = ToolContext()
        r = _new(AskUserQuestionRouter)
        with pytest.raises(ToolExecutionError, match="at least 2"):
            r._execute({
                "question": "x?",
                "options": [{"label": "only"}],
            }, ctx)

    def test_missing_label(self):
        ctx = ToolContext()
        r = _new(AskUserQuestionRouter)
        with pytest.raises(ToolExecutionError, match="label"):
            r._execute({
                "question": "x?",
                "options": [{"description": "no label"}, {"label": "ok"}],
            }, ctx)

    def test_no_human_bus_no_dry_run(self):
        """无 HumanBus + 无干跑模式 → 错误指引."""
        ctx = ToolContext()
        r = _new(AskUserQuestionRouter)
        with pytest.raises(ToolExecutionError, match="HumanBus"):
            r._execute({
                "question": "x?",
                "options": [{"label": "a"}, {"label": "b"}],
            }, ctx)


# ─── SleepRouter ──────────────────────────────────────────────────


class TestSleepCanary:
    def test_instant_mode(self, monkeypatch):
        monkeypatch.setenv("SLEEP_TOOL_INSTANT", "1")
        ctx = ToolContext()
        r = _new(SleepRouter)
        out = r._execute({"seconds": 100, "reason": "test"}, ctx)
        assert "100" in out
        assert "instant" in out

    def test_max_seconds_rejected(self):
        ctx = ToolContext()
        r = _new(SleepRouter)
        with pytest.raises(ToolExecutionError, match="<="):
            r._execute({"seconds": 10000}, ctx)

    def test_negative_rejected(self):
        ctx = ToolContext()
        r = _new(SleepRouter)
        with pytest.raises(ToolExecutionError, match=">= 0"):
            r._execute({"seconds": -1}, ctx)

    def test_real_short_sleep(self):
        """真睡 0.05 秒, 验证不挂."""
        import time
        ctx = ToolContext()
        r = _new(SleepRouter)
        t0 = time.time()
        out = r._execute({"seconds": 0.05}, ctx)
        elapsed = time.time() - t0
        assert elapsed >= 0.04, f"实际未睡 (elapsed={elapsed})"
        assert "Slept" in out


# ─── ConfigToolRouter ─────────────────────────────────────────────


class TestConfigCanary:
    def test_list_keys(self, tmp_path):
        cfg = tmp_path / "config" / "global.yaml"
        cfg.parent.mkdir()
        cfg.write_text("a: 1\nb:\n  c: 2\n", encoding="utf-8")
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(ConfigToolRouter)
        out = r._execute({"operation": "list"}, ctx)
        assert "a" in out and "b" in out

    def test_get_simple(self, tmp_path):
        cfg = tmp_path / "config" / "global.yaml"
        cfg.parent.mkdir()
        cfg.write_text("model: qwen-3.6-plus\n", encoding="utf-8")
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(ConfigToolRouter)
        out = r._execute({"operation": "get", "key": "model"}, ctx)
        assert out == "qwen-3.6-plus"

    def test_get_dotted(self, tmp_path):
        cfg = tmp_path / "config" / "global.yaml"
        cfg.parent.mkdir()
        cfg.write_text("llm:\n  model: x\n  temp: 0.5\n", encoding="utf-8")
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(ConfigToolRouter)
        out = r._execute({"operation": "get", "key": "llm.model"}, ctx)
        assert out == "x"

    def test_get_missing_key(self, tmp_path):
        cfg = tmp_path / "config" / "global.yaml"
        cfg.parent.mkdir()
        cfg.write_text("a: 1\n", encoding="utf-8")
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(ConfigToolRouter)
        with pytest.raises(ToolExecutionError, match="not found"):
            r._execute({"operation": "get", "key": "missing"}, ctx)

    def test_set_without_allowlist_refused(self, tmp_path):
        cfg = tmp_path / "config" / "global.yaml"
        cfg.parent.mkdir()
        cfg.write_text("a: 1\n", encoding="utf-8")
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(ConfigToolRouter)
        with pytest.raises(ToolExecutionError, match="REFUSED"):
            r._execute({"operation": "set", "key": "a", "value": 2}, ctx)

    def test_set_with_allowlist(self, tmp_path):
        cfg = tmp_path / "config" / "global.yaml"
        cfg.parent.mkdir()
        cfg.write_text("a: 1\n", encoding="utf-8")
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        ctx.allowed_config_targets = (str(cfg),)
        r = _new(ConfigToolRouter)
        out = r._execute({"operation": "set", "key": "a", "value": 99}, ctx)
        assert "Set" in out
        # 验证落盘
        import yaml
        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert data["a"] == 99

    def test_secret_path_refused(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(ConfigToolRouter)
        with pytest.raises(ToolExecutionError, match="secret"):
            r._execute({
                "operation": "get",
                "key": "x",
                "config_file": ".env",
            }, ctx)


# ─── 集成: schema 完整性 ──────────────────────────────────────────


class TestWave3Schemas:
    @pytest.mark.parametrize("router_cls,expected_name", [
        (TodoWriteRouter, "TodoWrite"),
        (AskUserQuestionRouter, "AskUserQuestion"),
        (SleepRouter, "Sleep"),
        (ConfigToolRouter, "Config"),
    ])
    def test_tool_names(self, router_cls, expected_name):
        assert router_cls.TOOL_NAME == expected_name
        assert router_cls.DESCRIPTION
        assert "properties" in router_cls.INPUT_SCHEMA
