# [OMNI] origin=ai-ide domain=tests/cli ts=2026-05-03T00:00:00Z type=test
"""Tests for `omni plan` CLI command group (cli/commands/plan.py).

Covers:
  - _walk_plans skips _archive subtree
  - _resolve_plan_query: full id / basename / NAME-only / ambiguous / miss
  - cmd_plan_list: rows + --package filter
  - cmd_plan_use: writes cc_session_active.json with new active_plan
  - cmd_plan_current: prompt when nothing bound
  - cmd_plan_show: prints frontmatter values
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """Build a fake docs/plans/ tree + redirect plan.py + resolver.py at it."""
    plans_root = tmp_path / "docs" / "plans"
    plans_root.mkdir(parents=True)
    # active plan
    a = plans_root / "_infra" / "dashboard" / "[2026-05-03]ALPHA"
    a.mkdir(parents=True)
    (a / "plan.md").write_text(
        "---\ntitle: ALPHA\ndate: 2026-05-03\nproject: dashboard\n"
        "work_type: foo-binding\nstatus: active\nphase: planning\n"
        "expected_completion: 2026-05-17\nttl_days: 30\n"
        "standards:\n  - concepts/plan\nexit_criteria:\n  - thing one\n---\n# ALPHA\n",
        encoding="utf-8",
    )
    # second plan in another package
    b = plans_root / "_infra" / "diagnosis" / "[2026-05-02]BETA"
    b.mkdir(parents=True)
    (b / "plan.md").write_text(
        "---\ntitle: BETA\ndate: 2026-05-02\nstatus: active\n---\n# BETA\n",
        encoding="utf-8",
    )
    # archived plan must be skipped
    arch = plans_root / "_archive" / "[2026-04-30]GHOST"
    arch.mkdir(parents=True)
    (arch / "plan.md").write_text("---\ntitle: GHOST\n---\n", encoding="utf-8")

    # redirect plan-module roots
    from omnicompany.cli.commands import plan as plan_mod
    monkeypatch.setattr(plan_mod, "_plans_root", lambda: plans_root)

    # redirect resolver active file
    from omnicompany.packages.services._core.identity import resolver
    active_file = tmp_path / "cc_session_active.json"
    monkeypatch.setattr(resolver, "_active_file", lambda: active_file)

    # tests inherit real OMNI_CC_* env from parent (we run inside a real cc wrapper),
    # which would override our seeded trace_id. Strip them so tests are deterministic.
    monkeypatch.delenv("OMNI_CC_TRACE_ID", raising=False)
    monkeypatch.delenv("OMNI_CC_PTY_ID", raising=False)

    return {
        "plans_root": plans_root,
        "alpha": a,
        "beta": b,
        "active_file": active_file,
    }


# ─── helpers ──────────────────────────────────────────────────────────────────


def test_walk_plans_skips_archive(fake_repo):
    from omnicompany.cli.commands import plan as plan_mod
    plans = plan_mod._walk_plans(fake_repo["plans_root"])
    ids = {pid for pid, _ in plans}
    assert "_infra/dashboard/[2026-05-03]ALPHA" in ids
    assert "_infra/diagnosis/[2026-05-02]BETA" in ids
    # GHOST under _archive must not appear
    assert not any("GHOST" in pid for pid in ids)


def test_resolve_plan_query_by_full_id(fake_repo):
    from omnicompany.cli.commands import plan as plan_mod
    pid, p = plan_mod._resolve_plan_query("_infra/dashboard/[2026-05-03]ALPHA")
    assert pid == "_infra/dashboard/[2026-05-03]ALPHA"
    assert p == fake_repo["alpha"]


def test_resolve_plan_query_by_basename(fake_repo):
    from omnicompany.cli.commands import plan as plan_mod
    pid, p = plan_mod._resolve_plan_query("[2026-05-02]BETA")
    assert p == fake_repo["beta"]


def test_resolve_plan_query_by_name_only(fake_repo):
    from omnicompany.cli.commands import plan as plan_mod
    pid, p = plan_mod._resolve_plan_query("ALPHA")
    assert p == fake_repo["alpha"]


def test_resolve_plan_query_ambiguous_raises(fake_repo):
    """Two plans with the same NAME should raise ValueError on a NAME-only lookup."""
    from omnicompany.cli.commands import plan as plan_mod
    dup = fake_repo["plans_root"] / "_infra" / "dashboard" / "[2026-04-15]ALPHA"
    dup.mkdir(parents=True)
    (dup / "plan.md").write_text("---\ntitle: ALPHA-OLDER\n---\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ambiguous"):
        plan_mod._resolve_plan_query("ALPHA")


def test_resolve_plan_query_miss_returns_none(fake_repo):
    from omnicompany.cli.commands import plan as plan_mod
    assert plan_mod._resolve_plan_query("DOES-NOT-EXIST") is None


# ─── commands ─────────────────────────────────────────────────────────────────


def test_cmd_list_renders_all_plans(fake_repo):
    from omnicompany.cli.commands.plan import cmd_plan
    result = CliRunner().invoke(cmd_plan, ["list"])
    assert result.exit_code == 0, result.output
    assert "_infra/dashboard/[2026-05-03]ALPHA" in result.output
    assert "_infra/diagnosis/[2026-05-02]BETA" in result.output
    assert "GHOST" not in result.output


def test_cmd_list_package_filter(fake_repo):
    from omnicompany.cli.commands.plan import cmd_plan
    result = CliRunner().invoke(cmd_plan, ["list", "--package", "_infra/dashboard"])
    assert result.exit_code == 0
    assert "ALPHA" in result.output
    assert "BETA" not in result.output


def test_cmd_list_json(fake_repo):
    from omnicompany.cli.commands.plan import cmd_plan
    result = CliRunner().invoke(cmd_plan, ["list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    titles = {row["title"] for row in data}
    assert {"ALPHA", "BETA"} <= titles


def test_cmd_show_renders_frontmatter(fake_repo):
    from omnicompany.cli.commands.plan import cmd_plan
    result = CliRunner().invoke(cmd_plan, ["show", "ALPHA"])
    assert result.exit_code == 0
    assert "title              : ALPHA" in result.output
    assert "work_type          : foo-binding" in result.output
    assert "expected_completion: 2026-05-17" in result.output
    assert "concepts/plan" in result.output
    assert "thing one" in result.output


def test_cmd_show_md_dumps_raw(fake_repo):
    from omnicompany.cli.commands.plan import cmd_plan
    result = CliRunner().invoke(cmd_plan, ["show", "ALPHA", "--md"])
    assert result.exit_code == 0
    assert "# ALPHA" in result.output
    assert "title: ALPHA" in result.output


def test_cmd_show_miss_exits_nonzero(fake_repo):
    from omnicompany.cli.commands.plan import cmd_plan
    result = CliRunner().invoke(cmd_plan, ["show", "NOPE"])
    assert result.exit_code != 0
    assert "no plan matched" in result.output


def test_cmd_use_writes_active_file(fake_repo, monkeypatch):
    """Pre-bind a fake session, then `omni plan use BETA` must update active_plan."""
    # seed active file with an existing session
    from omnicompany.packages.services._core.identity import resolver
    resolver.record_active_session(
        trace_id="t-fixture", claude_session_id="c-fixture",
        active_plan="_infra/dashboard/[2026-05-03]ALPHA",
        cwd=str(fake_repo["plans_root"].parent),
    )

    from omnicompany.cli.commands.plan import cmd_plan
    result = CliRunner().invoke(cmd_plan, ["use", "BETA"])
    assert result.exit_code == 0, result.output
    assert "active_plan = _infra/diagnosis/[2026-05-02]BETA" in result.output

    data = json.loads(fake_repo["active_file"].read_text(encoding="utf-8"))
    assert data["active_plan"] == "_infra/diagnosis/[2026-05-02]BETA"
    assert data["trace_id"] == "t-fixture"
    assert data["source"] == "cli_plan_use"


def test_cmd_use_miss_exits_nonzero(fake_repo):
    from omnicompany.cli.commands.plan import cmd_plan
    result = CliRunner().invoke(cmd_plan, ["use", "DOES-NOT-EXIST"])
    assert result.exit_code != 0
    assert "no plan matched" in result.output


def test_cmd_current_no_binding(fake_repo):
    """No active file → cmd_plan_current prompts user to pick one."""
    from omnicompany.cli.commands.plan import cmd_plan
    # active_file does not exist (fixture created path but not file)
    result = CliRunner().invoke(cmd_plan, ["current"])
    assert result.exit_code == 0
    assert "no plan bound" in result.output
    assert "omni plan use" in result.output


def test_cmd_current_with_binding(fake_repo):
    from omnicompany.packages.services._core.identity import resolver
    resolver.record_active_session(
        trace_id="t-cur", active_plan="_infra/dashboard/[2026-05-03]ALPHA",
    )
    from omnicompany.cli.commands.plan import cmd_plan
    result = CliRunner().invoke(cmd_plan, ["current"])
    assert result.exit_code == 0
    assert "_infra/dashboard/[2026-05-03]ALPHA" in result.output
    assert "title       : ALPHA" in result.output
