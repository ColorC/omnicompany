# [OMNI] origin=claude-code ts=2026-05-01 type=infra
# [OMNI] material_id="material:dashboard.cc_wrapper.http_router.endpoints.py"
"""HTTP + WebSocket API for the Claude Code wrapper.

Endpoints
---------
GET  /api/cc/sessions                — list live sessions
POST /api/cc/sessions                — spawn a new claude session
DELETE /api/cc/sessions/{sid}        — kill a session
WS   /api/cc/sessions/{sid}/ws       — bidirectional terminal IO

WebSocket protocol (newline-free JSON envelopes both directions)
----------------------------------------------------------------
client → server:
  {"type":"input", "data":"<utf-8 keystrokes>"}
  {"type":"resize", "cols":120, "rows":32}
server → client:
  {"type":"snapshot", "chunks":["...", ...]}   # sent once, on attach
  {"type":"output", "data":"<utf-8 chunk>"}
  {"type":"exit", "reason":"..."}              # session closed
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .pty import (
    DEFAULT_COLS, DEFAULT_ROWS, get_manager, resolve_claude_cmd,
    list_recoverable_sessions,
)
from . import installer as si

logger = logging.getLogger(__name__)

cc_router = APIRouter(prefix="/cc", tags=["cc-wrapper"])


class CreateSessionBody(BaseModel):
    cmd: list[str] | None = Field(default=None, description="Override command; defaults to claude CLI on PATH.")
    cwd: str | None = Field(default=None, description="Working directory; defaults to server CWD.")
    cols: int = DEFAULT_COLS
    rows: int = DEFAULT_ROWS
    safe_mode: bool = Field(
        default=False,
        description="If true, spawn vanilla `claude` (permission prompts ON). "
                    "Default false → adds `--dangerously-skip-permissions` so the "
                    "in-dashboard agent doesn't pepper you with prompts. All tool "
                    "calls remain visible via PreToolUse trace events.",
    )


@cc_router.get("/health")
async def cc_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "claude_cli_found": resolve_claude_cmd() is not None,
        "session_count": len(get_manager().list_meta()),
    }


# ── settings install / status (single source of truth — dashboard button calls this,
#    CLI `omni cc install` calls the same `settings_installer` module) ──

@cc_router.get("/install/status")
async def install_status(scope: str = "project") -> dict[str, Any]:
    if scope not in ("project", "user"):
        raise HTTPException(400, "scope must be 'project' or 'user'")
    return si.status(scope=scope)  # type: ignore[arg-type]


@cc_router.post("/install")
async def install(scope: str = "project") -> dict[str, Any]:
    if scope not in ("project", "user"):
        raise HTTPException(400, "scope must be 'project' or 'user'")
    rep = si.install(scope=scope)  # type: ignore[arg-type]
    return {
        "settings_path": rep.settings_path,
        "backup": rep.backup,
        "mcp_added_or_updated": rep.mcp_added,
        "hooks_added_or_updated": rep.hooks_added,
        "hooks_unchanged": rep.hooks_unchanged,
        "note": rep.note,
        "equivalent_cli": f"omni cc install --scope {scope}",
    }


@cc_router.delete("/install")
async def uninstall(scope: str = "project") -> dict[str, Any]:
    if scope not in ("project", "user"):
        raise HTTPException(400, "scope must be 'project' or 'user'")
    rep = si.uninstall(scope=scope)  # type: ignore[arg-type]
    rep["equivalent_cli"] = f"omni cc uninstall --scope {scope}"
    return rep


@cc_router.get("/sessions")
async def list_sessions(
    include_recoverable: bool = True,
    active_plan: str | None = None,
) -> dict[str, Any]:
    """Return live in-process sessions plus (optionally) recoverable ones whose
    PTY died (e.g. across a backend restart) but whose claude conversation log
    still exists on disk and can be revived via `--resume`.

    `active_plan` 反查过滤 (CC-PLAN-SESSION-CONTEXT 段四-1): 只列绑定指定 plan_id
    的 session, 用于 plan 详情页"关联 cc_sessions"块.
    """
    alive = get_manager().list_meta()
    if active_plan:
        alive = [a for a in alive if a.get("active_plan") == active_plan]
    out: dict[str, Any] = {"items": alive, "alive_count": len(alive)}
    if include_recoverable:
        # exclude any recoverable id that's also in `alive` (just in case the user
        # already resumed it this run)
        alive_ids = {a["id"] for a in alive}
        rec = [r for r in list_recoverable_sessions() if r["id"] not in alive_ids]
        if active_plan:
            rec = [r for r in rec if r.get("active_plan") == active_plan]
        out["recoverable"] = rec
        out["recoverable_count"] = len(rec)
    return out


@cc_router.post("/sessions")
async def create_session(body: CreateSessionBody) -> dict[str, Any]:
    try:
        sess = await get_manager().create(
            cmd=body.cmd,
            cwd=body.cwd,
            cols=body.cols,
            rows=body.rows,
            safe_mode=body.safe_mode,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return sess.to_meta()


@cc_router.post("/sessions/{recoverable_id}/resume")
async def resume_session(recoverable_id: str) -> dict[str, Any]:
    """Spawn a fresh PTY pointing at the same claude conversation (`claude --resume`).
    Returns the NEW session's metadata (it has a new pty id; the old one stays in
    cc_sessions.json marked terminated)."""
    try:
        sess = await get_manager().resume(recoverable_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    out = sess.to_meta()
    out["resumed_from"] = recoverable_id
    return out


@cc_router.delete("/sessions/{sid}")
async def kill_session(sid: str) -> dict[str, Any]:
    ok = await get_manager().kill(sid)
    if not ok:
        raise HTTPException(status_code=404, detail=f"session not found: {sid}")
    return {"ok": True, "id": sid}


# ── S16: session context aggregator ─────────────────────────────────────────
#
# GET /sessions/{sid}/context  →  structured asset summary (per user round 21 b)
# Three sections served as one bundle:
#   1. context: active plan / cwd / claude_session_id / user-added (work_type, standards)
#   2. modified_files: files this session edited (Edit/Write/MultiEdit/NotebookEdit)
#   3. added_workers / added_materials: new files matching worker.py / materials.py
#                                       / formats.py patterns under packages/
# Plus bash_writes: best-effort extraction of `> path`, `tee path` etc. from Bash calls.

import sqlite3
import re
from pathlib import Path
from .pty import _read_meta_store


def _events_db() -> Path:
    """Path to the unified events.db (where hooks write trace events)."""
    state_dir = os.environ.get("OMNI_CC_DAEMON_STATE_DIR")
    if state_dir:
        return Path(state_dir) / "ide_events.db"
    try:
        from omnicompany.core.config import resolve_unified_db_path
        return resolve_unified_db_path("ide_events.db")
    except Exception:
        pass
    from omnicompany.core.config import omni_workspace_root
    return omni_workspace_root() / "data" / "ide_events.db"


def _query_session_events(sid: str) -> list[dict]:
    """Pull all events for cc_<sid> trace from events.db."""
    db = _events_db()
    if not db.is_file():
        return []
    try:
        conn = sqlite3.connect(str(db), timeout=2.0)
        rows = conn.execute(
            "SELECT data FROM events WHERE trace_id=? ORDER BY timestamp", (sid,),
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    out: list[dict] = []
    for (raw,) in rows:
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out


_BASH_REDIRECT = re.compile(r"(?:>\s*|>>\s*|tee\s+(?:-a\s+)?)([^\s'\"|&;]+)")
# Worker / Team / Material file patterns under `packages/`.
_WORKER_PAT  = re.compile(r"packages[/\\][^/\\]+[/\\]workers[/\\][^/\\]+\.py$")
_TEAM_PAT    = re.compile(r"packages[/\\][^/\\]+[/\\]team[^/\\]*\.py$", re.IGNORECASE)
_MATERIAL_PAT = re.compile(r"packages[/\\][^/\\]+[/\\](?:materials|formats)\.py$")


def _aggregate_session_io(events: list[dict]) -> dict:
    """Walk events, classify into modified_files / bash_writes / added_workers / added_materials."""
    modified: dict[str, dict] = {}  # path -> {path, count, last_ts, last_tool}
    bash_writes: list[dict] = []
    added_workers: list[str] = []
    added_materials: list[str] = []
    seen_assets: set[str] = set()

    def _bump(path: str, ts: str, tool: str):
        if not path:
            return
        if path not in modified:
            modified[path] = {"path": path, "count": 0, "last_ts": ts, "last_tool": tool}
        modified[path]["count"] += 1
        if ts > modified[path]["last_ts"]:
            modified[path]["last_ts"] = ts
            modified[path]["last_tool"] = tool

    for ev in events:
        if ev.get("event_type") != "agent.tool.call":
            continue
        p = ev.get("payload") or {}
        tool = p.get("tool", "")
        args = p.get("args") or {}
        ts = ev.get("timestamp") or ""

        if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            fp = args.get("file_path") or args.get("notebook_path") or ""
            if fp:
                _bump(fp, ts, tool)
                if fp not in seen_assets:
                    seen_assets.add(fp)
                    if _WORKER_PAT.search(fp): added_workers.append(fp)
                    elif _TEAM_PAT.search(fp): added_workers.append(fp)  # treat team as same bucket
                    elif _MATERIAL_PAT.search(fp): added_materials.append(fp)

        elif tool == "Bash":
            cmd = args.get("command") or ""
            for m in _BASH_REDIRECT.finditer(cmd):
                target = m.group(1)
                bash_writes.append({
                    "path": target,
                    "snippet": cmd[:120],
                    "ts": ts,
                })
                # also count as modified
                _bump(target, ts, "Bash")

    # Convert modified dict to sorted list (most-recent first)
    mod_list = sorted(modified.values(), key=lambda x: x["last_ts"], reverse=True)
    return {
        "modified_files": mod_list,
        "bash_writes": bash_writes,
        "added_workers": added_workers,
        "added_materials": added_materials,
    }


@cc_router.get("/sessions/{sid}/context")
async def get_session_context(sid: str) -> dict[str, Any]:
    store = _read_meta_store()
    entry = store.get(sid) or {}
    if not entry:
        try:
            from .chat import get_chat_manager
            chat_sess = get_chat_manager()._sessions.get(sid)
            if chat_sess is not None:
                entry = chat_sess.to_meta()
        except Exception:
            entry = {}
    events = _query_session_events(sid)
    io = _aggregate_session_io(events)
    active_plan = entry.get("active_plan")
    # plan_meta = plan.md frontmatter, project_meta = 所属 project 的 project.md frontmatter
    # 两者都是真信息源 (明文 yaml), AI IDE / Claude Code 共编共看
    plan_meta: dict[str, Any] = {}
    project_meta: dict[str, Any] = {}
    if active_plan:
        try:
            from omnicompany.dashboard.controlplane.plans import parse_plan_frontmatter, parse_project_meta, _plans_root
            plan_meta = parse_plan_frontmatter(_plans_root() / active_plan / "plan.md")
            project_meta = parse_project_meta(active_plan)
        except Exception:
            plan_meta = {}
            project_meta = {}
    try:
        from .context_progressive import resolve_progressive_context
        resolved_context = resolve_progressive_context(
            active_plan=active_plan,
            cwd=entry.get("cwd"),
            plan_meta=plan_meta,
        )
    except Exception as exc:
        resolved_context = {
            "plan_id": active_plan,
            "contexts": [],
            "total": 0,
            "missing": [],
            "missing_total": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }
    # PTY alive 由 PtyManager 决定；chat session 由 cc_sessions.json 的 ended_at 判定。
    alive = sid in get_manager()._sessions if hasattr(get_manager(), "_sessions") else False
    if entry.get("kind") == "chat" and not entry.get("ended_at"):
        alive = True
    return {
        "session_id": sid,
        "kind": "cc",
        "context": {
            "active_plan": active_plan,
            "plan_meta": plan_meta,
            "project_meta": project_meta,
            "cwd": entry.get("cwd"),
            "provider": entry.get("provider") or entry.get("kind") or "claude_code",
            "claude_session_id": entry.get("claude_session_id"),
            "started_at": entry.get("started_at"),
            "ended_at": entry.get("ended_at"),
            "agent_state": "alive" if alive else "recoverable" if entry.get("ended_at") else "ended",
            "user_context": entry.get("user_context") or {},  # legacy fallback (deprecate)
            "resolved_context": resolved_context,
        },
        **io,
        "event_count": len(events),
    }


# (REMOVED 2026-05-02 round 4) PATCH /sessions/{sid}/context with UserContextPatch
# 旧设计: work_type / standards / notes 写到 cc_sessions.json.user_context (私有 JSON 字段)
# 新设计: 这些值是 plan.md frontmatter (work_type / standards / project / exit_criteria)
#         用户编辑 plan.md 即改值, 跟现有目录有机结合, 明文人和 agent 都读同一份
# 旧 cc_sessions.json.user_context 字段不删 (avoid breaking existing entries),
# context endpoint 仍在 fallback 读 (legacy compat) — 但不再写入新值
# CLI 等价 mirror 也撤回, 不做 `omni cc context set`


# ── plan binding switcher (CC-PLAN-SESSION-CONTEXT 段三-1) ───────────────────
#
# PATCH /sessions/{sid}/active_plan body={plan_id|null}
#   - 显式切 cc_session 绑定的 plan, 跟 omni plan use <id> CLI 同源逻辑
#   - 走 pty_service.update_meta_field 写 cc_sessions.json (持久, 跨重启)
#   - 同步更新 in-memory PtySession.active_plan (alive session)
#   - plan_id=null 解绑
#   - 返回新 state + alive 是否立即生效说明
#
# 段二审议点 (待用户拍板): alive 进程切 plan 后是否立即生效?
#   现状: 只更新元数据 + in-memory, 已运行的 claude code 进程当 turn 注入 context 已
#   定型, 下次 SessionStart 才看到新 plan. 重注入留 TODO 待用户拍板 a/b/c.

from .pty import update_meta_field as _pty_update_meta


class ActivePlanPatch(BaseModel):
    plan_id: str | None = Field(
        default=None,
        description="Plan id relative to docs/plans/ (e.g. `_infra/dashboard/[2026-05-03]CC-PLAN-SESSION-CONTEXT`). null 解绑.",
    )


def _validate_plan_id(plan_id: str) -> Path:
    """Resolve plan_id to absolute dir, refusing path traversal / non-existent.

    Raises HTTPException on bad input.
    """
    from omnicompany.core.config import omni_workspace_root
    plans_root = omni_workspace_root() / "docs" / "plans"
    if "../" in plan_id or "..\\" in plan_id or plan_id.startswith("/") or plan_id.startswith("\\"):
        raise HTTPException(400, f"invalid plan_id (path traversal): {plan_id!r}")
    candidate = (plans_root / plan_id).resolve()
    try:
        candidate.relative_to(plans_root.resolve())
    except ValueError:
        raise HTTPException(400, f"plan_id escapes plans root: {plan_id!r}")
    if not candidate.is_dir():
        raise HTTPException(404, f"plan dir not found: {plan_id!r}")
    if not (candidate / "plan.md").is_file():
        raise HTTPException(404, f"plan.md missing in {plan_id!r}")
    return candidate


@cc_router.patch("/sessions/{sid}/active_plan")
async def patch_active_plan(sid: str, body: ActivePlanPatch) -> dict[str, Any]:
    """Switch (or unbind) the plan bound to this cc_session.

    Persists to `cc_sessions.json` and updates in-memory `PtySession.active_plan`
    if the session is alive. **Does not** force-reinject context into a running
    claude — that requires a SessionStart (i.e. /clear or /restart). See timing
    note in the response.
    """
    store = _read_meta_store()
    chat_sess = None
    chat_mgr = None
    try:
        from .chat import get_chat_manager
        chat_mgr = get_chat_manager()
        chat_sess = chat_mgr._sessions.get(sid)
    except Exception as exc:
        logger.warning("patch_active_plan: chat manager lookup failed: %s", exc)
    if sid not in store and sid not in get_manager()._sessions and chat_sess is None:
        raise HTTPException(404, f"session not found: {sid}")

    plan_id = body.plan_id
    if plan_id:
        _validate_plan_id(plan_id)  # raises HTTPException on bad

    # 1. persistent metadata + change marker (UserPromptSubmit hook reads this
    #    to re-inject plan_meta on the next user turn — alive 进程 b 方案)
    import time as _time
    now_ts = _time.time()
    if plan_id is None:
        # explicit unbind — write null directly (update_meta_field skips None values)
        cur = store.get(sid) or {}
        cur["active_plan"] = None
        cur["active_plan_changed_ts"] = now_ts
        store[sid] = cur
        from .pty import _write_meta_store
        _write_meta_store(store)
    else:
        _pty_update_meta(sid, active_plan=plan_id, active_plan_changed_ts=now_ts)

    # 2. in-memory PtySession (if alive)
    sess = get_manager().get(sid)
    alive = False
    if sess is not None:
        sess.active_plan = plan_id
        alive = True

    # 2b. in-memory CcChatSession (if it's a chat session — SessionContextPanel
    #     always routes through ccApi regardless of session kind, so we must also
    #     update the chat manager's in-memory object for _maybe_inject_plan to
    #     pick up the change on the next user turn)
    if not alive:
        logger.info("patch_active_plan 2b: sid=%s chat_mgr_sessions=%s found=%s",
                    sid, list(chat_mgr._sessions.keys())[:5] if chat_mgr is not None else [],
                    chat_sess is not None)
        if chat_sess is not None:
            chat_sess.active_plan = plan_id
            alive = chat_sess.ended_at is None
            try:
                chat_mgr.schedule_context_event(
                    chat_sess,
                    trigger="plan_switch",
                    switched=True,
                )
            except AttributeError:
                pass

    # 3. CLI's cc_session_active.json — if this sid matches the currently active
    # trace_id (the one the user is "in"), mirror the change so omni plan current
    # picks it up next.
    try:
        from omnicompany.packages.services._core.identity import (
            current_session_meta,
            record_active_session,
        )
        meta = current_session_meta()
        if meta.get("pty_id") == sid or meta.get("trace_id") == sid:
            record_active_session(
                trace_id=meta.get("trace_id") or sid,
                claude_session_id=meta.get("claude_session_id"),
                pty_id=sid,
                active_plan=plan_id,
                cwd=meta.get("cwd"),
                source="web_patch_active_plan",
            )
    except Exception as e:
        logger.warning("active_plan PATCH: identity mirror failed: %s", e)

    # 4. return new state + timing note
    #    b 方案: alive 进程 UserPromptSubmit hook 会在下条用户输入触发时重注入 plan_meta
    return {
        "session_id": sid,
        "active_plan": plan_id,
        "alive": alive,
        "effective": "next_user_turn" if alive else "immediate",
        "note": (
            "Already-running claude code: the new plan_meta will be auto-injected "
            "via UserPromptSubmit hook on the NEXT user turn (no /clear needed). "
            "The current turn's already-cached system prompt is unchanged."
            if alive
            else "Session is not alive; new bindings apply when it's resumed."
        ),
    }


@cc_router.websocket("/sessions/{sid}/ws")
async def session_ws(ws: WebSocket, sid: str) -> None:
    await ws.accept()
    mgr = get_manager()
    try:
        sess, queue, snapshot = await mgr.attach(sid)
    except KeyError:
        await ws.send_text(json.dumps({"type": "exit", "reason": "session not found"}))
        await ws.close()
        return

    # 1) replay buffered output so xterm can paint the current screen
    if snapshot:
        await ws.send_text(json.dumps({"type": "snapshot", "chunks": snapshot}))

    import asyncio

    async def pump_out() -> None:
        # CC-PLAN-SESSION-CONTEXT 段五 (2026-05-05): drain queue 把连续 chunks 拼一
        # 帧再发. 当 reader 突 burst 时, 这里少发 N-1 个 WS 帧 + 少 N-1 次 JSON 编码.
        # asyncio.QueueEmpty 当 sentinel — 没东西就发当前 buf, 等下个 await get().
        try:
            while True:
                chunk = await queue.get()
                # try to drain extra without blocking
                while True:
                    try:
                        chunk += queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                await ws.send_text(json.dumps({"type": "output", "data": chunk}))
        except (WebSocketDisconnect, RuntimeError):
            pass

    out_task = asyncio.create_task(pump_out(), name=f"cc-ws-out-{sid}")
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            t = msg.get("type")
            if t == "input":
                data = msg.get("data", "")
                if isinstance(data, str) and data:
                    try:
                        await mgr.write(sid, data)
                    except KeyError:
                        break
            elif t == "resize":
                try:
                    await mgr.resize(sid, msg.get("cols", DEFAULT_COLS), msg.get("rows", DEFAULT_ROWS))
                except KeyError:
                    break
            # Unknown types are silently ignored.
    except WebSocketDisconnect:
        pass
    finally:
        out_task.cancel()
        mgr.detach(sess, queue)
        try:
            await ws.close()
        except RuntimeError:
            pass
