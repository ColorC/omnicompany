from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import click
from click.testing import CliRunner

from omnicompany.bus.memory import MemoryBus
from omnicompany.dashboard.boss_sight.controller import tools as tools_mod
from omnicompany.dashboard.boss_sight.controller.tools import (
    JudgeReviewstageMaterialRouter,
    SpawnSubagentRouter,
    SubmitToReviewstageRouter,
)
from omnicompany.runtime.agent.agent_loop_tools import ToolContext


@pytest.fixture
def bus():
    bus = MemoryBus()
    asyncio.get_event_loop().run_until_complete(bus.connect())
    return bus


@pytest.fixture
def ctx():
    return ToolContext(trace_id="t-v2-04", turn_number=0)


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNI_WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "docs" / "plans").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture(autouse=True)
def reset_singletons(monkeypatch):
    from omnicompany.dashboard.boss_sight.reviewstage import routes as rs_routes

    monkeypatch.setattr(rs_routes, "_store_singleton", None)
    monkeypatch.setattr(rs_routes, "_hub", None)
    yield


def _submitted_id(out: str) -> str:
    return out.split("id=")[1].split()[0]


def test_worktree_isolated_spawn_uses_worktree_cwd(tmp_workspace, bus, monkeypatch):
    worktree_path = tmp_workspace / ".claude" / "worktrees" / "boss-sight" / "unit"
    captured: dict[str, object] = {}

    def fake_create(ws: Path, plan_id: str, *, base_ref: str = "HEAD") -> dict[str, str]:
        assert ws == tmp_workspace
        assert plan_id == "plans/demo"
        return {"path": str(worktree_path), "branch": "boss-sight/unit", "base_ref": base_ref}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"id": "sess-worktree"}).encode("utf-8")

    def fake_urlopen(req, timeout=15):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResp()

    monkeypatch.setattr(tools_mod, "_create_spawn_worktree", fake_create)
    monkeypatch.setattr(tools_mod, "_find_git_root", lambda ws: tmp_workspace)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    router = SpawnSubagentRouter(bus=bus)
    out = router._spawn_standalone_worker(
        "plans/demo",
        "Please execute the isolated worker task and submit a material.",
        {
            "provider": "claude_code",
            "model_hint": "auto",
            "worktree_isolation": "git_worktree",
            "worktree_base": "HEAD",
        },
    )

    assert "standalone subagent spawned" in out
    assert "auto_model_hint=" in out
    assert "worktree=" in out
    body = captured["body"]
    assert body["cwd"] == str(worktree_path)
    assert body["active_plan"] == "plans/demo"


def test_worktree_isolation_non_git_returns_clear_error(tmp_workspace, bus, monkeypatch):
    def fail_create(ws: Path, plan_id: str, *, base_ref: str = "HEAD") -> dict[str, str]:
        raise RuntimeError(f"not in a git repository: {ws}")

    monkeypatch.setattr(tools_mod, "_create_spawn_worktree", fail_create)

    router = SpawnSubagentRouter(bus=bus)
    out = router._spawn_standalone_worker(
        "plans/demo",
        "Please run this in isolation.",
        {"provider": "claude_code", "worktree_isolation": "git_worktree"},
    )

    assert "standalone spawn failed: worktree isolation" in out
    assert "not in a git repository" in out


def test_worktree_isolation_refuses_repo_root_cwd_assertion(tmp_workspace, bus, monkeypatch):
    def fake_create(ws: Path, plan_id: str, *, base_ref: str = "HEAD") -> dict[str, str]:
        return {"path": str(tmp_workspace), "branch": "boss-sight/root", "base_ref": base_ref}

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("spawn must stop before HTTP when worktree cwd equals repo root")

    monkeypatch.setattr(tools_mod, "_create_spawn_worktree", fake_create)
    monkeypatch.setattr(tools_mod, "_find_git_root", lambda ws: tmp_workspace)
    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)

    router = SpawnSubagentRouter(bus=bus)
    out = router._spawn_standalone_worker(
        "plans/demo",
        "Please run this in isolation.",
        {"provider": "claude_code", "worktree_isolation": "git_worktree"},
    )

    assert out == "standalone spawn failed: worktree cwd assertion failed"


def test_worktree_isolation_refuses_dirty_repo(tmp_workspace, monkeypatch):
    monkeypatch.setattr(tools_mod, "_find_git_root", lambda ws: tmp_workspace)
    monkeypatch.setattr(tools_mod, "_git_dirty_summary", lambda repo: " M src/file.py")

    with pytest.raises(RuntimeError, match="uncommitted changes"):
        tools_mod._create_spawn_worktree(tmp_workspace, "plans/demo")


def test_cli_worker_spawn_accepts_auto_model_hint(monkeypatch):
    from omnicompany.cli.commands import boss_sight as boss_cli

    root = click.Group("omni")
    worker = click.Group("worker")
    plan = click.Group("plan")
    root.add_command(worker)
    root.add_command(plan)

    captured: dict[str, object] = {}

    def fake_invoke(router_cls, args):
        captured["router_cls"] = router_cls
        captured["args"] = args
        return "ok"

    monkeypatch.setattr(boss_cli, "_invoke_router", fake_invoke)
    boss_cli.register_boss_sight_commands(root, cmd_worker=worker, cmd_plan=plan)

    result = CliRunner().invoke(
        root,
        ["worker", "spawn", "plans/demo", "Do the work", "--model-hint", "auto"],
    )

    assert result.exit_code == 0, result.output
    assert captured["args"]["model_hint"] == "auto"


def test_material_soft_validation_persists_warnings(tmp_workspace, bus, ctx):
    router = SubmitToReviewstageRouter(bus=bus)
    out = router._execute({
        "kind": "custom_web_template",
        "tier": "important",
        "title": "Broken custom template",
        "source_plan_id": "test/v2-04",
        "inline_content": "{not-json}",
    }, ctx)

    assert "material submitted" in out
    assert "structure_warnings=" in out
    mid = _submitted_id(out)

    from omnicompany.dashboard.boss_sight.reviewstage.routes import get_store

    material = get_store().get(mid)
    assert material is not None
    warnings = material.extra.get("structure_warnings")
    assert isinstance(warnings, list)
    codes = {w["code"] for w in warnings}
    assert "custom_template_missing_schema" in codes
    assert "custom_template_invalid_json" in codes
    assert any(h.get("event") == "structure_warning" for h in material.history)


def test_judge_router_returns_decision_without_changing_status(tmp_workspace, bus, ctx):
    submit = SubmitToReviewstageRouter(bus=bus)
    out = submit._execute({
        "kind": "custom_web_template",
        "tier": "important",
        "title": "Architecture route material",
        "source_plan_id": "test/v2-04",
        "inline_content": "{not-json}",
    }, ctx)
    mid = _submitted_id(out)

    judge = JudgeReviewstageMaterialRouter(bus=bus)
    judged = json.loads(judge._execute({"material_id": mid}, ctx))

    assert judged["material_id"] == mid
    assert judged["status_unchanged"] == "pending"
    assert judged["decision"]["model_hint"] in {"high", "default", "low"}
    assert judged["decision"]["needs_orchestration"] is True
    assert judged["decision"]["warning_count"] >= 2

    from omnicompany.dashboard.boss_sight.reviewstage.routes import get_store

    assert get_store().get(mid).status == "pending"
