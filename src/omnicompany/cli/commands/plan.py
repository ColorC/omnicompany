# [OMNI] origin=ai-ide domain=cli/commands ts=2026-05-03T00:00:00Z type=router status=active
# [OMNI] summary="omni plan CLI command group — list / current / use / show plan bindings"
# [OMNI] why="cc_wrapper SessionStart hook 自动绑路径之外, 还要 CLI 显式查 / 切 plan 接口, 让 agent 跟用户能在不动文件的前提下切 active_plan. 走 services/_core/identity/record_active_session 同一份持久化逻辑跟 hook / web 一致"
# [OMNI] tags=cli,plan,session-binding,context
# [OMNI] material_id="material:cli.plan.session_binding_manager.implementation.py"
"""omni plan CLI command group — list / current / use / show plan bindings.

A plan is a bounded process record under `docs/plans/[topic-tree]/[date]NAME/`.
This command group lets the user (and agents) browse plans, see what's bound to
the current cc_session, and switch the binding without touching files manually.

Goes through `services/_core/identity/record_active_session` for writes — same
function the SessionStart hook uses, so CLI / hook / web all stay in sync.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import click

from omnicompany.packages.services._core.identity import (
    current_session_meta,
    record_active_session,
)


PLAN_DIR_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2})\](.+)$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _repo_root() -> Path:
    here = Path.cwd().resolve()
    for d in (here, *here.parents):
        if (d / "src" / "omnicompany").is_dir() and (d / "docs").is_dir():
            return d
    return Path(__file__).resolve().parents[4]


def _plans_root() -> Path:
    return _repo_root() / "docs" / "plans"


def _parse_frontmatter(plan_md: Path) -> dict[str, Any]:
    if not plan_md.is_file():
        return {}
    try:
        text = plan_md.read_text(encoding="utf-8")
    except OSError:
        return {}
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        import yaml
        data = yaml.safe_load(m.group(1)) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _walk_plans(root: Path) -> list[tuple[str, Path]]:
    """Find all [date]NAME plan dirs under root, skipping _archive subtrees.

    Returns list of (plan_id_relative_posix, abs_path).
    """
    out: list[tuple[str, Path]] = []
    if not root.is_dir():
        return out

    def _walk(d: Path) -> None:
        try:
            for entry in d.iterdir():
                if not entry.is_dir():
                    continue
                if entry.name == "_archive":
                    continue
                if PLAN_DIR_RE.match(entry.name):
                    rel = entry.relative_to(root).as_posix()
                    out.append((rel, entry))
                    continue
                _walk(entry)
        except OSError:
            pass

    _walk(root)
    return out


def _resolve_plan_query(query: str) -> tuple[str, Path] | None:
    """Resolve user-typed plan reference to (plan_id, abs_dir).

    Accepts:
      - full id: `_infra/dashboard/[2026-05-03]CC-PLAN-SESSION-CONTEXT`
      - dir basename: `[2026-05-03]CC-PLAN-SESSION-CONTEXT`
      - just NAME: `CC-PLAN-SESSION-CONTEXT` (must be globally unique)

    Returns None if no match. Raises ValueError on ambiguous match.
    """
    root = _plans_root()
    plans = _walk_plans(root)

    # exact full-id
    for pid, p in plans:
        if pid == query:
            return (pid, p)

    # exact basename
    basename_matches = [(pid, p) for pid, p in plans if p.name == query]
    if len(basename_matches) == 1:
        return basename_matches[0]
    if len(basename_matches) > 1:
        raise ValueError(f"ambiguous: {len(basename_matches)} plans match basename {query!r}")

    # NAME-only (strip date prefix)
    name_matches = []
    for pid, p in plans:
        m = PLAN_DIR_RE.match(p.name)
        if m and m.group(2) == query:
            name_matches.append((pid, p))
    if len(name_matches) == 1:
        return name_matches[0]
    if len(name_matches) > 1:
        sample = name_matches[0][0]
        raise ValueError(
            f"ambiguous: {len(name_matches)} plans named {query!r} "
            f"(use full id like '{sample}')"
        )

    return None


@click.group("plan")
def cmd_plan() -> None:
    """plan 绑定管理 — 查 / 切 / 看当前 cc_session 绑定的 plan.

    跟 dashboard cc_wrapper SessionStart hook + 网页 SessionContextPanel 共用同一份
    cc_session_active.json + cc_sessions.json 持久化, CLI / hook / web 三方一致.

    子命令:
      list     列所有非归档 plan
      current  显当前 session 绑的 plan + frontmatter
      use      切当前 session 的 active plan
      show     看指定 plan 的 frontmatter
    """


@cmd_plan.command("list")
@click.option("--package", default=None,
              help="按 package 前缀过滤 (例 _infra, _infra/dashboard, service/guardian)")
@click.option("--json", "as_json", is_flag=True, help="JSON 格式输出")
def cmd_plan_list(package: str | None, as_json: bool) -> None:
    """列 docs/plans/ 下所有非归档 plan."""
    plans = _walk_plans(_plans_root())
    if package:
        prefix = package.rstrip("/") + "/"
        plans = [(pid, p) for pid, p in plans if pid.startswith(prefix)]

    rows: list[dict[str, Any]] = []
    for pid, p in plans:
        fm = _parse_frontmatter(p / "plan.md")
        rows.append({
            "plan_id": pid,
            "title": fm.get("title") or "-",
            "status": fm.get("status") or "-",
            "work_type": fm.get("work_type") or "-",
            "date": str(fm.get("date") or "-"),
        })
    rows.sort(key=lambda r: r["date"], reverse=True)

    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    if not rows:
        click.echo("(no plans found)")
        return
    click.echo(f"{'date':12s}  {'status':10s}  {'work_type':22s}  plan_id")
    click.echo("-" * 100)
    for r in rows:
        click.echo(f"{r['date']:12s}  {r['status']:10s}  {r['work_type']:22s}  {r['plan_id']}")


@cmd_plan.command("current")
@click.option("--json", "as_json", is_flag=True, help="JSON 格式输出")
def cmd_plan_current(as_json: bool) -> None:
    """显当前 session 绑的 plan + frontmatter."""
    meta = current_session_meta()
    plan_id = meta.get("active_plan")

    if as_json:
        out: dict[str, Any] = {
            "plan_id": plan_id,
            "trace_id": meta.get("trace_id"),
            "claude_session_id": meta.get("claude_session_id"),
        }
        if plan_id:
            out["frontmatter"] = _parse_frontmatter(_plans_root() / plan_id / "plan.md")
        click.echo(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if not plan_id:
        click.echo("(no plan bound to this session)")
        click.echo("Pick one: `omni plan list` then `omni plan use <id>`")
        return

    fm = _parse_frontmatter(_plans_root() / plan_id / "plan.md")
    click.echo(f"plan_id     : {plan_id}")
    click.echo(f"title       : {fm.get('title') or '-'}")
    click.echo(f"status      : {fm.get('status') or '-'}")
    click.echo(f"work_type   : {fm.get('work_type') or '-'}")
    click.echo(f"trace_id    : {meta.get('trace_id')}")


@cmd_plan.command("use")
@click.argument("plan_query")
def cmd_plan_use(plan_query: str) -> None:
    """切当前 session 的 active plan.

    plan_query 接受:
      - 完整 id: `_infra/dashboard/[2026-05-03]CC-PLAN-SESSION-CONTEXT`
      - 目录名 : `[2026-05-03]CC-PLAN-SESSION-CONTEXT`
      - 仅名称 : `CC-PLAN-SESSION-CONTEXT` (须全局唯一)
    """
    try:
        resolved = _resolve_plan_query(plan_query)
    except ValueError as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(2)

    if not resolved:
        click.echo(f"ERROR: no plan matched {plan_query!r}", err=True)
        click.echo("Use `omni plan list` to browse available plans.", err=True)
        sys.exit(2)

    plan_id, plan_dir = resolved
    meta = current_session_meta()
    record_active_session(
        trace_id=meta["trace_id"],
        claude_session_id=meta.get("claude_session_id"),
        pty_id=meta.get("pty_id"),
        active_plan=plan_id,
        cwd=meta.get("cwd") or os.getcwd(),
        source="cli_plan_use",
    )

    # if we have a pty_id, also push into cc_sessions.json so dashboard sees it.
    # import lazily — CLI shouldn't pull fastapi unless dashboard is actually around.
    pty_id = meta.get("pty_id")
    if pty_id:
        try:
            from omnicompany.dashboard.ccdaemon.pty import update_meta_field
            update_meta_field(pty_id, active_plan=plan_id)
        except Exception as e:
            click.echo(f"WARN: pty meta update failed: {e}", err=True)

    click.echo(f"OK active_plan = {plan_id}")
    click.echo(f"   plan_dir   = {plan_dir}")
    click.echo("")
    click.echo("Note: a claude code already running in this session will see the new plan")
    click.echo("      on its NEXT SessionStart (i.e. after /clear or restart). The current")
    click.echo("      turn's injected context is fixed.")


@cmd_plan.command("show")
@click.argument("plan_query")
@click.option("--md", "as_md", is_flag=True, help="输出 plan.md 原文 (raw)")
def cmd_plan_show(plan_query: str, as_md: bool) -> None:
    """显指定 plan 的 frontmatter 概要."""
    try:
        resolved = _resolve_plan_query(plan_query)
    except ValueError as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(2)
    if not resolved:
        click.echo(f"ERROR: no plan matched {plan_query!r}", err=True)
        sys.exit(2)

    plan_id, plan_dir = resolved
    plan_md = plan_dir / "plan.md"

    if as_md:
        if plan_md.is_file():
            click.echo(plan_md.read_text(encoding="utf-8"))
        else:
            click.echo(f"(no plan.md in {plan_dir})", err=True)
            sys.exit(2)
        return

    fm = _parse_frontmatter(plan_md)
    click.echo(f"plan_id            : {plan_id}")
    click.echo(f"path               : {plan_dir}")
    click.echo(f"title              : {fm.get('title') or '-'}")
    click.echo(f"date               : {fm.get('date') or '-'}")
    click.echo(f"project            : {fm.get('project') or '-'}")
    click.echo(f"work_type          : {fm.get('work_type') or '-'}")
    click.echo(f"status             : {fm.get('status') or '-'}")
    click.echo(f"phase              : {fm.get('phase') or '-'}")
    click.echo(f"expected_completion: {fm.get('expected_completion') or '-'}")
    click.echo(f"ttl_days           : {fm.get('ttl_days') or '-'}")
    standards = fm.get("standards") or []
    if standards:
        click.echo("standards          :")
        for s in standards:
            click.echo(f"  - {s}")
    exit_criteria = fm.get("exit_criteria") or []
    if exit_criteria:
        click.echo("exit_criteria      :")
        for ec in exit_criteria:
            click.echo(f"  - {ec}")
