# [OMNI] origin=claude-code ts=2026-05-02 type=infra
# [OMNI] material_id="material:dashboard.cc_wrapper.hooks.shared_utilities.event_emitter.py"
"""Shared utilities for Claude Code hook scripts.

Hook scripts are short-lived (spawned once per event) and must:
  - read JSON from stdin
  - write JSON or text to stdout
  - exit 0 / 1 / 2 to signal allow / ask / block (or just 0 for non-permission events)

We keep this module tiny and dependency-free (sqlite3 + stdlib only) so hook
startup is sub-100ms.

Reference:  https://code.claude.com/docs/en/hooks-guide.md
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── stdin / stdout protocol ──────────────────────────────────────────────────


def read_stdin_json() -> dict[str, Any]:
    """Hooks always receive one JSON document on stdin (potentially with trailing newline)."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return {}


def emit_additional_context(text: str) -> None:
    """Print a JSON envelope that Claude Code interprets as 'add this to the next turn's context'.

    Per hooks guide, this is the supported way to influence the upcoming LLM call
    without rewriting the user's prompt or system prompt (so prompt caching is preserved).
    """
    payload = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                       "additionalContext": text}}
    # The runtime accepts either generic `additionalContext` or event-scoped variant.
    # The simpler top-level `additionalContext` works for any pre-LLM hook.
    try:
        json.dump({"additionalContext": text}, sys.stdout)
        sys.stdout.write("\n")
    except OSError:
        pass


def emit_decision(allow: bool, reason: str = "") -> None:
    """Permission decision for PreToolUse hooks. exit code carries the meaning."""
    if reason:
        try:
            print(reason, file=sys.stderr)
        except OSError:
            pass
    sys.exit(0 if allow else 2)


# ─── repo / plan discovery ────────────────────────────────────────────────────


def repo_root() -> Path:
    """Return the omnicompany workspace root."""
    try:
        from omnicompany.core.config import omni_workspace_root
        return omni_workspace_root()
    except Exception:
        here = Path.cwd().resolve()
        for d in (here, *here.parents):
            if (d / "src" / "omnicompany").is_dir() and (d / "docs").is_dir():
                return d
        return Path(__file__).resolve().parents[5]


PLAN_DIR_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2})\](.+)$")


def _read_cc_sessions_store(root: Path) -> dict[str, dict[str, Any]]:
    """Read data/cc_sessions.json without importing pty_service (avoid circular).

    Schema mirrors pty_service._meta_store_path():
      { "<pty_id>": { claude_session_id, active_plan, started_at, ended_at, ... } }
    """
    p = root / "data" / "cc_sessions.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8") or "{}") or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _historical_plan_for_claude_session(root: Path, claude_session_id: str) -> str | None:
    """If a previous PtySession with the same claude_session_id had active_plan, return it.

    Scenario: user closes browser tab → PTY reaps → user picks "resume" in dashboard
    → new PTY id but same claude_session_id (claude --resume). Without this, the new
    SessionStart hook would re-run mtime fallback and lose the prior plan binding.

    Returns plan_id (relative to docs/plans/) or None.
    """
    if not claude_session_id:
        return None
    store = _read_cc_sessions_store(root)
    matches: list[tuple[float, str]] = []
    for entry in store.values():
        if entry.get("claude_session_id") != claude_session_id:
            continue
        plan = entry.get("active_plan")
        if not plan:
            continue
        # prefer most recent (use ended_at, fall back to started_at)
        ts = entry.get("ended_at") or entry.get("started_at") or 0
        try:
            ts_f = float(ts)
        except (TypeError, ValueError):
            ts_f = 0.0
        matches.append((ts_f, plan))
    if not matches:
        return None
    matches.sort(reverse=True)
    return matches[0][1]


def detect_active_plan(
    root: Path | None = None,
    hint_cwd: str | None = None,
    claude_session_id: str | None = None,
) -> Path | None:
    """Which plan dir is the user currently bound to? Empty is a valid answer.

    Strategy (high → low priority):
      1. **Historical binding**: if claude_session_id matches a prior cc_sessions.json
         entry with active_plan set, use that (covers `claude --resume`).
      2. **cwd-based**: if hint_cwd is inside a [date]NAME plan dir, use that.
      3. **None**: no signal, no guess. Hook should prompt the user to pick one
         explicitly via `omni plan use <id>` rather than silently grabbing whatever
         plan was last touched (mtime fallback was deliberately removed because the
         "last modified" plan is often not the plan the user is working on).
    """
    root = root or repo_root()
    plans = root / "docs" / "plans"
    if not plans.is_dir():
        return None

    # 1. historical binding via claude_session_id
    if claude_session_id:
        plan_id = _historical_plan_for_claude_session(root, claude_session_id)
        if plan_id:
            candidate = plans / plan_id
            if candidate.is_dir():
                return candidate

    # 2. cwd-based
    cwd_check = Path(hint_cwd or os.getcwd()).resolve()
    cur = cwd_check
    for _ in range(8):
        if PLAN_DIR_RE.match(cur.name):
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent

    # 3. no signal → no plan. Don't guess.
    return None


def plan_id_of(plan_dir: Path) -> str:
    """Convert plan dir absolute path → catalogue id (e.g. `_infra/[2026-05-01]WEB-FOUNDATION`)."""
    plans = repo_root() / "docs" / "plans"
    try:
        rel = plan_dir.resolve().relative_to(plans.resolve())
        return str(rel).replace(os.sep, "/")
    except ValueError:
        return plan_dir.name


