# [OMNI] origin=ai-ide domain=cli/commands ts=2026-05-02T00:00:00Z type=router status=active agent=ai-ide-current
# [OMNI] summary="omni who / session 命令组, claude code session 身份显示 + 显式绑定"
# [OMNI] why="hook 自动绑定路径之外, 还要 CLI 显式兜底, 让脚本/测试场景能强制设 trace_id. hook 跟 CLI 走的逻辑一致 (都调 services/_core/identity/record_active_session)"
# [OMNI] tags=cli,identity,session,who
# [OMNI] material_id="material:cli.identity.session_manager.implementation.py"
"""omni CLI 身份命令组.

`omni who` — 显示当前 claude code session 的身份元数据 + 写过的文件清单
`omni session current` — 输出 trace_id 一个字符串 (供 shell 脚本 $(omni session current))
`omni session bind --trace-id=<>` — 显式绑定 trace_id (兜底, 测试 / 脚本场景用)

跟 dashboard cc_wrapper 的 SessionStart hook 走同一份 identity 模块, 只是触发方式不同.
"""
from __future__ import annotations

import json
import os

import click

from omnicompany.packages.services._core.identity import (
    resolve_active_trace_id,
    current_session_meta,
    record_active_session,
    session_writes,
)


@click.command("who")
@click.option("--json", "as_json", is_flag=True, help="JSON 格式输出 (供脚本消费)")
@click.option("--writes/--no-writes", default=True, help="是否显示写过的文件清单 (默认显示, 上限 20 条)")
@click.option("--writes-limit", type=int, default=20, help="写过的文件清单条数上限")
def cmd_who(as_json: bool, writes: bool, writes_limit: int) -> None:
    """显示当前 claude code session 的身份 + 写过的文件清单.

    身份解析优先级 (高→低):
      1. OMNI_CC_TRACE_ID env (CLI 显式)
      2. OMNI_CC_PTY_ID env (dashboard PTY 启动 claude 时传)
      3. data/cc_session_active.json (SessionStart hook 写)
      4. cc_unknown_<ts> (fallback)

    跟 dashboard / web / hook 用同一身份链, CLI 这里只是查询入口.
    """
    meta = current_session_meta()
    write_files = session_writes(meta["trace_id"], limit=writes_limit) if writes else []

    if as_json:
        out = dict(meta)
        out["writes"] = write_files
        click.echo(json.dumps(out, ensure_ascii=False, indent=2))
        return

    click.echo(f"trace_id           : {meta['trace_id']}")
    click.echo(f"source             : {meta['source']}")
    click.echo(f"claude_session_id  : {meta['claude_session_id'] or '-'}")
    click.echo(f"pty_id             : {meta['pty_id'] or '-'}")
    click.echo(f"active_plan        : {meta['active_plan'] or '-'}")
    click.echo(f"started_at         : {meta['started_at'] or '-'}")
    click.echo(f"cwd                : {meta['cwd']}")
    click.echo(f"active_file        : {meta['active_file_path']}")
    if writes:
        click.echo()
        click.echo(f"写过的文件 ({len(write_files)} 条, 最近 {writes_limit}):")
        if not write_files:
            click.echo("  (无, 可能 cc_wrapper hook 未运行 / 此 session 还没写过文件)")
        else:
            for w in write_files:
                click.echo(f"  [{w['tool']:6s}] {w['file_path']}  ({w['timestamp']})")


@click.group("session")
def cmd_session() -> None:
    """claude code session 身份管理 (跟 dashboard 共用一身份链).

    子命令:
      current  显示当前 trace_id (一行字符串, 供 shell 脚本嵌入)
      bind     显式绑定 trace_id (兜底, 测试 / 脚本场景)
      meta     显示完整元数据 (跟 omni who 等价但只 meta 不带 writes)
    """


@cmd_session.command("current")
def cmd_session_current() -> None:
    """输出当前 trace_id (一行字符串).

    供 shell 脚本嵌入, 例如:
        TRACE=$(omni session current)
        omni register material --trace-id=$TRACE ...
    """
    click.echo(resolve_active_trace_id())


@cmd_session.command("bind")
@click.option("--trace-id", required=True, help="要绑定的 trace_id")
@click.option("--claude-session-id", default=None, help="可选: claude session id")
@click.option("--pty-id", default=None, help="可选: dashboard PTY id")
@click.option("--active-plan", default=None, help="可选: 当前 active plan 路径")
def cmd_session_bind(
    trace_id: str,
    claude_session_id: str | None,
    pty_id: str | None,
    active_plan: str | None,
) -> None:
    """显式绑定 trace_id 到当前 active session.

    兜底入口 — 跟 SessionStart hook 共用一份 record_active_session() 函数,
    只是触发方式不同. 用于:
      - 测试场景 (绕过 hook 直接设)
      - 脚本场景 (一次跑多 session)
      - hook 故障 fallback
    """
    p = record_active_session(
        trace_id=trace_id,
        claude_session_id=claude_session_id,
        pty_id=pty_id,
        active_plan=active_plan,
        cwd=os.getcwd(),
        source="cli_bind",
    )
    click.echo(f"OK trace_id={trace_id} 已绑定 → {p}")


@cmd_session.command("meta")
@click.option("--json", "as_json", is_flag=True, help="JSON 格式输出")
def cmd_session_meta(as_json: bool) -> None:
    """显示完整 session 元数据 (跟 omni who 等价但不带 writes 清单)."""
    meta = current_session_meta()
    if as_json:
        click.echo(json.dumps(meta, ensure_ascii=False, indent=2))
    else:
        for k, v in meta.items():
            click.echo(f"{k:20s} : {v}")


# ── omni whoami (CLI-PHASE3 alias 跟 plan 命名一致) ──────────────────
@click.command("whoami")
@click.option("--json", "as_json", is_flag=True, help="JSON 格式输出")
@click.option("--writes/--no-writes", default=True, help="是否显示写过的文件清单")
@click.option("--writes-limit", type=int, default=20)
@click.pass_context
def cmd_whoami(ctx, as_json, writes, writes_limit):
    """显示当前身份 (跟 omni who 等价, CLI-PHASE3 plan 命名)."""
    ctx.invoke(cmd_who, as_json=as_json, writes=writes, writes_limit=writes_limit)
