"""第八波辅助工具 canary 测试 (2026-05-04 立)."""

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
from omnicompany.packages.services._core.agent.routers.aux_tools import (
    SnipRouter,
    TerminalCaptureRouter,
    BriefRouter,
    CtxInspectRouter,
    LSPRouter,
)


def _new(cls):
    return cls.__new__(cls)


# ─── SnipRouter ──────────────────────────────────────────────────


class TestSnipCanary:
    def test_save_get_list_delete(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(SnipRouter)

        r._execute({"operation": "save", "name": "k1", "content": "hello"}, ctx)
        out = r._execute({"operation": "get", "name": "k1"}, ctx)
        assert out == "hello"

        out = r._execute({"operation": "list"}, ctx)
        assert "k1" in out

        r._execute({"operation": "delete", "name": "k1"}, ctx)
        with pytest.raises(ToolExecutionError, match="not found"):
            r._execute({"operation": "get", "name": "k1"}, ctx)

    def test_unsafe_name(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(SnipRouter)
        with pytest.raises(ToolExecutionError, match="filesystem-safe"):
            r._execute({"operation": "save", "name": "../escape", "content": "x"}, ctx)


# ─── TerminalCaptureRouter ───────────────────────────────────────


class TestTerminalCaptureCanary:
    def test_scrollback(self, tmp_path):
        log = tmp_path / "log.txt"
        log.write_text("\n".join(f"line{i}" for i in range(50)))
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(TerminalCaptureRouter)
        out = r._execute({"mode": "scrollback", "log_path": str(log), "max_lines": 5}, ctx)
        lines = out.split("\n")
        assert len(lines) == 5
        assert "line49" in lines[-1]

    def test_invalid_mode(self):
        ctx = ToolContext()
        r = _new(TerminalCaptureRouter)
        with pytest.raises(ToolExecutionError, match="mode"):
            r._execute({"mode": "magic"}, ctx)

    def test_screenshot_dry_run(self, monkeypatch):
        monkeypatch.setenv("OMNI_TERMINAL_CAPTURE_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(TerminalCaptureRouter)
        out = r._execute({"mode": "screenshot", "out_path": "/tmp/x.png"}, ctx)
        data = json.loads(out)
        assert "mock screenshot" in data["result"]


# ─── BriefRouter ─────────────────────────────────────────────────


class TestBriefCanary:
    def test_send(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(BriefRouter)
        out = r._execute({"message": "Build done", "status": "normal"}, ctx)
        assert "Brief sent" in out
        files = list((tmp_path / ".omni" / "user_briefs").glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["message"] == "Build done"

    def test_invalid_status(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(BriefRouter)
        with pytest.raises(ToolExecutionError, match="status"):
            r._execute({"message": "x", "status": "urgent"}, ctx)


# ─── CtxInspectRouter ───────────────────────────────────────────


class TestCtxInspectCanary:
    def test_basic_fields(self):
        ctx = ToolContext(
            cwd="/test/cwd",
            project_root="/test/proj",
            turn_number=5,
        )
        r = _new(CtxInspectRouter)
        out = r._execute({}, ctx)
        data = json.loads(out)
        assert data["cwd"] == "/test/cwd"
        assert data["project_root"] == "/test/proj"
        assert data["turn_number"] == 5

    def test_custom_fields_included(self):
        ctx = ToolContext(cwd="/x", project_root="/x")
        ctx.allowed_write_paths = ("/foo", "/bar")  # type: ignore[attr-defined]
        r = _new(CtxInspectRouter)
        out = r._execute({}, ctx)
        data = json.loads(out)
        assert "allowed_write_paths" in data
        # tuple → JSON list
        assert "/foo" in str(data["allowed_write_paths"])

    def test_non_serializable_safe(self):
        ctx = ToolContext()

        class X:
            pass

        ctx.weird_obj = X()  # type: ignore[attr-defined]
        r = _new(CtxInspectRouter)
        out = r._execute({}, ctx)
        data = json.loads(out)
        assert data["weird_obj"] == "<X>"


# ─── LSPRouter ──────────────────────────────────────────────────


class TestLSPCanary:
    def test_non_python_skipped(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("not python")
        ctx = ToolContext()
        r = _new(LSPRouter)
        out = r._execute({"action": "diagnose", "file_path": str(f)}, ctx)
        data = json.loads(out)
        assert data["diagnostics"] == []

    def test_missing_file(self, tmp_path):
        ctx = ToolContext()
        r = _new(LSPRouter)
        with pytest.raises(ToolExecutionError, match="does not exist"):
            r._execute({"action": "diagnose", "file_path": str(tmp_path / "ghost.py")}, ctx)

    def test_invalid_action(self):
        ctx = ToolContext()
        r = _new(LSPRouter)
        with pytest.raises(ToolExecutionError, match="diagnose"):
            r._execute({"action": "rename", "file_path": "/x.py"}, ctx)


# ─── Schema ─────────────────────────────────────────────────────


class TestWave8Schemas:
    @pytest.mark.parametrize("router_cls,expected", [
        (SnipRouter, "Snip"),
        (TerminalCaptureRouter, "TerminalCapture"),
        (BriefRouter, "Brief"),
        (CtxInspectRouter, "CtxInspect"),
        (LSPRouter, "LSP"),
    ])
    def test_tool_names(self, router_cls, expected):
        assert router_cls.TOOL_NAME == expected
        assert router_cls.DESCRIPTION
        assert "properties" in router_cls.INPUT_SCHEMA
