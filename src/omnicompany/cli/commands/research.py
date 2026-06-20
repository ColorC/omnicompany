# [OMNI] origin=ai-ide domain=research/cli ts=2026-06-14T00:00:00Z type=cli status=active
# [OMNI] summary="omni research — 公开调研管线导航 + 统一研究库查询。管线是 Team,用 omni run research.run 跑。"
# [OMNI] why="框架级统一:管线只能是 Team。本命令做落点/清单导航 + 看研究库累积了什么(查重的人读面)。"
# [OMNI] tags=research,cli,pipeline,team,library
"""omni research — 公开调研导航(status / list / library)。

跑调研: `omni run research.run --topic "<题目>"`。
本命令: 看落点、列管线、查统一研究库累积的记录。
"""
from __future__ import annotations

import click

from .._access import any_caller


@click.group("research")
def cmd_research() -> None:
    """公开调研管线导航。管线是 Team,用 `omni run research.run --topic "..."` 跑。"""


@cmd_research.command("status")
@any_caller
def cmd_research_status() -> None:
    """管线落点 + 研究库计数。"""
    from omnicompany.packages.domains.research import _paths, library

    recs = library.active_records()
    runs = _paths.RUNS_ROOT
    n_runs = len(list(runs.iterdir())) if runs.is_dir() else 0
    click.echo("== 公开调研管线 (Team) ==")
    click.echo(f"  管线/Worker : {_paths._OMNI_ROOT / 'src/omnicompany/packages/domains/research'}")
    click.echo(f"  统一研究库  : {_paths.RECORDS_PATH}  ({len(recs)} 条 active)")
    click.echo(f"  runs        : {n_runs}")
    click.echo(f"  reports     : {_paths.REPORTS_ROOT}")
    click.echo("  跑调研      : omni run research.run --topic \"<题目>\"")


@cmd_research.command("list")
@any_caller
def cmd_research_list() -> None:
    """列已注册的 research Team。"""
    from omnicompany.core.registry import discover, list_all

    discover()
    rows = [e for e in list_all() if e.name.startswith("research.")]
    if not rows:
        click.echo("(未发现 research 管线)")
        return
    click.echo("公开调研管线(Team,经 omni run 调度):")
    for e in sorted(rows, key=lambda x: x.name):
        click.echo(f"  omni run {e.name:<22} {e.description}")


@cmd_research.command("library")
@click.option("--topic", default="", help="按题目查重(给题目看库里有没有同题)")
@any_caller
def cmd_research_library(topic: str) -> None:
    """看统一研究库累积了什么;给 --topic 查同题是否已调研过。"""
    from omnicompany.packages.domains.research import library

    if topic:
        norm = library.normalize_topic(topic)
        hit = library.lookup_by_topic(norm)
        if hit:
            click.echo(f"✓ 库内已有同题: {hit['record_id']}")
            click.echo(f"  更新 {hit.get('updated_at', '')} · 丰富度 {hit.get('richness', 0)} · "
                       f"来源 {len(hit.get('sources') or [])} 条 · 发现 {len(hit.get('findings') or [])} 条")
            click.echo(f"  摘要: {(hit.get('summary') or '')[:200]}")
        else:
            click.echo(f"（库内无同题「{topic}」,可放心新调研）")
        return

    recs = sorted(library.active_records(), key=lambda r: r.get("updated_at", ""), reverse=True)
    if not recs:
        click.echo("（研究库还空着）")
        return
    click.echo(f"统一研究库 · {len(recs)} 条:")
    for r in recs:
        click.echo(f"  [{r.get('richness', 0):>2}] {r.get('topic', '')[:40]:<40} "
                   f"{r.get('record_id', '')}  (更新 {r.get('updated_at', '')[:10]})")


@cmd_research.command("find-local")
@click.argument("query")
@any_caller
def cmd_research_find_local(query: str) -> None:
    """先查本地(研究记录+已拉repo+资料)有没有 query —— `omni refs find` 的别名。"""
    from omnicompany.packages.domains.research import catalog

    hits = catalog.find(query)
    if not hits:
        click.echo(f"✗ 本地无「{query}」。可放心新调研/新拉。")
        return
    click.echo(f"✓ 本地有 {len(hits)} 项命中「{query}」:")
    for h in hits:
        click.echo(f"  [{h.get('kind','')}] {h.get('name','')}  {h.get('source_url') or h.get('id','')}")


@cmd_research.command("doctor")
@any_caller
def cmd_research_doctor() -> None:
    """列带病研究记录:落库校验不过(缺字段/源无 url/快照缺失)。"""
    from omnicompany.packages.domains.research import library

    recs = library.active_records()
    bad = [(r, (r.get("validation") or {}).get("issues") or [])
           for r in recs if (r.get("validation") or {}).get("ok") is False]
    if not bad:
        click.echo(f"✓ {len(recs)} 条研究记录全部合法(或未校验)。")
        return
    click.echo(f"⚠ {len(bad)}/{len(recs)} 条记录带病:")
    for r, issues in bad:
        click.echo(f"  {r.get('record_id','')}  {r.get('topic','')[:34]}")
        for i in issues[:5]:
            click.echo(f"      - {i}")
