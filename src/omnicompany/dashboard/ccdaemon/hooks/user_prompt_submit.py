# [OMNI] origin=ai-ide domain=dashboard/cc_wrapper/hooks ts=2026-05-04T00:00:00Z type=hook status=active
# [OMNI] summary="UserPromptSubmit hook — alive cc_session 切 plan 后下一条 turn 重注入 plan_meta"
# [OMNI] why="alive 进程 SessionStart 已跑过, 系统提示词缓存固定. 用 UserPromptSubmit additionalContext 不破缓存, 下一条用户输入触发即生效, 实现 b 方案"
# [OMNI] tags=cc-wrapper,hook,plan-binding,reinject
# [OMNI] material_id="material:dashboard.cc_wrapper.hooks.user_prompt_submit_plan_reinject.implementation.py"
"""UserPromptSubmit hook — re-inject plan_meta into the next turn after a plan switch.

Triggered before each user prompt is sent to the LLM. Compares
`active_plan_changed_ts` vs `last_plan_inject_ts` in `cc_sessions.json[pty_id]`;
if a switch happened since last injection, emit `additionalContext` with the
new plan's frontmatter summary, then advance the marker so we don't re-inject
on subsequent turns.

This is alive-session re-injection (option b in CC-PLAN-SESSION-CONTEXT 段二
审议). 不破系统提示词缓存 (additionalContext 是 per-turn 注入, 不进 system),
也不需要用户主动 /clear.

No-op when:
  - OMNI_CC_PTY_ID not set (claude not spawned via dashboard wrapper)
  - cc_sessions.json missing or pty_id absent
  - active_plan_changed_ts <= last_plan_inject_ts (already injected or never switched)
"""
from __future__ import annotations

import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from . import _shared as sh


def _build_plan_summary(plan_id: str, plan_meta: dict) -> str:
    """Compact additionalContext text for a plan switch."""
    lines = [
        "# omnicompany context (plan switched)",
        "",
        f"active plan: `{plan_id}`",
    ]
    if plan_meta:
        lines.append("")
        for k in ("work_type", "project", "status", "phase", "expected_completion"):
            v = plan_meta.get(k)
            if v:
                lines.append(f"- **{k}**: {v}")
        standards = plan_meta.get("standards") or []
        if standards:
            lines.append(f"- **standards**: {', '.join(standards)}")
        exit_criteria = plan_meta.get("exit_criteria") or []
        if exit_criteria:
            lines.append("- **exit_criteria**:")
            for ec in exit_criteria:
                lines.append(f"  - {ec}")
        title = plan_meta.get("title")
        if title:
            lines.insert(3, f"title: {title}")
    lines.append("")
    lines.append(
        "_Plan was switched mid-session. Use `omni plan show <id>` for full frontmatter "
        "or open `docs/plans/<id>/plan.md` for the prose._"
    )
    return "\n".join(lines)


def main() -> int:
    payload = sh.read_stdin_json()
    pty_id = os.environ.get("OMNI_CC_PTY_ID")
    if not pty_id:
        return 0  # not spawned through dashboard wrapper — nothing to re-inject

    root = sh.repo_root()
    store_path = root / "data" / "cc_sessions.json"
    if not store_path.is_file():
        return 0
    try:
        store = json.loads(store_path.read_text(encoding="utf-8") or "{}") or {}
    except (json.JSONDecodeError, OSError):
        return 0
    entry = store.get(pty_id) or {}
    changed_ts = entry.get("active_plan_changed_ts") or 0
    last_inject_ts = entry.get("last_plan_inject_ts") or 0
    plan_id = entry.get("active_plan")
    if not changed_ts or not plan_id or changed_ts <= last_inject_ts:
        return 0  # no switch since last injection

    # parse plan.md frontmatter for the new plan
    plan_md = root / "docs" / "plans" / plan_id / "plan.md"
    plan_meta: dict = {}
    if plan_md.is_file():
        try:
            from omnicompany.dashboard.controlplane.plans import parse_plan_frontmatter
            plan_meta = parse_plan_frontmatter(plan_md) or {}
        except Exception:
            plan_meta = {}

    text = _build_plan_summary(plan_id, plan_meta)

    # advance marker (atomic-ish — write+replace)
    entry["last_plan_inject_ts"] = changed_ts
    store[pty_id] = entry
    try:
        tmp = store_path.with_suffix(store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, store_path)
    except OSError as e:
        print(f"[cc_wrapper] last_plan_inject_ts write failed: {e}", file=sys.stderr)

    sh.append_audit("user_prompt_submit_plan_reinject", {
        "pty_id": pty_id,
        "plan_id": plan_id,
        "changed_ts": changed_ts,
        "context_chars": len(text),
    })

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": text,
        }
    }
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
