# [OMNI] origin=claude-code ts=2026-05-02 type=infra
# [OMNI] material_id="material:dashboard.cc_wrapper.hooks.compact_context_preserver.implementation.py"
"""PreCompact hook — runs immediately before Claude's auto / manual compaction.

Two responsibilities:
  1. Snapshot key state to disk so the human can recover even if compact loses things.
     File: docs/plans/<active_plan>/compact_snapshot_<ts>.json
  2. Output `additionalContext` so the *post-compact* turn still knows the active
     plan id, workspace cwd, and which files this session has touched.

We do NOT call an LLM here. Passive compact triggers when context is already full,
so anything heavy would crowd out the actual conversation. The structured snapshot
is enough for human + future-AI recovery.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import _shared as sh


def _gather_modified_files(session_id: str) -> list[str]:
    """Pull file paths from this session's recent Edit/Write trace events."""
    if not session_id:
        return []
    db = sh._events_db_path()
    if not db.is_file():
        return []
    try:
        import sqlite3
        conn = sqlite3.connect(str(db), timeout=2.0)
        try:
            rows = conn.execute(
                "SELECT data FROM events WHERE trace_id=? AND event_type='agent.tool.call' "
                "ORDER BY timestamp DESC LIMIT 200",
                (f"cc_{session_id}",),
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return []
    paths: list[str] = []
    seen = set()
    for (raw,) in rows:
        try:
            ev = json.loads(raw)
            p = ev.get("payload") or {}
            tool = p.get("tool", "")
            if tool not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                continue
            args = p.get("args") or {}
            fp = args.get("file_path") or args.get("notebook_path")
            if fp and fp not in seen:
                seen.add(fp)
                paths.append(fp)
                if len(paths) >= 30:
                    break
        except (json.JSONDecodeError, AttributeError):
            continue
    return paths


def main() -> int:
    payload = sh.read_stdin_json()
    cwd = payload.get("cwd") or os.getcwd()
    session_id = payload.get("session_id") or payload.get("sessionId") or ""
    trigger = (payload.get("trigger") or "auto").lower()  # 'manual' | 'auto'

    plan = sh.detect_active_plan(hint_cwd=cwd)
    plan_id = sh.plan_id_of(plan) if plan else None
    modified = _gather_modified_files(session_id)

    snapshot = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "trigger": trigger,
        "session_id": session_id,
        "cwd": cwd,
        "active_plan": plan_id,
        "modified_files": modified,
    }

    if plan and trigger in ("manual", "auto"):
        try:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            out = plan / f"compact_snapshot_{ts}.json"
            out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            print(f"[cc_wrapper] snapshot write failed: {e}", file=sys.stderr)

    # Emit a trace event so the dashboard sees the compact event in real time.
    sh.emit_event(
        trace_id=sh.trace_id_for(payload),
        event_type="agent.state.change",
        payload={"from_state": "active", "to_state": "compacting", **snapshot},
        tags=["cc_session", "compact"],
    )
    sh.append_audit("compact", snapshot)

    # additionalContext: keep critical refs alive across the compaction.
    parts = ["# omnicompany context (preserved across compact)"]
    if plan_id:
        parts.append(f"- active plan: `{plan_id}`")
    parts.append(f"- workspace cwd: `{cwd}`")
    if modified:
        parts.append("- files modified this session:")
        for p in modified[:20]:
            parts.append(f"  - `{p}`")
    if trigger == "manual":
        parts.append("\n_/compact was invoked manually. Consider running the 8-item "
                     "session-summary checklist (per `docs/standards/l2_session_summary_protocol.md`) "
                     "and writing `compact_summary_<date>.md` to the plan directory before returning to work._")
    else:
        parts.append("\n_(auto-compact: no checklist required; resume work)_")

    text = "\n".join(parts)
    out = {"hookSpecificOutput": {"hookEventName": "PreCompact", "additionalContext": text}}
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
