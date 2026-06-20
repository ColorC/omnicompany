# [OMNI] origin=claude-code ts=2026-05-01 type=infra
# [OMNI] material_id="material:dashboard.cc_wrapper.pty_manager.session_lifecycle.py"
"""PTY session manager for the Claude Code wrapper.

Each PtySession owns:
- one `winpty.PTY` child process (e.g. `claude.cmd`),
- a background asyncio task that polls the PTY non-blocking and fans chunks
  out to every attached WebSocket subscriber,
- a ring buffer so late-attaching / reconnecting clients can replay recent
  output (xterm.js needs the last screenful to repaint correctly).

Sessions are kept alive after the last subscriber detaches (so the user can
close a browser tab and keep the claude CLI running). They reap themselves
when the child exits OR after `IDLE_TTL_S` with zero subscribers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Session lives this long after its last subscriber leaves before reap.
IDLE_TTL_S = 30 * 60
# Per-session output ring buffer cap (chunks, not bytes).
RING_CAP = 5000
# How often the read loop polls when the PTY has no data.
# CC-PLAN-SESSION-CONTEXT 段五 (2026-05-05): 20ms → 2ms. baseline bench 显示
# 端到端 echo 延迟 p50 30.8ms, 主要是这里. 改 2ms 后 p50 < 10ms 预期.
# CPU 代价: 空轮询从 50/s → 500/s, 每次 to_thread + read syscall 仍可控.
READ_IDLE_SLEEP_S = 0.002
# Reader hot-drain: 拿到非空 chunk 后, 不睡接连再 read 几次, 把已 buffer 的字节
# 一次取完, 一帧 fan out. 减 JSON 编码 + WS 帧次, 减重复 to_thread 切换.
READ_HOT_DRAIN_MAX = 4
# Default terminal geometry.
DEFAULT_COLS = 120
DEFAULT_ROWS = 32


def _meta_store_path() -> Path:
    """Where we persist session metadata so they survive backend restart.

    Schema: { "<pty_id>": { id, cmd, cwd, started_at, ended_at,
                            claude_session_id, active_plan, exit_reason } }
    """
    # repo_root / data / cc_sessions.json — same dir as ide_events.db
    state_dir = os.environ.get("OMNI_CC_DAEMON_STATE_DIR")
    if state_dir:
        return Path(state_dir) / "cc_sessions.json"
    from omnicompany.core.config import omni_workspace_root
    return omni_workspace_root() / "data" / "cc_sessions.json"


@dataclass
class PtySession:
    id: str
    cmd: list[str]
    cwd: str
    cols: int
    rows: int
    started_at: float
    pty: Any = None
    subscribers: set[asyncio.Queue[str]] = field(default_factory=set)
    ring: deque[str] = field(default_factory=lambda: deque(maxlen=RING_CAP))
    reader_task: asyncio.Task | None = None
    last_detach_at: float = 0.0
    closed: bool = False
    # populated by SessionStart hook (via metadata file) once claude announces its session id
    claude_session_id: str | None = None
    active_plan: str | None = None

    def to_meta(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cmd": self.cmd,
            "cwd": self.cwd,
            "cols": self.cols,
            "rows": self.rows,
            "started_at": self.started_at,
            "alive": bool(self.pty and self.pty.isalive()),
            "subscribers": len(self.subscribers),
            "buffered_chunks": len(self.ring),
            "claude_session_id": self.claude_session_id,
            "active_plan": self.active_plan,
            "status": "alive",
        }


def resolve_claude_cmd(safe_mode: bool = False) -> list[str] | None:
    """Locate the `claude` CLI on PATH. Returns None if not installed.

    By default (safe_mode=False) we pass `--dangerously-skip-permissions` so the
    in-dashboard wrapper doesn't pepper the user with permission prompts that
    interrupt agent flow. All tool calls remain visible via our PreToolUse trace
    hook, so the audit trail is preserved.
    Pass safe_mode=True to spawn vanilla claude with permission prompts.
    """
    for name in ("claude.cmd", "claude.exe", "claude"):
        p = shutil.which(name)
        if p:
            return [p] if safe_mode else [p, "--dangerously-skip-permissions"]
    return None


# ── on-disk session metadata store ──────────────────────────────────────────


def _read_meta_store() -> dict[str, dict[str, Any]]:
    p = _meta_store_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8") or "{}") or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_meta_store(store: dict[str, dict[str, Any]]) -> None:
    p = _meta_store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        logger.warning("cc_sessions.json write failed: %s", e)


def _claude_jsonl_for(cwd: str, claude_session_id: str | None) -> Path | None:
    """Best-effort path to claude's own conversation log so we can verify a
    session is actually resumable via `claude --resume`.

    Claude's encoding (observed from real `~/.claude/projects/`):
      `C:\\Users\\user`           → `C--Users-user`
      `E:\\workspace\\omnicompany` → `E--workspace-omnicompany`
    Rule: colon → `--`, backslash/slash → `-`, no leading marker.
    """
    if not claude_session_id:
        return None
    enc = cwd.replace(":", "--").replace("\\", "-").replace("/", "-")
    base = Path.home() / ".claude" / "projects" / enc
    p = base / f"{claude_session_id}.jsonl"
    return p if p.is_file() else None


def list_recoverable_sessions() -> list[dict[str, Any]]:
    """Sessions that are no longer alive in PtyManager but had a claude_session_id
    captured — `claude --resume <id>` may continue them. We don't gate on jsonl
    existence (claude only writes the file after the first user turn, and we want
    to surface even ephemeral sessions so the user knows they happened)."""
    out: list[dict[str, Any]] = []
    for sid, m in _read_meta_store().items():
        if m.get("ended_at") is None:
            continue
        csid = m.get("claude_session_id")
        if not csid:
            continue
        jsonl = _claude_jsonl_for(m.get("cwd") or "", csid)
        out.append({
            **m,
            "alive": False,
            "status": "recoverable",
            "claude_jsonl": str(jsonl) if jsonl else None,
            "jsonl_present": jsonl is not None,
        })
    return sorted(out, key=lambda x: x.get("ended_at") or 0, reverse=True)


def update_meta_field(sid: str, **fields: Any) -> None:
    """External hook helper — write new field(s) for a session id (e.g. `claude_session_id`)."""
    if not sid:
        return
    store = _read_meta_store()
    cur = store.get(sid) or {}
    cur.update({k: v for k, v in fields.items() if v is not None})
    store[sid] = cur
    _write_meta_store(store)


class PtyManager:
    """Process-wide registry of live PTY sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, PtySession] = {}
        self._lock = asyncio.Lock()
        self._reaper_task: asyncio.Task | None = None

    def list_meta(self) -> list[dict[str, Any]]:
        return [s.to_meta() for s in self._sessions.values()]

    def get(self, sid: str) -> PtySession | None:
        return self._sessions.get(sid)

    async def create(
        self,
        cmd: list[str] | None,
        cwd: str | None,
        cols: int = DEFAULT_COLS,
        rows: int = DEFAULT_ROWS,
        safe_mode: bool = False,
        resume_claude_session_id: str | None = None,
    ) -> PtySession:
        from winpty import PTY  # imported lazily so non-Windows hosts can import this module

        if cmd is None:
            resolved = resolve_claude_cmd(safe_mode=safe_mode)
            if resolved is None:
                raise RuntimeError(
                    "claude CLI not found on PATH. Install Claude Code first."
                )
            cmd = resolved
            if resume_claude_session_id:
                cmd = cmd + ["--resume", resume_claude_session_id]

        cwd = cwd or os.getcwd()
        if not Path(cwd).is_dir():
            raise ValueError(f"cwd does not exist: {cwd}")

        # mint our session id BEFORE spawn so we can hand it to the child via env;
        # hooks read OMNI_CC_PTY_ID and use it as their trace_id (so the dashboard
        # cc_session entity can correlate to its own trace events).
        sid = uuid.uuid4().hex[:16]

        # Inherit current env, then add our marker. winpty wants `KEY=VAL\0KEY=VAL\0\0`.
        env_dict = dict(os.environ)
        env_dict["OMNI_CC_PTY_ID"] = sid
        env_str = "".join(f"{k}={v}\0" for k, v in env_dict.items()) + "\0"

        pty = PTY(cols, rows)
        appname = cmd[0]
        cmdline = " ".join(_quote_arg(a) for a in cmd[1:]) if len(cmd) > 1 else None
        ok = pty.spawn(appname, cmdline=cmdline, cwd=cwd, env=env_str)
        if not ok:
            raise RuntimeError(f"PTY spawn failed for {cmd!r}")
        sess = PtySession(
            id=sid,
            cmd=cmd,
            cwd=cwd,
            cols=cols,
            rows=rows,
            started_at=time.time(),
            pty=pty,
        )
        sess.reader_task = asyncio.create_task(self._reader_loop(sess), name=f"pty-read-{sid}")
        async with self._lock:
            self._sessions[sid] = sess
        if self._reaper_task is None or self._reaper_task.done():
            self._reaper_task = asyncio.create_task(self._reaper_loop(), name="pty-reaper")

        # Persist metadata so this session can be discovered after a backend restart.
        store = _read_meta_store()
        store[sid] = {
            "id": sid,
            "cmd": cmd,
            "cwd": cwd,
            "started_at": sess.started_at,
            "ended_at": None,
            "claude_session_id": resume_claude_session_id,  # filled in by SessionStart hook on first turn
            "active_plan": None,
            "resumed_from_claude_session_id": resume_claude_session_id,
        }
        _write_meta_store(store)
        logger.info("pty_session created id=%s cmd=%s", sid, cmd)
        return sess

    async def resume(self, recoverable_id: str) -> PtySession:
        """Resume a previously-killed session by spawning a fresh PTY with `claude --resume`.

        Looks up the metadata entry for `recoverable_id`, gets its claude_session_id +
        cwd, then spawns a new session pointing at the same conversation. Returns the
        new PtySession (which has a new pty_id).
        """
        store = _read_meta_store()
        entry = store.get(recoverable_id)
        if not entry:
            raise KeyError(f"no metadata for session {recoverable_id}")
        csid = entry.get("claude_session_id")
        if not csid:
            raise RuntimeError(f"session {recoverable_id} has no claude_session_id (was it ever fully started?)")
        if entry.get("ended_at") is None:
            raise RuntimeError(f"session {recoverable_id} is still marked alive; kill it first or use its WS")
        cwd = entry.get("cwd") or os.getcwd()
        # we don't reuse the user's original cmd[0] — claude.cmd path may have moved
        return await self.create(cmd=None, cwd=cwd, safe_mode=False, resume_claude_session_id=csid)

    async def attach(self, sid: str) -> tuple[PtySession, asyncio.Queue[str], list[str]]:
        """Subscribe a client. Returns (session, queue, replay-snapshot)."""
        sess = self._sessions.get(sid)
        if sess is None or sess.closed:
            raise KeyError(sid)
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=1024)
        snapshot = list(sess.ring)
        sess.subscribers.add(q)
        return sess, q, snapshot

    def detach(self, sess: PtySession, q: asyncio.Queue[str]) -> None:
        sess.subscribers.discard(q)
        if not sess.subscribers:
            sess.last_detach_at = time.time()

    async def write(self, sid: str, data: str) -> None:
        sess = self._sessions.get(sid)
        if sess is None or sess.closed or sess.pty is None:
            raise KeyError(sid)
        # winpty PTY.write expects str; runs in thread to avoid blocking loop.
        await asyncio.to_thread(sess.pty.write, data)

    async def resize(self, sid: str, cols: int, rows: int) -> None:
        sess = self._sessions.get(sid)
        if sess is None or sess.closed or sess.pty is None:
            raise KeyError(sid)
        cols = max(2, min(500, int(cols)))
        rows = max(1, min(200, int(rows)))
        await asyncio.to_thread(sess.pty.set_size, cols, rows)
        sess.cols = cols
        sess.rows = rows

    async def kill(self, sid: str) -> bool:
        sess = self._sessions.get(sid)
        if sess is None:
            return False
        await self._close_session(sess, reason="kill")
        return True

    async def _reader_loop(self, sess: PtySession) -> None:
        """Pump PTY → subscribers + ring buffer until child exits.

        CC-PLAN-SESSION-CONTEXT 段五 (2026-05-05): chunk 热时连读排干 (最多
        READ_HOT_DRAIN_MAX 次), 把可能已经在 PTY buffer 里的连续字节合并到一帧.
        减 JSON 编码 + WS 帧次, 减重复 to_thread 切换开销.
        """
        try:
            while not sess.closed:
                try:
                    chunk = await asyncio.to_thread(sess.pty.read, False)
                except Exception as e:  # winpty.WinptyError, etc.
                    logger.warning("pty_session %s read error: %s", sess.id, e)
                    break
                if chunk:
                    # hot-drain: 不睡再多读几次, 合并 burst
                    for _ in range(READ_HOT_DRAIN_MAX):
                        try:
                            more = await asyncio.to_thread(sess.pty.read, False)
                        except Exception:
                            break
                        if not more:
                            break
                        chunk += more
                    sess.ring.append(chunk)
                    dead: list[asyncio.Queue[str]] = []
                    for q in sess.subscribers:
                        try:
                            q.put_nowait(chunk)
                        except asyncio.QueueFull:
                            # slow consumer — drop this client
                            dead.append(q)
                    for q in dead:
                        sess.subscribers.discard(q)
                else:
                    if not sess.pty.isalive():
                        # process exited; do one final drain attempt then stop
                        tail = await asyncio.to_thread(sess.pty.read, False)
                        if tail:
                            sess.ring.append(tail)
                            for q in sess.subscribers:
                                try:
                                    q.put_nowait(tail)
                                except asyncio.QueueFull:
                                    pass
                        break
                    await asyncio.sleep(READ_IDLE_SLEEP_S)
        finally:
            await self._close_session(sess, reason="reader-exit")

    async def _close_session(self, sess: PtySession, *, reason: str) -> None:
        if sess.closed:
            return
        sess.closed = True
        for q in list(sess.subscribers):
            try:
                q.put_nowait(f"\r\n[wrapper] session closed ({reason})\r\n")
            except asyncio.QueueFull:
                pass
        try:
            if sess.pty is not None and sess.pty.isalive():
                sess.pty.close() if hasattr(sess.pty, "close") else None
        except Exception:
            pass
        async with self._lock:
            self._sessions.pop(sess.id, None)

        # Mark terminated in the persistent store (don't delete — the session may
        # still be resumable via claude --resume <claude_session_id>).
        try:
            store = _read_meta_store()
            entry = store.get(sess.id)
            if entry is not None:
                entry["ended_at"] = time.time()
                entry["exit_reason"] = reason
                # carry forward claude_session_id / active_plan if hooks set them
                if sess.claude_session_id and not entry.get("claude_session_id"):
                    entry["claude_session_id"] = sess.claude_session_id
                if sess.active_plan and not entry.get("active_plan"):
                    entry["active_plan"] = sess.active_plan
                store[sess.id] = entry
                _write_meta_store(store)
        except Exception as e:
            logger.warning("meta-store close-update failed: %s", e)
        logger.info("pty_session closed id=%s reason=%s", sess.id, reason)

    async def _reaper_loop(self) -> None:
        """Reap idle sessions (no subscribers for IDLE_TTL_S)."""
        try:
            while True:
                await asyncio.sleep(60)
                now = time.time()
                stale = [
                    s for s in list(self._sessions.values())
                    if not s.subscribers
                    and s.last_detach_at
                    and (now - s.last_detach_at) > IDLE_TTL_S
                ]
                for s in stale:
                    await self._close_session(s, reason="idle-ttl")
        except asyncio.CancelledError:
            pass


def _quote_arg(a: str) -> str:
    """Minimal quoting for cmd-line args that may contain spaces."""
    if not a:
        return '""'
    if any(c in a for c in (" ", "\t", '"')):
        return '"' + a.replace('"', '\\"') + '"'
    return a


# Process-wide singleton; the FastAPI router creates it lazily.
_manager: PtyManager | None = None


def get_manager() -> PtyManager:
    global _manager
    if _manager is None:
        _manager = PtyManager()
    return _manager
