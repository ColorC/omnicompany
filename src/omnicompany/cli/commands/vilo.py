# [OMNI] origin=ai-ide domain=vilo/cli ts=2026-06-13T00:00:00Z type=cli status=active
# [OMNI] summary="omni vilo — Vilo 内容管线导航。管线已框架化为 Team，统一经 omni run vilo.* 跑；本命令只做落点/清单导航。"
# [OMNI] why="框架级统一(用户定向 2026-06-13)：管线只能是 Team。旧的 subprocess 直跑脚本入口已退役，避免绕过 Team/Material 框架。"
# [OMNI] tags=vilo,cli,pipeline,team
"""omni vilo — Vilo 内容管线导航（status/list）。

管线已全部框架化为 omnicompany Team（Router/Format/PipelineSpec），统一经
`omni run vilo.<id>` 调度。pipeline/scripts 退为 Worker 的实现库（被 routers 复用），
不再直接跑。本命令只做落点与管线清单导航。
"""
from __future__ import annotations

from pathlib import Path

import click

from .._access import any_caller

# cli/commands/vilo.py → parents[2]=src/omnicompany, parents[4]=仓根
_OMNI_ROOT = Path(__file__).resolve().parents[4]
DATA_ROOT = _OMNI_ROOT / "data" / "domains" / "vilo"


@click.group("vilo")
def cmd_vilo() -> None:
    """Vilo 内容管线导航。管线是 Team，用 `omni run vilo.<id>` 跑；这里看落点/清单。"""


@cmd_vilo.command("status")
@any_caller
def cmd_vilo_status() -> None:
    """管线落点 + 产物计数。"""

    def _count(p: Path) -> int:
        return len(list(p.iterdir())) if p.is_dir() else 0

    runs = DATA_ROOT / "runs"
    latest = ""
    if runs.is_dir():
        items = sorted((x for x in runs.iterdir() if x.is_dir()), key=lambda x: x.stat().st_mtime, reverse=True)
        latest = items[0].name if items else ""
    click.echo("== Vilo 内容管线 (已框架化为 Team) ==")
    click.echo(f"  管线/Worker : {_OMNI_ROOT / 'src/omnicompany/packages/domains/vilo'}")
    click.echo(f"  产物根      : {DATA_ROOT}")
    click.echo(f"  runs        : {_count(runs)}  (最新: {latest or '-'})")
    click.echo(f"  reports     : {_count(DATA_ROOT / 'reports')}")
    click.echo(f"  内容真源    : 外部 故事/vilo-wants-to-know (omnicompany 不接管内容)")
    click.echo("  跑管线      : omni run vilo.<id>  ——  `omni vilo list` 查看")


@cmd_vilo.command("list")
@any_caller
def cmd_vilo_list() -> None:
    """列已注册的 vilo Team（用 omni run 跑）。"""
    from omnicompany.core.registry import discover, list_all

    discover()
    rows = [e for e in list_all() if e.name.startswith("vilo.")]
    if not rows:
        click.echo("(未发现 vilo 管线)")
        return
    click.echo("Vilo 管线（Team，经 omni run 调度）：")
    for e in sorted(rows, key=lambda x: x.name):
        click.echo(f"  omni run {e.name:<26} {e.description}")
