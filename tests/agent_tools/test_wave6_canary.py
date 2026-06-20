"""第六波工具 canary 测试 (2026-05-04 立).

覆盖:
  - ScheduleCronRouter: create / list / delete / run_now / 校验
  - MonitorRouter: 干跑模式
  - RemoteTriggerRouter: 写 trigger 文件
  - PushNotificationRouter: 写 notification 文件
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
from omnicompany.packages.services._core.agent.routers.cron_tools import ScheduleCronRouter
from omnicompany.packages.services._core.agent.routers.event_tools import (
    MonitorRouter,
    RemoteTriggerRouter,
    PushNotificationRouter,
)


def _new(cls):
    return cls.__new__(cls)


# ─── ScheduleCronRouter ──────────────────────────────────────────


class TestCronCanary:
    def test_create_and_list(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(ScheduleCronRouter)
        out = r._execute({
            "action": "create",
            "name": "nightly",
            "schedule": "@daily",
            "command": "echo hi",
            "description": "nightly echo",
        }, ctx)
        assert "Created" in out
        assert (tmp_path / ".omni" / "cron" / "nightly.json").exists()

        # list
        out = r._execute({"action": "list"}, ctx)
        assert "nightly" in out

    def test_invalid_schedule(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(ScheduleCronRouter)
        with pytest.raises(ToolExecutionError, match="invalid cron"):
            r._execute({
                "action": "create", "name": "x",
                "schedule": "every 5 minutes",  # 非法
                "command": "echo",
            }, ctx)

    def test_create_already_exists(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(ScheduleCronRouter)
        r._execute({
            "action": "create", "name": "dup",
            "schedule": "@hourly", "command": "echo",
        }, ctx)
        with pytest.raises(ToolExecutionError, match="already exists"):
            r._execute({
                "action": "create", "name": "dup",
                "schedule": "@hourly", "command": "echo",
            }, ctx)

    def test_update_existing(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(ScheduleCronRouter)
        r._execute({"action": "create", "name": "u", "schedule": "@hourly", "command": "echo"}, ctx)
        out = r._execute({"action": "update", "name": "u", "description": "updated"}, ctx)
        assert "Updated" in out
        data = json.loads((tmp_path / ".omni" / "cron" / "u.json").read_text(encoding="utf-8"))
        assert data["description"] == "updated"

    def test_delete(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(ScheduleCronRouter)
        r._execute({"action": "create", "name": "rm", "schedule": "@daily", "command": "x"}, ctx)
        out = r._execute({"action": "delete", "name": "rm"}, ctx)
        assert "Deleted" in out
        assert not (tmp_path / ".omni" / "cron" / "rm.json").exists()

    def test_run_now(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(ScheduleCronRouter)
        r._execute({"action": "create", "name": "trig", "schedule": "@daily", "command": "x"}, ctx)
        out = r._execute({"action": "run_now", "name": "trig"}, ctx)
        assert "Triggered" in out
        # trigger 标记文件
        assert (tmp_path / ".omni" / "cron" / "trig.trigger").exists()


# ─── MonitorRouter ───────────────────────────────────────────────


class TestMonitorCanary:
    def test_dry_run(self, monkeypatch):
        monkeypatch.setenv("OMNI_MONITOR_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(MonitorRouter)
        out = r._execute({"mode": "process", "command": "echo hi"}, ctx)
        data = json.loads(out)
        assert data["dry_run"] is True
        assert "lines" in data

    def test_invalid_mode(self):
        ctx = ToolContext()
        r = _new(MonitorRouter)
        with pytest.raises(ToolExecutionError, match="mode"):
            r._execute({"mode": "fly"}, ctx)

    def test_process_requires_command(self):
        ctx = ToolContext()
        r = _new(MonitorRouter)
        with pytest.raises(ToolExecutionError, match="command"):
            r._execute({"mode": "process"}, ctx)

    def test_real_short_process(self):
        """真跑短命令收集 stdout."""
        ctx = ToolContext()
        r = _new(MonitorRouter)
        # cross-platform: Python -c
        out = r._execute({
            "mode": "process",
            "command": "python -c \"print('alpha'); print('beta')\"",
            "max_lines": 10,
            "timeout_sec": 10,
        }, ctx)
        data = json.loads(out)
        assert "alpha" in str(data["lines"])
        assert "beta" in str(data["lines"])


# ─── RemoteTriggerRouter ─────────────────────────────────────────


class TestRemoteTriggerCanary:
    def test_basic(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(RemoteTriggerRouter)
        out = r._execute({"name": "ci-rebuild", "payload": {"branch": "main"}}, ctx)
        assert "fired" in out.lower()
        files = list((tmp_path / ".omni" / "triggers").glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["name"] == "ci-rebuild"
        assert data["payload"]["branch"] == "main"

    def test_unsafe_name(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(RemoteTriggerRouter)
        with pytest.raises(ToolExecutionError, match="filesystem-safe"):
            r._execute({"name": "bad/name"}, ctx)

    def test_no_name(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(RemoteTriggerRouter)
        with pytest.raises(ToolExecutionError, match="name"):
            r._execute({}, ctx)


# ─── PushNotificationRouter ──────────────────────────────────────


class TestPushNotificationCanary:
    def test_basic(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(PushNotificationRouter)
        out = r._execute({
            "title": "Build done",
            "message": "All tests passed",
            "severity": "info",
        }, ctx)
        assert "sent" in out.lower()
        files = list((tmp_path / ".omni" / "notifications").glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["title"] == "Build done"
        assert data["severity"] == "info"

    def test_invalid_severity(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(PushNotificationRouter)
        with pytest.raises(ToolExecutionError, match="severity"):
            r._execute({
                "title": "x",
                "message": "y",
                "severity": "extreme",
            }, ctx)

    def test_required_fields(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(PushNotificationRouter)
        with pytest.raises(ToolExecutionError, match="title"):
            r._execute({"message": "x"}, ctx)
        with pytest.raises(ToolExecutionError, match="message"):
            r._execute({"title": "x"}, ctx)


# ─── Schema ──────────────────────────────────────────────────────


class TestWave6Schemas:
    @pytest.mark.parametrize("router_cls,expected", [
        (ScheduleCronRouter, "ScheduleCron"),
        (MonitorRouter, "Monitor"),
        (RemoteTriggerRouter, "RemoteTrigger"),
        (PushNotificationRouter, "PushNotification"),
    ])
    def test_tool_names(self, router_cls, expected):
        assert router_cls.TOOL_NAME == expected
        assert router_cls.DESCRIPTION
        assert "properties" in router_cls.INPUT_SCHEMA
