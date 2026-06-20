"""第五波工具 canary 测试 (2026-05-04 立).

覆盖:
  - EnterPlanModeRouter / ExitPlanModeRouter: 状态机持久 + 进入/退出
  - EnterWorktreeRouter / ExitWorktreeRouter: git worktree 创建/移除 + 状态持久
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.agent.routers.single_tool import (
    ToolContext,
    ToolExecutionError,
)
from omnicompany.packages.services._core.agent.routers.plan_mode import (
    EnterPlanModeRouter,
    ExitPlanModeRouter,
    _read_state,
)
from omnicompany.packages.services._core.agent.routers.worktree import (
    EnterWorktreeRouter,
    ExitWorktreeRouter,
)


def _new(cls):
    return cls.__new__(cls)


# ─── PlanMode ─────────────────────────────────────────────────────


class TestPlanModeCanary:
    def test_enter_plan_mode(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(EnterPlanModeRouter)
        out = r._execute({"topic": "FOO", "rationale": "complex"}, ctx)
        assert "plan mode" in out.lower()
        # 状态持久
        state = _read_state(ctx)
        assert state["in_plan_mode"] is True
        assert state["topic"] == "FOO"

    def test_enter_when_already_in_plan(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(EnterPlanModeRouter)
        r._execute({"topic": "FIRST"}, ctx)
        out = r._execute({"topic": "SECOND"}, ctx)
        assert "Already in plan mode" in out
        # 状态没被覆盖
        state = _read_state(ctx)
        assert state["topic"] == "FIRST"

    def test_exit_plan_mode(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        enter = _new(EnterPlanModeRouter)
        enter._execute({"topic": "X"}, ctx)
        exit_r = _new(ExitPlanModeRouter)
        out = exit_r._execute({}, ctx)
        assert "Exited plan mode" in out
        state = _read_state(ctx)
        assert state["in_plan_mode"] is False

    def test_exit_when_not_in_plan(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(ExitPlanModeRouter)
        out = r._execute({}, ctx)
        assert "no-op" in out.lower() or "Not in plan mode" in out

    def test_exit_with_plan_path(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        plan = tmp_path / "plan.md"
        plan.write_text("# plan", encoding="utf-8")
        enter = _new(EnterPlanModeRouter)
        enter._execute({"topic": "X"}, ctx)
        exit_r = _new(ExitPlanModeRouter)
        out = exit_r._execute({"plan_path": str(plan)}, ctx)
        assert "Exited plan mode" in out
        assert str(plan) in out

    def test_exit_with_missing_plan_rejected(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        enter = _new(EnterPlanModeRouter)
        enter._execute({"topic": "X"}, ctx)
        exit_r = _new(ExitPlanModeRouter)
        with pytest.raises(ToolExecutionError, match="does not exist"):
            exit_r._execute({"plan_path": str(tmp_path / "ghost.md")}, ctx)

    def test_topic_required(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(EnterPlanModeRouter)
        with pytest.raises(ToolExecutionError, match="topic"):
            r._execute({}, ctx)


# ─── Worktree ─────────────────────────────────────────────────────


@pytest.fixture
def fake_git_repo(tmp_path):
    """造一个干净的 git 仓库, 给 worktree 测试用."""
    subprocess.run(
        ["git", "init", "-b", "main", str(tmp_path)],
        capture_output=True, check=True,
    )
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "T"], check=True)
    # 加一个初始 commit (worktree 需要至少一个 commit)
    (tmp_path / "README.md").write_text("init", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "init"], check=True)
    return tmp_path


class TestWorktreeCanary:
    def test_enter_worktree_creates(self, fake_git_repo):
        ctx = ToolContext(cwd=str(fake_git_repo), project_root=str(fake_git_repo))
        r = _new(EnterWorktreeRouter)
        out = r._execute({"name": "feat-x"}, ctx)
        assert "Worktree created" in out
        worktree = fake_git_repo / ".claude" / "worktrees" / "feat-x"
        assert worktree.exists()
        assert (worktree / "README.md").exists()  # 初始 commit 内容应出现在新 worktree

    def test_enter_worktree_unsafe_name(self, fake_git_repo):
        ctx = ToolContext(cwd=str(fake_git_repo), project_root=str(fake_git_repo))
        r = _new(EnterWorktreeRouter)
        with pytest.raises(ToolExecutionError, match="filesystem-safe"):
            r._execute({"name": "bad/name"}, ctx)

    def test_enter_worktree_outside_git(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(EnterWorktreeRouter)
        with pytest.raises(ToolExecutionError, match="git repository"):
            r._execute({"name": "x"}, ctx)

    def test_enter_twice_rejected(self, fake_git_repo):
        ctx = ToolContext(cwd=str(fake_git_repo), project_root=str(fake_git_repo))
        r = _new(EnterWorktreeRouter)
        r._execute({"name": "first"}, ctx)
        with pytest.raises(ToolExecutionError, match="already in worktree"):
            r._execute({"name": "second"}, ctx)

    def test_exit_keep(self, fake_git_repo):
        ctx = ToolContext(cwd=str(fake_git_repo), project_root=str(fake_git_repo))
        enter = _new(EnterWorktreeRouter)
        enter._execute({"name": "kept"}, ctx)
        exit_r = _new(ExitWorktreeRouter)
        out = exit_r._execute({"action": "keep"}, ctx)
        assert "kept on disk" in out
        # 目录还在
        assert (fake_git_repo / ".claude" / "worktrees" / "kept").exists()

    def test_exit_remove(self, fake_git_repo):
        ctx = ToolContext(cwd=str(fake_git_repo), project_root=str(fake_git_repo))
        enter = _new(EnterWorktreeRouter)
        enter._execute({"name": "tobedel"}, ctx)
        exit_r = _new(ExitWorktreeRouter)
        out = exit_r._execute({"action": "remove"}, ctx)
        assert "removed" in out
        # 目录已删 (git worktree remove 在干净 worktree 上无需 force)
        assert not (fake_git_repo / ".claude" / "worktrees" / "tobedel").exists()

    def test_exit_no_session_noop(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(ExitWorktreeRouter)
        out = r._execute({"action": "keep"}, ctx)
        assert "no-op" in out.lower() or "No worktree session active" in out


# ─── Schema ──────────────────────────────────────────────────────


class TestWave5Schemas:
    @pytest.mark.parametrize("router_cls,expected", [
        (EnterPlanModeRouter, "EnterPlanMode"),
        (ExitPlanModeRouter, "ExitPlanMode"),
        (EnterWorktreeRouter, "EnterWorktree"),
        (ExitWorktreeRouter, "ExitWorktree"),
    ])
    def test_tool_names(self, router_cls, expected):
        assert router_cls.TOOL_NAME == expected
        assert router_cls.DESCRIPTION
        assert "properties" in router_cls.INPUT_SCHEMA
