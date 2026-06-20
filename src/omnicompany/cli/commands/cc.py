# [OMNI] origin=claude-code ts=2026-05-02 type=infra
# [OMNI] material_id="material:cli.claude_code.wrapper.settings_installer.py"
"""omni cc — Claude Code wrapper management.

Subcommands (single source of truth — dashboard install button calls these):
    omni cc install   [--scope project|user]   register MCP + hooks in settings.json
    omni cc uninstall [--scope project|user]   remove only the entries we own
    omni cc status    [--scope project|user]   show what's currently wired
"""

import json

import click

from omnicompany.dashboard.ccdaemon import installer as si


@click.group("cc")
def cmd_cc():
    """Claude Code wrapper integration commands."""


@cmd_cc.command("install")
@click.option("--scope", type=click.Choice(["project", "user"]), default="project",
              help="`project` writes to <repo>/.claude/settings.json (recommended). "
                   "`user` writes to ~/.claude/settings.json (affects all your claude usage).")
def cc_install(scope: str) -> None:
    """Wire omnicompany MCP server + hooks into Claude Code's settings."""
    rep = si.install(scope=scope)  # type: ignore[arg-type]
    click.echo(json.dumps({
        "settings_path": rep.settings_path,
        "backup": rep.backup,
        "mcp_added_or_updated": rep.mcp_added,
        "hooks_added_or_updated": rep.hooks_added,
        "hooks_unchanged": rep.hooks_unchanged,
        "note": rep.note,
    }, indent=2, ensure_ascii=False))


@cmd_cc.command("uninstall")
@click.option("--scope", type=click.Choice(["project", "user"]), default="project")
def cc_uninstall(scope: str) -> None:
    """Remove only the entries omnicompany installed; leave the rest of settings.json alone."""
    rep = si.uninstall(scope=scope)  # type: ignore[arg-type]
    click.echo(json.dumps(rep, indent=2, ensure_ascii=False))


@cmd_cc.command("status")
@click.option("--scope", type=click.Choice(["project", "user"]), default="project")
def cc_status(scope: str) -> None:
    """Show whether the integration is currently installed at the given scope."""
    rep = si.status(scope=scope)  # type: ignore[arg-type]
    click.echo(json.dumps(rep, indent=2, ensure_ascii=False))


# ── ccdaemon lifecycle ([2026-05-09]DASHBOARD-DOGFOOD-RESILIENCE) ──
# 独立 uvicorn 进程, 持有 chat / pty 真业务. 跟 dashboard 控制面进程拆开,
# 确保 AI IDE 改控制面任意文件触发 reload 都不影响 chat 会话.

@cmd_cc.group("daemon")
def cc_daemon() -> None:
    """ccdaemon lifecycle — start / stop / restart / status."""


@cc_daemon.command("start")
@click.option("--port", type=int, default=8201, help="Listen port (default 8201).")
@click.option("--host", default="127.0.0.1")
@click.option("--reload/--no-reload", default=False,
              help="Enable file watcher reload (default off — daemon自动 reload 会"
                   "杀掉正在跑的 chat 会话, 改 ccdaemon 文件后请走 `omni cc daemon restart`).")
