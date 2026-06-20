# [OMNI] origin=claude-code ts=2026-05-02 type=infra
# [OMNI] material_id="material:dashboard.cc_wrapper.hooks.session_initializer.implementation.py"
"""SessionStart hook — fires once when a Claude Code session starts (or resumes).

Output: `additionalContext` JSON injecting plan + workspace + initial todos.
Side effect: emits `task.intent` event so the cc_session shows up in dashboard's
Trace list immediately on session start.

Stays small (≤ ~2KB injected) to not bloat first-turn context.
"""

from __future__ import annotations

import json
import os
import sys

# Windows: 默认 stdout encoding cp936 (GBK), plan.md 含 ↔ 等 unicode → encode fail.
# 强制 utf-8 输出 (跟 cli/main.py 同 pattern).
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from . import _shared as sh


def main() -> int:
    payload = sh.read_stdin_json()
    cwd = payload.get("cwd") or os.getcwd()
    session_id = payload.get("session_id") or payload.get("sessionId") or ""

    plan = sh.detect_active_plan(hint_cwd=cwd, claude_session_id=session_id or None)
    plan_id = sh.plan_id_of(plan) if plan else None

    plan_head = ""
    plan_meta: dict = {}
    todo_lines: list[dict] = []
    if plan:
        plan_md = plan / "plan.md"
        if plan_md.is_file():
            try:
                full = plan_md.read_text(encoding="utf-8", errors="replace")
                # head: first ~80 lines (or until next H2 — whichever shorter)
                lines = full.splitlines()
                head_cut = 80
                for i, ln in enumerate(lines[:200]):
                    if i > 5 and ln.startswith("## "):
                        head_cut = min(head_cut, i)
                        break
                plan_head = "\n".join(lines[:head_cut])
                todo_lines = sh.parse_checklist(full)
                # parse frontmatter (work_type / standards / project / exit_criteria)
                # — 真信息源, 注入文案带上让 agent 不用再读 plan.md 也知道边界
                try:
                    from omnicompany.dashboard.controlplane.plans import parse_plan_frontmatter
                    plan_meta = parse_plan_frontmatter(plan_md) or {}
                except Exception:
                    plan_meta = {}
            except OSError:
                pass

    parts = []
    if plan_id:
        parts.append(f"# omnicompany context\n\nactive plan: `{plan_id}`")
        parts.append(f"workspace cwd: `{cwd}`")
        # plan_meta 真信息源摘要 (不重读 plan.md 也能定位边界)
        if plan_meta:
            meta_lines = ["\n## plan meta (frontmatter)\n"]
            for k in ("work_type", "project", "status", "phase", "expected_completion"):
                v = plan_meta.get(k)
                if v:
                    meta_lines.append(f"- **{k}**: {v}")
            standards = plan_meta.get("standards") or []
            if standards:
                meta_lines.append(f"- **standards**: {', '.join(standards)}")
            exit_criteria = plan_meta.get("exit_criteria") or []
            if exit_criteria:
                meta_lines.append("- **exit_criteria**:")
                for ec in exit_criteria:
                    meta_lines.append(f"  - {ec}")
            if len(meta_lines) > 1:
                parts.append("\n".join(meta_lines))
        if plan_head:
            parts.append(f"\n## plan.md (head)\n\n{plan_head}")
        if todo_lines:
            parts.append("\n## existing checklist (from plan.md, sync via TodoWrite to make these your todos)\n")
            for t in todo_lines[:30]:  # cap to keep context tight
                box = "x" if t["done"] else " "
                parts.append(f"- [{box}] {t['text']}")
        parts.append(
            "\n_Switch plan: `omni plan use <id>` (CLI) 或 web SessionContextPanel "
            "右上 '切 plan' 按钮. 列出所有可选: `omni plan list`._"
        )
        parts.append(
            "_Tip: use the `omni_*` MCP tools to query workers / teams / materials / "
            "traces / notes / other plans on demand. Don't dump them upfront._"
        )
    else:
        parts.append(
            "# omnicompany context\n\n"
            f"workspace cwd: `{cwd}`\n\n"
            "No active plan is bound to this session.\n"
            "Pick one explicitly:\n"
            "- CLI: `omni plan list` to browse, then `omni plan use <id>` to bind\n"
            "- Web: open the dashboard cc_session panel and click the plan picker\n"
            "Working without a plan is fine for ad-hoc exploration, but durable work "
            "should be anchored to a plan so the workspace, applicable standards, "
            "and exit criteria are explicit."
        )

    text = "\n".join(parts)

    # Audit so we can see what we injected (for debugging via tail data/cc_hooks_audit.jsonl)
    sh.append_audit("session_start", {
        "session_id": session_id, "cwd": cwd, "plan_id": plan_id,
        "todos": len(todo_lines), "context_chars": len(text),
    })

    # Mirror to event bus so the session appears as a trace immediately.
    sh.emit_event(
        trace_id=sh.trace_id_for(payload),
        event_type="task.intent",
        payload={
            "claude_session_id": session_id,
            "cwd": cwd,
            "active_plan": plan_id,
            "instruction": f"claude code session started (plan={plan_id or 'none'})",
        },
        tags=["cc_session"],
    )

    # If we know our PTY id (set by PtyManager via OMNI_CC_PTY_ID env), write
    # claude_session_id + active_plan back into cc_sessions.json so the dashboard
    # can correlate + offer resume after a backend restart.
    pty_id = os.environ.get("OMNI_CC_PTY_ID")
    if pty_id and session_id:
        try:
            from omnicompany.dashboard.ccdaemon.pty import update_meta_field
            update_meta_field(pty_id, claude_session_id=session_id, active_plan=plan_id)
        except Exception as e:
            print(f"[ccdaemon] meta link failed: {e}", file=sys.stderr)

    # Record active session to cc_session_active.json so CLI / non-hook callers can
    # resolve the same trace_id (shared identity across hook + CLI + web — all three
    # go through omnicompany.packages.services._core.identity.record_active_session).
    try:
        from omnicompany.packages.services._core.identity import record_active_session
        record_active_session(
            trace_id=sh.trace_id_for(payload),
            claude_session_id=session_id or None,
            pty_id=pty_id,
            active_plan=plan_id,
            cwd=cwd,
            source="hook",
        )
    except Exception as e:
        print(f"[cc_wrapper] record_active_session failed: {e}", file=sys.stderr)

    # Write the additionalContext envelope to stdout for Claude to consume.
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