# ─── event bus (synchronous SQLite write) ────────────────────────────────────


def _events_db_path() -> Path:
    state_dir = os.environ.get("OMNI_CC_DAEMON_STATE_DIR")
    if state_dir:
        return Path(state_dir) / "ide_events.db"
    try:
        from omnicompany.core.config import resolve_unified_db_path
        return resolve_unified_db_path("ide_events.db")
    except Exception:
        pass
    return repo_root() / "data" / "ide_events.db"


def trace_id_for(stdin_payload: dict) -> str:
    """Pick the right trace_id for hook-emitted events.

    Prefer `OMNI_CC_PTY_ID` env (set by our PtyManager) so dashboard cc_session
    entities can find their own trace events. Fall back to claude's session_id
    if we weren't spawned through the wrapper (e.g. user runs `claude` directly
    from a terminal — events still land but won't be visible in the cc_session
    panel).
    """
    pty_id = os.environ.get("OMNI_CC_PTY_ID")
    if pty_id:
        return pty_id  # cc_session.id matches directly
    sid = stdin_payload.get("session_id") or stdin_payload.get("sessionId") or "unknown"
    return f"cc_{sid}"


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS events (
        id          TEXT PRIMARY KEY,
        trace_id    TEXT NOT NULL,
        parent_id   TEXT,
        event_type  TEXT NOT NULL,
        source      TEXT NOT NULL,
        tags        TEXT NOT NULL DEFAULT '[]',
        timestamp   TEXT NOT NULL,
        data        TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_events_trace ON events (trace_id, timestamp);
    """)


def emit_event(
    trace_id: str,
    event_type: str,
    payload: dict[str, Any],
    *,
    parent_id: str | None = None,
    source: str = "claude-code",
    tags: list[str] | None = None,
) -> str:
    """Write one event synchronously. Returns the new event id."""
    eid = uuid.uuid4().hex
    ts = datetime.now(timezone.utc).isoformat()
    db_path = _events_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "id": eid,
        "trace_id": trace_id,
        "parent_id": parent_id,
        "event_type": event_type,
        "source": source,
        "tags": tags or [],
        "timestamp": ts,
        "payload": payload,
    }
    try:
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        try:
            _ensure_schema(conn)
            conn.execute(
                "INSERT INTO events (id, trace_id, parent_id, event_type, source, tags, timestamp, data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (eid, trace_id, parent_id, event_type, source,
                 json.dumps(tags or []), ts, json.dumps(body, ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as e:
        # never break the hook on a logging failure
        try:
            print(f"[cc_wrapper] event emit failed: {e}", file=sys.stderr)
        except OSError:
            pass
    return eid


# ─── plan.md checklist parsing & writing ─────────────────────────────────────

CHECK_RE = re.compile(r"^(\s*)- \[([ xX])\]\s+(.+?)\s*$")


def parse_checklist(md_text: str) -> list[dict[str, Any]]:
    """Pull `- [ ]` / `- [x]` items from anywhere in the doc.

    Returns: [{indent, done, text, lineno}] preserving order.
    """
    items: list[dict[str, Any]] = []
    for i, line in enumerate(md_text.splitlines(), 1):
        m = CHECK_RE.match(line)
        if not m:
            continue
        items.append({
            "indent": len(m.group(1)),
            "done": m.group(2).lower() == "x",
            "text": m.group(3).rstrip(),
            "lineno": i,
        })
    return items


def merge_todos_into_plan(md_text: str, todos: list[dict[str, Any]]) -> str:
    """Update existing `- [ ]` / `- [x]` lines in plan.md to match `todos[].status`.

    Match by text equality (whitespace-trimmed). Items in `todos` not present in the
    plan are appended to a `## Todos` section (created if missing).
    """
    lines = md_text.splitlines(keepends=True)
    todo_by_text: dict[str, dict[str, Any]] = {}
    for t in todos:
        key = (t.get("content") or t.get("activeForm") or "").strip()
        if key:
            todo_by_text[key.lower()] = t

    matched: set[str] = set()
    for i, line in enumerate(lines):
        m = CHECK_RE.match(line.rstrip("\n"))
        if not m:
            continue
        text = m.group(3).strip()
        key = text.lower()
        if key in todo_by_text:
            t = todo_by_text[key]
            done = (t.get("status") or "").lower() == "completed"
            new_box = "x" if done else " "
            lines[i] = re.sub(r"\[[ xX]\]", f"[{new_box}]", line, count=1)
            matched.add(key)

    new_items = [t for k, t in todo_by_text.items() if k not in matched]
    if new_items:
        out = "".join(lines)
        if "## Todos" not in out:
            if not out.endswith("\n"):
                out += "\n"
            out += "\n## Todos\n\n"
        elif not out.endswith("\n"):
            out += "\n"
        for t in new_items:
            done = (t.get("status") or "").lower() == "completed"
            box = "x" if done else " "
            text = (t.get("content") or t.get("activeForm") or "").strip()
            out += f"- [{box}] {text}\n"
        return out
    return "".join(lines)


# ─── audit / debug helper ────────────────────────────────────────────────────


def append_audit(scope: str, payload: dict[str, Any]) -> None:
    """Append one JSONL line to `data/cc_hooks_audit.jsonl` for debugging hooks
    that produced no observable effect. Bounded by file size — caller's burden."""
    p = repo_root() / "data" / "cc_hooks_audit.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": time.time(), "scope": scope, "payload": payload}
    try:
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass
