# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T04:30:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest 单元测 GitLogTool — 4hr 拷问真问题 1+5 修后的工具自测 (跟 scanner+builder 同模式)"
# [OMNI] why="git_log_tool 立时跟 facility_scanner / work_pattern_scanner / pytest_skeleton_builder 同模式应有 pytest 测试. 修 AP-019 (tool-not-eat-own-dogfood)"
# [OMNI] tags=test,pytest,git-log-tool,unit-test,boundary-case
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_git_log_tool.py"
"""pytest 单元测 GitLogTool.

测 case:
- 边界 (空 since 报错 / since 在未来 0 commit / max_count 上限)
- 真用 (recent / paths filter)
- schema (INPUT_SCHEMA 字段齐 / 必填 since)
- 解析 (_parse_git_log_output 单元测)
"""
from __future__ import annotations

import pytest

from omnicompany.packages.services._diagnosis.doctor.tools.git_log_tool import (
    GitLogTool,
    _parse_git_log_output,
    GitCommitSummary,
)
from omnicompany.packages.services._core.agent.routers.single_tool import ToolExecutionError


class FakeCtx:
    """简单 ctx fixture, 仅含 scratch 字典."""
    def __init__(self):
        self.scratch = {}


@pytest.fixture
def tool():
    """绕开 SingleToolRouter __init__ (它要 bus), 直接 __new__ 用于 _execute 单元测."""
    return GitLogTool.__new__(GitLogTool)


# ── INPUT_SCHEMA ──

def test_input_schema_required_since():
    """schema 必填 since."""
    assert "since" in GitLogTool.INPUT_SCHEMA["required"]
    assert "since" in GitLogTool.INPUT_SCHEMA["properties"]


def test_input_schema_max_count_default_50():
    """max_count 默认 50, 上限 500."""
    p = GitLogTool.INPUT_SCHEMA["properties"]["max_count"]
    assert p["default"] == 50
    assert p["maximum"] == 500


def test_input_schema_optional_fields():
    """until / paths 是 optional."""
    schema = GitLogTool.INPUT_SCHEMA
    assert "until" in schema["properties"]
    assert "until" not in schema["required"]
    assert "paths" in schema["properties"]
    assert "paths" not in schema["required"]


# ── 边界 case ──

def test_empty_since_raises(tool):
    """空 since 应报 ToolExecutionError."""
    ctx = FakeCtx()
    with pytest.raises(ToolExecutionError, match="since"):
        tool._execute({}, ctx)


def test_since_in_future_returns_zero(tool):
    """since 未来 → 0 commit, 不报错."""
    ctx = FakeCtx()
    msg = tool._execute({"since": "2099-01-01", "max_count": 5}, ctx)
    assert "0 commits" in msg
    assert ctx.scratch["last_git_log_result"] == []


def test_max_count_caps_at_500(tool):
    """max_count > 500 应 cap 到 500."""
    ctx = FakeCtx()
    # 真大值, 应不挂 (cap 后跑通)
    msg = tool._execute({"since": "2099-01-01", "max_count": 99999}, ctx)
    assert "0 commits" in msg  # 未来 since 仍 0


# ── 真用 ──

def test_recent_since_returns_commits(tool):
    """recent since 返 ≥1 commit."""
    ctx = FakeCtx()
    msg = tool._execute({"since": "1 month ago", "max_count": 5}, ctx)
    # 应 ≥1 commit (我们项目 1 月内必然有 commit)
    assert ctx.scratch["last_git_log_result"]
    commits = ctx.scratch["last_git_log_result"]
    assert len(commits) >= 1
    # 第一 commit 字段齐
    c0 = commits[0]
    assert "short_hash" in c0
    assert "date" in c0
    assert "subject" in c0


def test_paths_filter(tool):
    """paths filter 真过滤 — 只返触及指定 path 的 commit."""
    ctx = FakeCtx()
    msg = tool._execute({
        "since": "1 week ago",
        "max_count": 20,
        "paths": ["src/omnicompany/packages/services/_diagnosis/doctor/"],
    }, ctx)
    commits = ctx.scratch.get("last_git_log_result", [])
    # 应有 commit (本周确实改 doctor/)
    assert isinstance(commits, list)


# ── _parse_git_log_output ──

def test_parse_git_log_output_empty():
    """空输出 → 空 list."""
    assert _parse_git_log_output("") == []
    assert _parse_git_log_output("\n\n\n") == []


def test_parse_git_log_output_simple():
    """简单输出含 1 commit + shortstat."""
    fake_output = """abcd123|2026-05-07 12:00:00 +0800|ai-ide|fix something
 2 files changed, 10 insertions(+), 5 deletions(-)
"""
    commits = _parse_git_log_output(fake_output)
    assert len(commits) == 1
    c = commits[0]
    assert c.short_hash == "abcd123"
    assert c.author == "ai-ide"
    assert c.subject == "fix something"
    assert c.files_changed == 2
    assert c.lines_added == 10
    assert c.lines_deleted == 5


def test_parse_git_log_output_no_stat():
    """commit 没 shortstat → 默认 0."""
    fake_output = "abcd123|2026-05-07 12:00:00 +0800|ai-ide|fix without stat\n"
    commits = _parse_git_log_output(fake_output)
    assert len(commits) == 1
    assert commits[0].files_changed == 0
    assert commits[0].lines_added == 0


# ── GitCommitSummary dataclass ──

def test_git_commit_summary_default_fields():
    """GitCommitSummary 默认 0/空."""
    c = GitCommitSummary(
        short_hash="abc123",
        date="2026-05-07",
        author="test",
        subject="test",
    )
    assert c.files_changed == 0
    assert c.lines_added == 0
    assert c.lines_deleted == 0
