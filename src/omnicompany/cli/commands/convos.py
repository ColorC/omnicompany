# [OMNI] origin=ai-ide ts=2026-06-06 type=cli
"""omni convos — 列/搜/采纳(resume)别处已有的 claude code / codex 对话历史(给总控 AI 用)。

用户 2026-06-06: 总控能用 omni cli 列出/搜索/排序现有 codex & claude code 对话历史, 采纳(resume)成 subagent;
也能按 plan 查关联会话并 resume。这是"给 AI 用的 resume 模式"。

- list   : 列本机 ~/.claude / ~/.codex 的历史对话(按 mtime 排序); --plan 改为查 ccdaemon 里关联该 plan 的 chat 会话。
- search : 在历史对话里搜(匹配预览/目录/会话id)。
- adopt  : resume 某条对话, 采纳成 subagent(走 ccdaemon /cc/chat/sessions 的 adopt_session_id; caller_identity=subagent)。
"""
from __future__ import annotations

import json
import urllib.request

import click

from .._access import any_caller


def _scan() -> list[dict]:
    from omnicompany.dashboard.ccdaemon.import_routes import _scan_claude, _scan_codex
    return list(_scan_claude()) + list(_scan_codex())


def _daemon_base() -> str:
    from omnicompany.dashboard.ccdaemon import lifecycle
    s = lifecycle.read_status()
    if not (getattr(s, "alive", False) and getattr(s, "port", None)):
        raise click.ClickException("ccdaemon 未运行(先 `omni cc daemon start`)")
    return f"http://127.0.0.1:{s.port}"


def _http(method: str, url: str, body: dict | None = None, timeout: int = 60) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - 本机 daemon
        return json.loads(r.read().decode())


def _cc_sessions_by_plan(plan: str) -> list[dict]:
    base = _daemon_base()
    d = _http("GET", f"{base}/cc/chat/sessions?limit=200&include_archived=true")
    items = d.get("items") or d.get("sessions") or []
    return [
        {"provider": s.get("provider"), "session_id": s.get("claude_session_id") or s.get("id"),
         "cwd": s.get("cwd"), "mtime": s.get("started_at"), "preview": s.get("name") or s.get("last_message") or "",
         "active_plan": s.get("active_plan"), "id": s.get("id"), "alive": s.get("alive")}
        for s in items if s.get("active_plan") == plan
    ]


def _print(items: list[dict], as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(items, ensure_ascii=False, indent=2))
        return
    if not items:
        click.echo("(无)")
        return
    for s in items:
        prov = "Codex" if s.get("provider") == "codex" else "Claude"
        sid = (s.get("session_id") or "")[:14]
        cwd = s.get("cwd") or "?"
        prev = (s.get("preview") or "").replace("\n", " ")[:60]
        click.echo(f"  [{prov:6}] {sid}  {cwd}")
        if prev:
            click.echo(f"           {prev}")


@click.group("convos")
def cmd_convos() -> None:
    """列/搜/采纳(resume)已有 claude/codex 对话历史(给总控 AI 用)。"""


@cmd_convos.command("list")
@click.option("--provider", type=click.Choice(["claude_code", "codex"]), default=None)
@click.option("--cwd", default=None, help="按 cwd 子串过滤")
@click.option("--plan", default=None, help="改为查 ccdaemon 里关联该 plan 的 chat 会话")
@click.option("--limit", default=30, help="最多列几条")
@click.option("--json", "as_json", is_flag=True)
@any_caller
def cmd_convos_list(provider: str | None, cwd: str | None, plan: str | None, limit: int, as_json: bool) -> None:
    """列出现有对话(默认本机 ~/.claude/~/.codex, 按更新时间倒序)。"""
    if plan:
        _print(_cc_sessions_by_plan(plan)[:limit], as_json)
        return
    items = _scan()
    if provider:
        items = [s for s in items if s.get("provider") == provider]
    if cwd:
        items = [s for s in items if cwd.lower() in (s.get("cwd") or "").lower()]
    items.sort(key=lambda s: s.get("mtime", 0) or 0, reverse=True)
    _print(items[:limit], as_json)


@cmd_convos.command("search")
@click.argument("query")
@click.option("--provider", type=click.Choice(["claude_code", "codex"]), default=None)
@click.option("--limit", default=30)
@click.option("--json", "as_json", is_flag=True)
@any_caller
def cmd_convos_search(query: str, provider: str | None, limit: int, as_json: bool) -> None:
    """在历史对话里搜(匹配预览/目录/会话id, 不区分大小写)。"""
    q = query.lower()
    items = _scan()
    if provider:
        items = [s for s in items if s.get("provider") == provider]
    items = [s for s in items if q in f"{s.get('preview', '')} {s.get('cwd', '')} {s.get('session_id', '')}".lower()]
    items.sort(key=lambda s: s.get("mtime", 0) or 0, reverse=True)
    _print(items[:limit], as_json)


@cmd_convos.command("adopt")
@click.argument("provider", type=click.Choice(["claude_code", "codex"]))
@click.argument("session_id")
@click.option("--plan", default=None, help="关联 plan id")
@click.option("--cwd", default=None, help="工作目录(默认沿用原会话)")
@click.option("--effort", type=click.Choice(["low", "medium", "high", "xhigh", "max"]), default=None,
              help="N2b 推理强度档(仅 claude_code 生效), 省略=用模型默认")
@any_caller
def cmd_convos_adopt(provider: str, session_id: str, plan: str | None, cwd: str | None, effort: str | None) -> None:
    """resume 某条已有对话, 采纳成 subagent(总控可驱动 / 用户可接管)。"""
    base = _daemon_base()
    body: dict = {"adopt_session_id": session_id, "provider": provider}
    if cwd:
        body["cwd"] = cwd
    if plan:
        body["active_plan"] = plan
    if effort:
        body["effort"] = effort
    try:
        data = _http("POST", f"{base}/cc/chat/sessions", body, timeout=120)
    except Exception as e:  # noqa: BLE001
        raise click.ClickException(f"采纳失败: {e}") from e
    click.echo(json.dumps(
        {"ok": True, "subagent_id": data.get("id"), "adopted": data.get("adopted"),
         "provider": data.get("provider"), "active_plan": data.get("active_plan")},
        ensure_ascii=False, indent=2,
    ))


__all__ = ["cmd_convos"]