def cc_daemon_start(port: int, host: str, reload: bool) -> None:
    """Start the ccdaemon process (background)."""
    import subprocess
    import sys
    import os
    from omnicompany.dashboard.ccdaemon import lifecycle

    s = lifecycle.read_status()
    if s.alive:
        click.echo(json.dumps({"ok": False, "reason": "already running",
                                "pid": s.pid, "port": s.port}, indent=2))
        return

    log_path = lifecycle.log_file()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # 启动前 log 滚动 — 防长期 dogfood log 无限增长 (>10MB 自动轮转, 留 5 份历史)
    rotated = lifecycle.rotate_log_if_oversize()
    env = os.environ.copy()
    env["OMNI_CC_DAEMON_PORT"] = str(port)
    cmd = [
        sys.executable, "-m", "uvicorn",
        "omnicompany.dashboard.ccdaemon.main:app",
        "--host", host, "--port", str(port),
    ]
    if reload:
        cmd.extend(["--reload",
                    "--reload-dir", str(lifecycle._data_dir().parent / "src" / "omnicompany" / "dashboard" / "ccdaemon")])

    log_fd = open(log_path, "ab")
    creationflags = 0
    if sys.platform == "win32":
        # DETACHED_PROCESS 让子进程不跟 CLI 父进程绑, ctrl+c CLI 时 daemon 不死
        creationflags = 0x00000008  # DETACHED_PROCESS
    proc = subprocess.Popen(
        cmd, stdout=log_fd, stderr=subprocess.STDOUT,
        env=env, creationflags=creationflags,
    )
    # 不立刻关 log_fd, Popen 持有引用, 子进程退出时由 OS 释放
    click.echo(json.dumps({
        "ok": True, "pid": proc.pid, "port": port, "log": str(log_path),
        "log_rotated": rotated,
        "note": "daemon spawned; check status with `omni cc daemon status`",
    }, indent=2, ensure_ascii=False))


@cc_daemon.command("stop")
@click.option("--timeout", type=float, default=5.0,
              help="Seconds to wait for graceful shutdown before kill -9 / TerminateProcess.")
def cc_daemon_stop(timeout: float) -> None:
    """Stop the running ccdaemon (graceful → force after timeout)."""
    import os
    import sys
    import time
    import signal as _sig
    from omnicompany.dashboard.ccdaemon import lifecycle

    s = lifecycle.read_status()
    if not s.alive:
        click.echo(json.dumps({"ok": False, "reason": "not running"}, indent=2))
        return

    pid = s.pid
    assert pid is not None
    try:
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            CTRL_BREAK_EVENT = 1
            # GenerateConsoleCtrlEvent 仅对 process group 工作; DETACHED_PROCESS 起的没控制台
            # → 直接 TerminateProcess (Windows 没 SIGTERM 概念)
            PROCESS_TERMINATE = 0x0001
            h = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
            if h:
                kernel32.TerminateProcess(h, 0)
                kernel32.CloseHandle(h)
        else:
            os.kill(pid, _sig.SIGTERM)
            deadline = time.time() + timeout
            while lifecycle._pid_alive(pid) and time.time() < deadline:
                time.sleep(0.2)
            if lifecycle._pid_alive(pid):
                os.kill(pid, _sig.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError) as e:
        click.echo(json.dumps({"ok": False, "reason": f"kill failed: {e}"}, indent=2))
        return

    # 清陈旧 pid 文件 (lifecycle.read_status 已经会清, 但显式清更稳)
    lifecycle.clear_pid()
    click.echo(json.dumps({"ok": True, "killed_pid": pid}, indent=2))


@cc_daemon.command("restart")
@click.option("--port", type=int, default=8201)
@click.option("--host", default="127.0.0.1")
@click.pass_context
def cc_daemon_restart(ctx: click.Context, port: int, host: str) -> None:
    """Stop then start. Equivalent to `stop` followed by `start`."""
    from omnicompany.dashboard.ccdaemon import lifecycle
    import time

    s = lifecycle.read_status()
    if s.alive:
        ctx.invoke(cc_daemon_stop, timeout=5.0)
        # 等 OS 真释放端口
        for _ in range(20):
            if not lifecycle.read_status().alive:
                break
            time.sleep(0.2)
    ctx.invoke(cc_daemon_start, port=port, host=host, reload=False)


@cc_daemon.command("status")
def cc_daemon_status() -> None:
    """Show ccdaemon pid / port / alive."""
    from omnicompany.dashboard.ccdaemon import lifecycle
    s = lifecycle.read_status()
    click.echo(json.dumps({
        "alive": s.alive,
        "pid": s.pid,
        "port": s.port,
        "pid_file": str(lifecycle.pid_file()),
        "port_file": str(lifecycle.port_file()),
        "log_file": str(lifecycle.log_file()),
    }, indent=2, ensure_ascii=False))
