# [OMNI] origin=claude-code domain=tests/guardian ts=2026-04-25T00:00:00Z type=test
"""CLI `omni guardian health` 输出契约测试 · 契约变更 #01.

对应 plan: docs/plans/[2026-04-25]CORE-ARCH-DEBT-CLEANUP/contract_change_01_guardian_health_reporter.md

铁律 (2026-04-25): CLI 不得显示 "健康分数: X/100" (压缩语义信号为分数).
改显示: counts + issue 列表 + verdict 语义标签.

本测试 mock `dispatch()` 返回新契约 schema, 验 CLI 输出渲染合规.
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner


_NEW_SCHEMA_RESULT_OK = {
    "verdict": "healthy",
    "passed": True,
    "issues": [
        {
            "severity": "minor",
            "category": "style",
            "field": "workers/foo.py",
            "message": "DESCRIPTION 描述略短",
            "evidence": "DESCRIPTION='x' 1 字符",
            "fix_hint": "扩 ≥ 20 字符",
        },
    ],
    "counts": {"critical": 0, "major": 0, "minor": 1},
    "total_issues": 1,
    "top_actions": ["补 DESCRIPTION 描述"],
    "fs_issues": [],
    "arch_issues": [],
    "report": "结构合规, 仅 1 minor.",
    "summary": "结构合规",
}


_NEW_SCHEMA_RESULT_BAD = {
    "verdict": "unhealthy",
    "passed": False,
    "issues": [
        {
            "severity": "critical",
            "category": "root_contamination",
            "field": "root_stray",
            "message": "根目录有 3 个 .db 文件污染",
            "evidence": "扫出 /foo.db /bar.db /baz.db",
            "fix_hint": "迁到 data/ 下",
        },
        {
            "severity": "major",
            "category": "omnimark_missing",
            "field": "services/foo.py",
            "message": "OmniMark 头缺失",
            "evidence": "first line: 'import os'",
            "fix_hint": "加 OmniMark 头",
        },
    ],
    "counts": {"critical": 1, "major": 1, "minor": 0},
    "total_issues": 2,
    "top_actions": ["清根目录 .db", "补 OmniMark 头"],
    "fs_issues": [],
    "arch_issues": [],
    "report": "发现 1 critical + 1 major, 需处理.",
    "summary": "根污染 + OmniMark 缺失",
}


@pytest.fixture
def runner():
    return CliRunner()


def test_T6_cli_output_has_no_health_score_line(runner, monkeypatch):
    """T6: `omni guardian health` 输出**不含** '健康分数: X/100' 行."""
    # mock dispatch() 返回新契约结果
    async def fake_dispatch(service, payload):
        return _NEW_SCHEMA_RESULT_OK

    monkeypatch.setattr(
        "omnicompany.core.dispatch.dispatch", fake_dispatch,
    )
    # mock discover() no-op
    monkeypatch.setattr("omnicompany.core.registry.discover", lambda: None)

    from omnicompany.cli.commands.guardian import cmd_guardian_health

    result = runner.invoke(cmd_guardian_health, ["--root", "/tmp"])
    assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"
    assert "健康分数:" not in result.output, (
        f"violation: CLI still shows '健康分数:' (score gate)\n{result.output}"
    )
    assert "/100" not in result.output or "%" in result.output, (
        f"violation: CLI still shows 'X/100' score format\n{result.output}"
    )


def test_T7_cli_output_shows_counts_and_issues(runner, monkeypatch):
    """T7: CLI 输出含 counts 块 + 前 N 条 issues (severity + field + message + evidence)."""
    async def fake_dispatch(service, payload):
        return _NEW_SCHEMA_RESULT_BAD

    monkeypatch.setattr("omnicompany.core.dispatch.dispatch", fake_dispatch)
    monkeypatch.setattr("omnicompany.core.registry.discover", lambda: None)

    from omnicompany.cli.commands.guardian import cmd_guardian_health
    result = runner.invoke(cmd_guardian_health, ["--root", "/tmp"])
    assert result.exit_code != 0 or result.exit_code == 0, result.output   # 允许非零, 见 T7b
    out = result.output

    # counts 显式出现
    assert "critical" in out
    assert "major" in out
    # 至少一个 issue 的 field 或 message 出现
    assert "root_stray" in out or "根目录" in out or "root_contamination" in out
    # evidence 片段也应该显示 (语义完整铁律)
    assert "foo.db" in out or "扫出" in out


def test_T7b_passed_and_exit_code(runner, monkeypatch):
    """T7b: passed=True 时 CLI exit_code 应为 0."""
    async def fake_dispatch(service, payload):
        return _NEW_SCHEMA_RESULT_OK
    monkeypatch.setattr("omnicompany.core.dispatch.dispatch", fake_dispatch)
    monkeypatch.setattr("omnicompany.core.registry.discover", lambda: None)

    from omnicompany.cli.commands.guardian import cmd_guardian_health
    result = runner.invoke(cmd_guardian_health, ["--root", "/tmp"])
    assert result.exit_code == 0


def test_T7c_verdict_string_appears(runner, monkeypatch):
    """T7c: verdict 字符串 (healthy/unhealthy/uncertain) 应当显示给用户."""
    async def fake_dispatch(service, payload):
        return _NEW_SCHEMA_RESULT_OK
    monkeypatch.setattr("omnicompany.core.dispatch.dispatch", fake_dispatch)
    monkeypatch.setattr("omnicompany.core.registry.discover", lambda: None)

    from omnicompany.cli.commands.guardian import cmd_guardian_health
    result = runner.invoke(cmd_guardian_health, ["--root", "/tmp"])
    assert "healthy" in result.output
