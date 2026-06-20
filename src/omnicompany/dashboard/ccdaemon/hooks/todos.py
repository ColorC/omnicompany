# [OMNI] origin=claude-code ts=2026-05-02 type=infra
# [OMNI] material_id="material:dashboard.cc_wrapper.hooks.plan_todo_bidirectional_sync.implementation.py"
"""Bidirectional sync between Claude's TodoWrite and the active plan.md checklist.

Triggered as a PostToolUse hook with two matchers:
  - `TodoWrite`        → claude updated todos → write back to plan.md
  - `Edit` / `Write`   → if the modified file is the active plan.md, parse its
                          checklist and emit additionalContext nudging claude to
                          sync via TodoWrite.

We never directly mutate Claude's TodoWrite state (impossible from a hook); we
just suggest. Plan.md *is* directly written (it's the canonical source).
"""

from __future__ import annotations

import json
import os
import sys

from . import _shared as sh


def _handle_todowrite(stdin: dict) -> int:
    tool_input = stdin.get("tool_input") or stdin.get("toolInput") or {}
    todos = tool_input.get("todos") or []
    cwd = stdin.get("cwd") or os.getcwd()
    session_id = stdin.get("session_id") or stdin.get("sessionId") or ""

    plan = sh.detect_active_plan(hint_cwd=cwd)
    if not plan:
        sh.append_audit("todos.todowrite.no_plan", {"todos": len(todos)})
        return 0

    plan_md = plan / "plan.md"
    if not plan_md.is_file():
        sh.append_audit("todos.todowrite.no_plan_md", {"plan": str(plan)})
        return 0

    try:
        before = plan_md.read_text(encoding="utf-8", errors="replace")
        after = sh.merge_todos_into_plan(before, todos)
        if after != before:
            plan_md.write_text(after, encoding="utf-8")
        sh.append_audit("todos.todowrite.synced", {
            "plan": str(plan_md), "todos": len(todos),
            "changed": after != before,
        })
    except OSError as e:
        print(f"[cc_wrapper] todo sync failed: {e}", file=sys.stderr)

    sh.emit_event(
        trace_id=sh.trace_id_for(stdin),
        event_type="agent.tool.result",
        payload={
            "tool": "TodoWrite", "node": "todo_sync",
            "verdict": "synced",
            "result": f"wrote {len(todos)} todos to {sh.plan_id_of(plan)}/plan.md",
        },
        tags=["cc_session", "todo_sync"],
    )
    return 0


def _handle_edit_or_write(stdin: dict) -> int:
    tool_input = stdin.get("tool_input") or stdin.get("toolInput") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not file_path:
        return 0
    cwd = stdin.get("cwd") or os.getcwd()
    plan = sh.detect_active_plan(hint_cwd=cwd)
    if not plan:
        return 0
    plan_md = plan / "plan.md"
    try:
        if not plan_md.is_file():
            return 0
        # only nudge when the edited file IS the active plan.md
        if os.path.normcase(os.path.realpath(file_path)) != os.path.normcase(os.path.realpath(str(plan_md))):
            return 0
    except OSError:
        return 0

    try:
        text = plan_md.read_text(encoding="utf-8", errors="replace")
        items = sh.parse_checklist(text)
    except OSError:
        return 0

    if not items:
        return 0
    lines = ["# plan.md was edited — please call TodoWrite to sync your todos:"]
    for it in items[:20]:
        box = "x" if it["done"] else " "
        lines.append(f"- [{box}] {it['text']}")
    text = "\n".join(lines)
    out = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sh.append_audit("todos.edit.nudge", {"plan_md": str(plan_md), "items": len(items)})
    return 0


def main() -> int:
    stdin = sh.read_stdin_json()
    tool_name = stdin.get("tool_name") or stdin.get("toolName") or ""
    if tool_name == "TodoWrite":
        return _handle_todowrite(stdin)
    if tool_name in ("Edit", "Write", "MultiEdit"):
        return _handle_edit_or_write(stdin)
    return 0


if __name__ == "__main__":
    sys.exit(main())
