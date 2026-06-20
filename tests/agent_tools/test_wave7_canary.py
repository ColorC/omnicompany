"""第七波工具 canary 测试 (2026-05-04 立).

覆盖:
  - AgentRouter: 干跑 + ctx.subagent_registry 验证
  - DiscoverSkillsRouter: 扫 .claude/skills 目录
  - SkillRouter: 加载 SKILL.md
  - ToolSearchRouter: ctx.tool_registry 列举/搜索
  - WorkflowRouter: list / load
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
from omnicompany.packages.services._core.agent.routers.agent_spawn import AgentRouter
from omnicompany.packages.services._core.agent.routers.skill_tools import (
    DiscoverSkillsRouter,
    SkillRouter,
    ToolSearchRouter,
)
from omnicompany.packages.services._core.agent.routers.workflow_tool import WorkflowRouter


def _new(cls):
    return cls.__new__(cls)


# ─── AgentRouter ─────────────────────────────────────────────────


class TestAgentCanary:
    def test_dry_run(self, monkeypatch):
        monkeypatch.setenv("OMNI_AGENT_DRY_RUN", "1")
        ctx = ToolContext()
        r = _new(AgentRouter)
        out = r._execute({
            "description": "Find auth bugs",
            "prompt": "Search for auth-related bugs in src/",
            "subagent_type": "Explore",
        }, ctx)
        data = json.loads(out)
        assert data["dry_run"] is True
        assert data["subagent_type"] == "Explore"

    def test_required_fields(self):
        ctx = ToolContext()
        r = _new(AgentRouter)
        with pytest.raises(ToolExecutionError, match="description"):
            r._execute({"prompt": "x"}, ctx)
        with pytest.raises(ToolExecutionError, match="prompt"):
            r._execute({"description": "x"}, ctx)

    def test_no_registry_no_dry_run(self):
        ctx = ToolContext()
        r = _new(AgentRouter)
        with pytest.raises(ToolExecutionError, match="subagent_registry"):
            r._execute({"description": "x", "prompt": "y"}, ctx)


# ─── DiscoverSkillsRouter ────────────────────────────────────────


class TestDiscoverSkillsCanary:
    def test_scan_skills(self, tmp_path):
        # 造两个假 skill
        skills_dir = tmp_path / ".claude" / "skills"
        for name, desc in [("foo", "Foo skill description"), ("bar", "Bar does bar")]:
            d = skills_dir / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n\n{desc}\n")

        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(DiscoverSkillsRouter)
        out = r._execute({}, ctx)
        assert "foo" in out
        assert "bar" in out

    def test_no_skills(self, tmp_path, monkeypatch):
        # DiscoverSkillsRouter 也会扫 ~/.claude/skills/, monkeypatch home 隔离
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(DiscoverSkillsRouter)
        out = r._execute({}, ctx)
        assert "No skills" in out


# ─── SkillRouter ─────────────────────────────────────────────────


class TestSkillCanary:
    def test_load_skill(self, tmp_path):
        skill_dir = tmp_path / ".claude" / "skills" / "writer"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Writer\n\nWrites essays.\n")

        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(SkillRouter)
        out = r._execute({"name": "writer"}, ctx)
        assert "Writer" in out
        assert "Writes essays" in out

    def test_skill_not_found(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(SkillRouter)
        with pytest.raises(ToolExecutionError, match="not found"):
            r._execute({"name": "ghost"}, ctx)

    def test_unsafe_name(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(SkillRouter)
        with pytest.raises(ToolExecutionError, match="filesystem-safe"):
            r._execute({"name": "../etc"}, ctx)

    def test_with_args(self, tmp_path):
        skill_dir = tmp_path / ".claude" / "skills" / "x"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("instructions")
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(SkillRouter)
        out = r._execute({"name": "x", "args": "topic-foo"}, ctx)
        assert "Arguments: topic-foo" in out


# ─── ToolSearchRouter ───────────────────────────────────────────
# 注: 旧 4 条用 ctx.tool_registry 模式的 ToolSearch 测试已删 (2026-05-04 第二波 P0).
# 行为已重做对齐 claude code deferred 拉取机制.
# 新测试见 tests/agent_tools/test_default_vs_deferred.py: TestToolSearch* 多条.


# ─── WorkflowRouter ──────────────────────────────────────────────


class TestWorkflowCanary:
    def test_list_workflows(self, tmp_path):
        wf_dir = tmp_path / ".claude" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "deploy.md").write_text("# deploy")
        (wf_dir / "rollback.yaml").write_text("steps: []")
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(WorkflowRouter)
        out = r._execute({"action": "list"}, ctx)
        assert "deploy" in out and "rollback" in out

    def test_load_workflow(self, tmp_path):
        wf_dir = tmp_path / ".claude" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "x.md").write_text("# X workflow\n\nstep 1")
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(WorkflowRouter)
        out = r._execute({"action": "load", "name": "x"}, ctx)
        assert "X workflow" in out
        assert "step 1" in out

    def test_load_missing(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(WorkflowRouter)
        with pytest.raises(ToolExecutionError, match="not found"):
            r._execute({"action": "load", "name": "ghost"}, ctx)

    def test_invalid_action(self, tmp_path):
        ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path))
        r = _new(WorkflowRouter)
        with pytest.raises(ToolExecutionError, match="action"):
            r._execute({"action": "delete"}, ctx)


# ─── Schema ──────────────────────────────────────────────────────


class TestWave7Schemas:
    @pytest.mark.parametrize("router_cls,expected", [
        (AgentRouter, "Agent"),
        (DiscoverSkillsRouter, "DiscoverSkills"),
        (SkillRouter, "Skill"),
        (ToolSearchRouter, "ToolSearch"),
        (WorkflowRouter, "Workflow"),
    ])
    def test_tool_names(self, router_cls, expected):
        assert router_cls.TOOL_NAME == expected
        assert router_cls.DESCRIPTION
        assert "properties" in router_cls.INPUT_SCHEMA
