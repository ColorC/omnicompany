"""第九波工具 canary 测试 (2026-05-04 立)."""

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
from omnicompany.packages.services._core.agent.routers.mcp_tools import (
    MCPRouter,
    McpAuthRouter,
    ListMcpResourcesRouter,
    ReadMcpResourceRouter,
    ListPeersRouter,
)
from omnicompany.packages.services._core.agent.routers.shell_alt_tools import (
    PowerShellRouter,
    REPLRouter,
)
from omnicompany.packages.services._core.agent.routers.testing_tools import (
    OverflowTestRouter,
    SyntheticOutputRouter,
)


def _new(cls):
    return cls.__new__(cls)


# ─── MCP 套件 ────────────────────────────────────────────────────


class TestMCPCanary:
    def test_mcp_dry_run(self, monkeypatch):
        monkeypatch.setenv("OMNI_MCP_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(MCPRouter)
        out = r._execute({"server": "fs", "tool": "read", "params": {"path": "/x"}}, ctx)
        data = json.loads(out)
        assert data["dry_run"] is True

    def test_mcp_no_client_no_dry_run(self):
        ctx = ToolContext()
        r = _new(MCPRouter)
        with pytest.raises(ToolExecutionError, match="mcp_client"):
            r._execute({"server": "fs", "tool": "x"}, ctx)

    def test_mcp_required_fields(self, monkeypatch):
        monkeypatch.setenv("OMNI_MCP_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(MCPRouter)
        with pytest.raises(ToolExecutionError, match="server"):
            r._execute({"tool": "x"}, ctx)
        with pytest.raises(ToolExecutionError, match="tool"):
            r._execute({"server": "x"}, ctx)

    def test_auth_actions(self, monkeypatch):
        monkeypatch.setenv("OMNI_MCP_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(McpAuthRouter)
        out = r._execute({"server": "x", "action": "start"}, ctx)
        assert json.loads(out)["dry_run"] is True

    def test_auth_invalid_action(self, monkeypatch):
        monkeypatch.setenv("OMNI_MCP_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(McpAuthRouter)
        with pytest.raises(ToolExecutionError, match="action"):
            r._execute({"server": "x", "action": "purge"}, ctx)

    def test_list_resources_dry_run(self, monkeypatch):
        monkeypatch.setenv("OMNI_MCP_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(ListMcpResourcesRouter)
        out = r._execute({"server": "x"}, ctx)
        data = json.loads(out)
        assert data["dry_run"] is True
        assert "resources" in data

    def test_read_resource_dry_run(self, monkeypatch):
        monkeypatch.setenv("OMNI_MCP_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(ReadMcpResourceRouter)
        out = r._execute({"server": "x", "uri": "mock://r"}, ctx)
        data = json.loads(out)
        assert data["dry_run"] is True


class TestListPeersCanary:
    def test_dry_run(self, monkeypatch):
        monkeypatch.setenv("OMNI_LIST_PEERS_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(ListPeersRouter)
        out = r._execute({}, ctx)
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_no_registry(self):
        ctx = ToolContext()
        r = _new(ListPeersRouter)
        with pytest.raises(ToolExecutionError, match="peer_registry"):
            r._execute({}, ctx)


# ─── PowerShell ─────────────────────────────────────────────────


class TestPowerShellCanary:
    def test_required(self):
        ctx = ToolContext()
        r = _new(PowerShellRouter)
        with pytest.raises(ToolExecutionError, match="command"):
            r._execute({}, ctx)

    def test_real_simple_command(self):
        """如果机器有 pwsh / powershell.exe, 跑一个简单命令."""
        import shutil
        if not (shutil.which("pwsh") or shutil.which("powershell.exe") or shutil.which("powershell")):
            pytest.skip("no pwsh / powershell on PATH")
        ctx = ToolContext()
        r = _new(PowerShellRouter)
        out = r._execute({"command": "Write-Output 'hello'"}, ctx)
        assert "hello" in out


# ─── REPL ───────────────────────────────────────────────────────


class TestREPLCanary:
    def test_state_persists(self):
        ctx = ToolContext()
        r = _new(REPLRouter)
        r._execute({"code": "x = 42"}, ctx)
        out = r._execute({"code": "print(x * 2)"}, ctx)
        assert "84" in out

    def test_reset_state(self):
        ctx = ToolContext()
        r = _new(REPLRouter)
        r._execute({"code": "y = 100"}, ctx)
        r._execute({"code": "print('placeholder')", "reset_state": True}, ctx)
        # y 不再存在
        out = r._execute({"code": "print(y)"}, ctx)
        assert "NameError" in out

    def test_capture_stdout(self):
        ctx = ToolContext()
        r = _new(REPLRouter)
        out = r._execute({"code": "print('hello')\nprint('world')"}, ctx)
        assert "hello" in out and "world" in out

    def test_exception_captured(self):
        ctx = ToolContext()
        r = _new(REPLRouter)
        out = r._execute({"code": "1/0"}, ctx)
        assert "ZeroDivisionError" in out

    def test_empty_code_rejected(self):
        ctx = ToolContext()
        r = _new(REPLRouter)
        with pytest.raises(ToolExecutionError, match="code"):
            r._execute({"code": ""}, ctx)


# ─── Testing 工具 ──────────────────────────────────────────────


class TestOverflowTestCanary:
    def test_lines_mode(self):
        ctx = ToolContext()
        r = _new(OverflowTestRouter)
        out = r._execute({"mode": "lines", "size": 5}, ctx)
        assert out.count("\n") == 4
        assert "line 5" in out

    def test_chars_mode(self):
        ctx = ToolContext()
        r = _new(OverflowTestRouter)
        out = r._execute({"mode": "chars", "size": 100}, ctx)
        assert len(out) == 100
        assert out == "x" * 100

    def test_json_mode(self):
        ctx = ToolContext()
        r = _new(OverflowTestRouter)
        out = r._execute({"mode": "json", "size": 3}, ctx)
        data = json.loads(out)
        assert len(data) == 3

    def test_size_clamp(self):
        ctx = ToolContext()
        r = _new(OverflowTestRouter)
        with pytest.raises(ToolExecutionError, match="size"):
            r._execute({"mode": "lines", "size": 99999999}, ctx)


class TestSyntheticOutputCanary:
    def test_json_valid(self):
        ctx = ToolContext()
        r = _new(SyntheticOutputRouter)
        out = r._execute({"pattern": "json_valid"}, ctx)
        data = json.loads(out)
        assert data["ok"] is True

    def test_json_malformed(self):
        ctx = ToolContext()
        r = _new(SyntheticOutputRouter)
        out = r._execute({"pattern": "json_malformed"}, ctx)
        # 故意是坏 JSON, 解析应抛异常
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)

    def test_markdown_table(self):
        ctx = ToolContext()
        r = _new(SyntheticOutputRouter)
        out = r._execute({"pattern": "markdown_table", "n_rows": 5}, ctx)
        assert "| col1 |" in out
        assert "| a4 |" in out

    def test_echo(self):
        ctx = ToolContext()
        r = _new(SyntheticOutputRouter)
        out = r._execute({"pattern": "echo", "body": "hello world"}, ctx)
        assert out == "hello world"

    def test_long_unicode(self):
        ctx = ToolContext()
        r = _new(SyntheticOutputRouter)
        out = r._execute({"pattern": "long_unicode"}, ctx)
        assert "你好世界" in out
        assert "🎉" in out

    def test_unknown_pattern(self):
        ctx = ToolContext()
        r = _new(SyntheticOutputRouter)
        with pytest.raises(ToolExecutionError, match="pattern"):
            r._execute({"pattern": "magic"}, ctx)


# ─── Schema ─────────────────────────────────────────────────────


class TestWave9Schemas:
    @pytest.mark.parametrize("router_cls,expected", [
        (MCPRouter, "MCP"),
        (McpAuthRouter, "McpAuth"),
        (ListMcpResourcesRouter, "ListMcpResources"),
        (ReadMcpResourceRouter, "ReadMcpResource"),
        (ListPeersRouter, "ListPeers"),
        (PowerShellRouter, "PowerShell"),
        (REPLRouter, "REPL"),
        (OverflowTestRouter, "OverflowTest"),
        (SyntheticOutputRouter, "SyntheticOutput"),
    ])
    def test_tool_names(self, router_cls, expected):
        assert router_cls.TOOL_NAME == expected
        assert router_cls.DESCRIPTION
        assert "properties" in router_cls.INPUT_SCHEMA
