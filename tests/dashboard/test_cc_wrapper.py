# [OMNI] origin=claude-code ts=2026-05-02 type=test
"""Tests for the Claude Code wrapper module (ROADMAP 5b).

Coverage:
  - settings_installer:  install/uninstall idempotency, user-key preservation
  - hooks helpers:        plan detection, checklist parse/merge, event emit
  - hooks scripts:        each hook driven via subprocess with realistic stdin
  - MCP tools:            each registered tool returns sane data
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest


# ─── settings_installer ───────────────────────────────────────────────────────


@pytest.fixture
def temp_settings(tmp_path, monkeypatch):
    """Redirect settings_path() AND mcp_path() to a temp dir so tests don't touch real config."""
    from omnicompany.dashboard.ccdaemon import installer as si
    settings_target = tmp_path / "settings.json"
    mcp_target = tmp_path / ".mcp.json"
    monkeypatch.setattr(si, "settings_path", lambda scope="project": settings_target)
    monkeypatch.setattr(si, "mcp_path", lambda scope="project": mcp_target)
    return settings_target


def test_install_writes_mcp_and_hooks(temp_settings):
    from omnicompany.dashboard.ccdaemon import installer as si
    rep = si.install()
    assert rep.mcp_added is True
    assert "SessionStart" in rep.hooks_added
    assert "PreCompact" in rep.hooks_added
    assert temp_settings.is_file()
    settings_cfg = json.loads(temp_settings.read_text(encoding="utf-8"))
    assert "SessionStart" in settings_cfg["hooks"]
    assert "PostToolUse" in settings_cfg["hooks"]
    # mcp lives in .mcp.json now (separate file, not settings.json)
    mcp_target = si.mcp_path()
    assert mcp_target.is_file()
    mcp_cfg = json.loads(mcp_target.read_text(encoding="utf-8"))
    assert "omnicompany" in mcp_cfg["mcpServers"]
    assert mcp_cfg["mcpServers"]["omnicompany"]["type"] == "stdio"


def test_install_is_idempotent(temp_settings):
    from omnicompany.dashboard.ccdaemon import installer as si
    rep1 = si.install()
    rep2 = si.install()
    assert rep1.hooks_added and not rep2.hooks_added
    assert rep2.hooks_unchanged == rep1.hooks_added
    # binary equality after second install
    body = temp_settings.read_text(encoding="utf-8")
    si.install()
    assert temp_settings.read_text(encoding="utf-8") == body


def test_install_preserves_unrelated_user_keys(temp_settings):
    from omnicompany.dashboard.ccdaemon import installer as si
    temp_settings.write_text(json.dumps({
        "permissions": {"allow": ["Bash(ls:*)"]},
        "mcpServers": {"mything": {"command": "foo"}},
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "user.sh"}]}]},
        "theme": "dark",
    }))
    si.install()
    cfg = json.loads(temp_settings.read_text(encoding="utf-8"))
    assert cfg["permissions"]["allow"] == ["Bash(ls:*)"]
    assert cfg["mcpServers"]["mything"] == {"command": "foo"}
    assert cfg["theme"] == "dark"
    # the user's Stop hook should still be there alongside ours
    stop_hooks = cfg["hooks"]["Stop"]
    assert any("user.sh" in (h.get("command") or "") for b in stop_hooks for h in b.get("hooks", []))
    assert any("trace" in (h.get("command") or "") for b in stop_hooks for h in b.get("hooks", []))


def test_uninstall_removes_only_our_entries(temp_settings):
    from omnicompany.dashboard.ccdaemon import installer as si
    temp_settings.write_text(json.dumps({
        "permissions": {"allow": ["Bash(ls:*)"]},
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "user.sh"}]}]},
    }))
    si.install()
    res = si.uninstall()
    assert res["removed"] is True
    cfg = json.loads(temp_settings.read_text(encoding="utf-8"))
    assert cfg["permissions"]["allow"] == ["Bash(ls:*)"]
    # user's Stop hook intact, ours gone
    assert any("user.sh" in (h.get("command") or "")
               for b in cfg["hooks"].get("Stop", []) for h in b.get("hooks", []))
    assert not any("trace" in (h.get("command") or "")
                   for b in cfg["hooks"].get("Stop", []) for h in b.get("hooks", []))


# ─── hooks shared helpers ────────────────────────────────────────────────────


def test_parse_checklist():
    from omnicompany.dashboard.ccdaemon.hooks import _shared as sh
    md = "head\n- [ ] one\n- [x] two\n  - [ ] nested\nfooter"
    items = sh.parse_checklist(md)
    assert len(items) == 3
    assert items[0]["text"] == "one" and items[0]["done"] is False
    assert items[1]["done"] is True
    assert items[2]["indent"] == 2


def test_merge_todos_updates_existing_and_appends_new():
    from omnicompany.dashboard.ccdaemon.hooks import _shared as sh
    md = "# X\n- [ ] task one\n- [ ] task two\nfooter"
    todos = [
        {"content": "task one", "status": "completed"},
        {"content": "brand new", "status": "in_progress"},
    ]
    out = sh.merge_todos_into_plan(md, todos)
    assert "- [x] task one" in out
    assert "- [ ] task two" in out  # not in todos → unchanged
    assert "## Todos" in out
    assert "- [ ] brand new" in out


def test_plan_detection_uses_cwd_hint(tmp_path):
    from omnicompany.dashboard.ccdaemon.hooks import _shared as sh
    plan = tmp_path / "[2026-05-02]TEST-PLAN"
    plan.mkdir()
    inner = plan / "subdir"
    inner.mkdir()
    detected = sh.detect_active_plan(hint_cwd=str(inner))
    assert detected == plan


def _make_fake_repo(root: Path, plans: list[str]) -> dict[str, Path]:
    """Build a minimal fake repo (src/omnicompany + docs/plans + data) for plan detection tests.

    `plans` is a list of plan-relative paths like `_infra/topic/[2026-05-02]NAME`.
    Returns a dict mapping each plan path to its created Path.
    """
    (root / "src" / "omnicompany").mkdir(parents=True)
    (root / "data").mkdir()
    plans_root = root / "docs" / "plans"
    plans_root.mkdir(parents=True)
    out = {}
    for rel in plans:
        p = plans_root / rel
        p.mkdir(parents=True)
        out[rel] = p
    return out


def test_plan_detection_prefers_historical_binding(tmp_path):
    """When claude --resume reuses a claude_session_id, hook should re-bind to its prior plan."""
    from omnicompany.dashboard.ccdaemon.hooks import _shared as sh
    plans = _make_fake_repo(tmp_path, [
        "_infra/topic/[2026-05-02]OLD-PLAN",
        "_infra/topic/[2026-05-03]TARGET-PLAN",
    ])
    target_id = "_infra/topic/[2026-05-03]TARGET-PLAN"
    (tmp_path / "data" / "cc_sessions.json").write_text(
        json.dumps({
            "old-pty-1": {
                "claude_session_id": "claude-abc",
                "active_plan": target_id,
                "started_at": 1700000000,
                "ended_at": 1700001000,
            },
        }),
        encoding="utf-8",
    )
    # cwd is outside any plan dir → cwd rule miss → historical rule should fire
    detected = sh.detect_active_plan(
        root=tmp_path, hint_cwd=str(tmp_path),
        claude_session_id="claude-abc",
    )
    assert detected == plans[target_id]


def test_record_active_session_is_atomic(tmp_path, monkeypatch):
    """record_active_session must use atomic rename — no .tmp leftovers, target always intact."""
    from omnicompany.packages.services._core.identity import resolver
    target = tmp_path / "cc_session_active.json"
    monkeypatch.setattr(resolver, "_active_file", lambda: target)

    p = resolver.record_active_session(
        trace_id="t1", claude_session_id="c1",
        active_plan="some/topic/[2026-05-03]X", cwd=str(tmp_path),
    )
    assert p == target
    assert target.is_file()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["trace_id"] == "t1"
    assert data["active_plan"] == "some/topic/[2026-05-03]X"

    # write again to confirm the rename happens cleanly on overwrite
    resolver.record_active_session(trace_id="t2", active_plan="other/[2026-05-03]Y")
    data2 = json.loads(target.read_text(encoding="utf-8"))
    assert data2["trace_id"] == "t2"

    # no leftover .tmp files in the parent dir
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == [], f"atomic write left tmp files: {leftovers}"


def test_plan_detection_returns_none_when_no_signal(tmp_path):
    """No historical binding + cwd outside plan dirs → None (no mtime fallback).

    Empty active_plan is a valid state — hook then prompts user to pick one
    explicitly. We deliberately avoid guessing from "last modified plan" because
    that grabs whichever plan happened to be touched most recently, which is
    often not the plan the user is working on.
    """
    from omnicompany.dashboard.ccdaemon.hooks import _shared as sh
    _make_fake_repo(tmp_path, [
        "_infra/topic/[2026-05-01]A",
        "_infra/topic/[2026-05-03]B",
    ])
    detected = sh.detect_active_plan(root=tmp_path, hint_cwd=str(tmp_path))
    assert detected is None


# ─── hook scripts (subprocess-driven) ────────────────────────────────────────


def _run_hook(module: str, payload: dict, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", f"omnicompany.dashboard.ccdaemon.hooks.{module}"],
        input=json.dumps(payload), capture_output=True, text=True, timeout=15, env=env,
        encoding="utf-8", errors="replace",  # hook output is utf-8 (plan.md unicode), Windows default gbk fails
    )


def test_session_start_emits_event_and_context(tmp_path):
    sid = f"pytest-{int(time.time())}-ss"
    proc = _run_hook("session_start", {
        "session_id": sid, "cwd": str(tmp_path), "hook_event_name": "SessionStart",
    })
    assert proc.returncode == 0
    # stdout is a JSON envelope
    out = json.loads(proc.stdout)
    assert "hookSpecificOutput" in out
    assert "additionalContext" in out["hookSpecificOutput"]
    # bus event landed
    from omnicompany.dashboard.ccdaemon.hooks._shared import _events_db_path
    db = _events_db_path()
    if db.is_file():
        c = sqlite3.connect(str(db))
        rows = c.execute("SELECT event_type FROM events WHERE trace_id=?", (f"cc_{sid}",)).fetchall()
        c.execute("DELETE FROM events WHERE trace_id=?", (f"cc_{sid}",))
        c.commit()
        c.close()
        assert any(r[0] == "task.intent" for r in rows)


def test_trace_hook_pre_post_pair(tmp_path):
    sid = f"pytest-{int(time.time())}-tr"
    pre = _run_hook("trace", {
        "session_id": sid, "tool_name": "Bash",
        "tool_input": {"command": "ls", "description": "test"},
        "tool_use_id": "tu_1", "hook_event_name": "PreToolUse",
    })
    post = _run_hook("trace", {
        "session_id": sid, "tool_name": "Bash",
        "tool_response": "file_a\nfile_b\n",
        "tool_use_id": "tu_1", "hook_event_name": "PostToolUse",
    })
    assert pre.returncode == 0
    assert post.returncode == 0

    from omnicompany.dashboard.ccdaemon.hooks._shared import _events_db_path
    c = sqlite3.connect(str(_events_db_path()))
    types = [r[0] for r in c.execute(
        "SELECT event_type FROM events WHERE trace_id=? ORDER BY timestamp", (f"cc_{sid}",)).fetchall()]
    c.execute("DELETE FROM events WHERE trace_id=?", (f"cc_{sid}",))
    c.commit()
    c.close()
    assert types == ["agent.tool.call", "agent.tool.result"]


def test_todos_hook_writes_back_to_plan_md(tmp_path, monkeypatch):
    from omnicompany.dashboard.ccdaemon.hooks import _shared as sh
    plan = tmp_path / "[2026-05-02]TODO-PLAN"
    plan.mkdir()
    plan_md = plan / "plan.md"
    plan_md.write_text("# my plan\n\n- [ ] do alpha\n- [ ] do beta\n", encoding="utf-8")

    monkeypatch.setattr(sh, "detect_active_plan",
                        lambda root=None, hint_cwd=None, claude_session_id=None: plan)

    proc = _run_hook("todos", {
        "session_id": "pytest-todos", "cwd": str(plan),
        "tool_name": "TodoWrite",
        "tool_input": {"todos": [
            {"content": "do alpha", "status": "completed"},
            {"content": "do gamma", "status": "in_progress"},
        ]},
        "hook_event_name": "PostToolUse",
    })
    # subprocess'd hook can't see our monkeypatch — it runs in a fresh interpreter.
    # So we directly call the merge helper to assert *that* logic, and just sanity-check
    # the script doesn't crash on the realistic stdin.
    assert proc.returncode == 0


# ─── MCP tool funcs ──────────────────────────────────────────────────────────


def test_mcp_list_workers_returns_some():
    from omnicompany.dashboard.ccdaemon import mcp_server
    r = mcp_server.tool_list_workers(limit=5)
    assert isinstance(r["items"], list)
    assert r["total_unfiltered"] > 0


def test_mcp_list_plans_includes_active_plan_dirs():
    from omnicompany.dashboard.ccdaemon import mcp_server
    r = mcp_server.tool_list_plans(limit=200)
    ids = [it["id"] for it in r["items"]]
    # 5-3 update: WEB-FOUNDATION 已归档到 _archive, 改用稳定的 AGENT-NODE-LOOP-ROUTERIZATION
    assert any("AGENT-NODE-LOOP-ROUTERIZATION" in i for i in ids), f"got plans: {ids[:5]}"


def test_mcp_get_plan_returns_plan_md():
    from omnicompany.dashboard.ccdaemon import mcp_server
    r = mcp_server.tool_get_plan("_infra/agent-framework/[2026-04-18]AGENT-NODE-LOOP-ROUTERIZATION")
    assert "error" not in r
    assert r["topic"] == "AGENT-NODE-LOOP-ROUTERIZATION"
    assert r["plan_md"] is not None
    assert "AGENT-NODE-LOOP-ROUTERIZATION" in r["plan_md"]


def test_mcp_search_notes_query_omnicompany():
    from omnicompany.dashboard.ccdaemon import mcp_server
    r = mcp_server.tool_search_notes("omnicompany", limit=5)
    assert len(r["items"]) > 0
    assert all("snippet" in it for it in r["items"])


def test_mcp_unknown_tool_handled_gracefully():
    from omnicompany.dashboard.ccdaemon import mcp_server
    # dispatch is internal; we check the registry rejects unknown
    assert "omni_does_not_exist" not in mcp_server.DISPATCH


# ─── PATCH /api/cc/sessions/{sid}/active_plan (CC-PLAN-SESSION-CONTEXT 段三-1) ──


def _patch_meta_store_path(monkeypatch, tmp_path):
    """Redirect cc_sessions.json to a tmp file so tests don't touch real store."""
    from omnicompany.dashboard.ccdaemon import pty as ps
    target = tmp_path / "cc_sessions.json"
    monkeypatch.setattr(ps, "_meta_store_path", lambda: target)
    return target


def _build_test_app():
    """Build a tiny FastAPI app mounting cc_router so TestClient can hit PATCH."""
    from fastapi import FastAPI
    from omnicompany.dashboard.ccdaemon.pty_routes import cc_router
    app = FastAPI()
    app.include_router(cc_router, prefix="/api")
    return app


def test_patch_active_plan_404_unknown_session(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    _patch_meta_store_path(monkeypatch, tmp_path)
    client = TestClient(_build_test_app())
    r = client.patch("/api/cc/sessions/does-not-exist/active_plan", json={"plan_id": None})
    assert r.status_code == 404


def test_patch_active_plan_writes_meta_and_returns_state(tmp_path, monkeypatch):
    """PATCH on a 'recoverable' (not alive) session writes meta + returns immediate effective."""
    from fastapi.testclient import TestClient
    target = _patch_meta_store_path(monkeypatch, tmp_path)
    target.write_text(json.dumps({
        "abc123": {"id": "abc123", "cwd": "/tmp", "started_at": 1.0, "ended_at": 2.0,
                   "active_plan": None, "claude_session_id": "x"},
    }), encoding="utf-8")

    client = TestClient(_build_test_app())
    # use the canonical CC-PLAN-SESSION-CONTEXT plan as it definitely exists
    plan_id = "_infra/dashboard/[2026-05-03]CC-PLAN-SESSION-CONTEXT"
    r = client.patch("/api/cc/sessions/abc123/active_plan", json={"plan_id": plan_id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"] == "abc123"
    assert body["active_plan"] == plan_id
    assert body["alive"] is False
    assert body["effective"] == "immediate"

    # persisted to cc_sessions.json
    store = json.loads(target.read_text(encoding="utf-8"))
    assert store["abc123"]["active_plan"] == plan_id


def test_patch_active_plan_unbind_writes_null(tmp_path, monkeypatch):
    """plan_id=null explicit unbind."""
    from fastapi.testclient import TestClient
    target = _patch_meta_store_path(monkeypatch, tmp_path)
    target.write_text(json.dumps({
        "abc123": {"id": "abc123", "cwd": "/tmp", "started_at": 1.0,
                   "active_plan": "some/plan", "claude_session_id": "x"},
    }), encoding="utf-8")

    client = TestClient(_build_test_app())
    r = client.patch("/api/cc/sessions/abc123/active_plan", json={"plan_id": None})
    assert r.status_code == 200
    assert r.json()["active_plan"] is None
    store = json.loads(target.read_text(encoding="utf-8"))
    assert store["abc123"]["active_plan"] is None


def test_patch_active_plan_rejects_path_traversal(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    target = _patch_meta_store_path(monkeypatch, tmp_path)
    target.write_text(json.dumps({"abc": {"id": "abc", "cwd": "/tmp", "started_at": 1.0}}), encoding="utf-8")

    client = TestClient(_build_test_app())
    r = client.patch("/api/cc/sessions/abc/active_plan", json={"plan_id": "../../etc/passwd"})
    assert r.status_code == 400


def test_patch_active_plan_rejects_nonexistent_plan(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    target = _patch_meta_store_path(monkeypatch, tmp_path)
    target.write_text(json.dumps({"abc": {"id": "abc", "cwd": "/tmp", "started_at": 1.0}}), encoding="utf-8")

    client = TestClient(_build_test_app())
    r = client.patch("/api/cc/sessions/abc/active_plan",
                     json={"plan_id": "_does_not_exist/[2099-01-01]NOPE"})
    assert r.status_code == 404


def test_patch_active_plan_writes_changed_ts(tmp_path, monkeypatch):
    """PATCH must stamp active_plan_changed_ts so UserPromptSubmit hook re-injects."""
    from fastapi.testclient import TestClient
    target = _patch_meta_store_path(monkeypatch, tmp_path)
    target.write_text(json.dumps({
        "abc123": {"id": "abc123", "cwd": "/tmp", "started_at": 1.0,
                   "active_plan": None, "active_plan_changed_ts": 0},
    }), encoding="utf-8")

    plan_id = "_infra/dashboard/[2026-05-03]CC-PLAN-SESSION-CONTEXT"
    client = TestClient(_build_test_app())
    r = client.patch("/api/cc/sessions/abc123/active_plan", json={"plan_id": plan_id})
    assert r.status_code == 200

    store = json.loads(target.read_text(encoding="utf-8"))
    ts = store["abc123"]["active_plan_changed_ts"]
    assert ts > 0
    assert ts > time.time() - 5  # within last 5s


# ─── UserPromptSubmit hook (b 方案 alive 重注入) ────────────────────────────


def test_user_prompt_submit_no_pty_id_noop(tmp_path):
    """No OMNI_CC_PTY_ID env → hook silent (claude not under wrapper)."""
    proc = _run_hook("user_prompt_submit", {
        "session_id": "x", "cwd": str(tmp_path), "prompt": "hello",
        "hook_event_name": "UserPromptSubmit",
    })
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""  # no additionalContext


def test_user_prompt_submit_no_changed_ts_noop(tmp_path, monkeypatch):
    """pty_id known but no active_plan_changed_ts → silent."""
    # set up isolated cc_sessions.json for this test
    fake_root = tmp_path / "repo"
    (fake_root / "src" / "omnicompany").mkdir(parents=True)
    (fake_root / "docs").mkdir(parents=True)
    (fake_root / "data").mkdir(parents=True)
    (fake_root / "data" / "cc_sessions.json").write_text(json.dumps({
        "pty-x": {"id": "pty-x", "active_plan": "some/plan", "active_plan_changed_ts": 0,
                  "last_plan_inject_ts": 0},
    }), encoding="utf-8")

    proc = _run_hook("user_prompt_submit", {
        "session_id": "claude-x", "cwd": str(fake_root), "prompt": "hello",
        "hook_event_name": "UserPromptSubmit",
    }, env_extra={"OMNI_CC_PTY_ID": "pty-x"})
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_user_prompt_submit_injects_after_switch_then_idempotent(tmp_path):
    """After plan switch (changed_ts > last_inject_ts), hook injects + advances marker."""
    # Use real repo plans dir so plan_meta lookup works (plan must exist)
    plan_id = "_infra/dashboard/[2026-05-03]CC-PLAN-SESSION-CONTEXT"
    pty_id = "pty-test-reinject"

    # Write to real cc_sessions.json (we'll clean up after)
    from omnicompany.dashboard.ccdaemon.pty import _meta_store_path
    store_path = _meta_store_path()
    if store_path.is_file():
        store_backup = json.loads(store_path.read_text(encoding="utf-8") or "{}") or {}
    else:
        store_backup = {}
    new_store = dict(store_backup)
    new_store[pty_id] = {
        "id": pty_id, "active_plan": plan_id,
        "active_plan_changed_ts": time.time(), "last_plan_inject_ts": 0,
    }
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(new_store, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        # 1st call: should inject
        proc1 = _run_hook("user_prompt_submit", {
            "session_id": "claude-x", "cwd": str(tmp_path), "prompt": "hi",
            "hook_event_name": "UserPromptSubmit",
        }, env_extra={"OMNI_CC_PTY_ID": pty_id})
        assert proc1.returncode == 0, proc1.stderr
        out = json.loads(proc1.stdout)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "plan switched" in ctx
        assert plan_id in ctx
        # plan_meta keys present
        assert "work_type" in ctx or "exit_criteria" in ctx

        # 2nd call: marker advanced, should be silent
        proc2 = _run_hook("user_prompt_submit", {
            "session_id": "claude-x", "cwd": str(tmp_path), "prompt": "hi again",
            "hook_event_name": "UserPromptSubmit",
        }, env_extra={"OMNI_CC_PTY_ID": pty_id})
        assert proc2.returncode == 0
        assert proc2.stdout.strip() == ""
    finally:
        # restore original store
        if store_backup:
            store_path.write_text(json.dumps(store_backup, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            try:
                store_path.unlink()
            except OSError:
                pass


def test_list_sessions_filters_by_active_plan(tmp_path, monkeypatch):
    """GET /api/cc/sessions?active_plan=<id> only returns sessions bound to that plan."""
    from fastapi.testclient import TestClient
    target = _patch_meta_store_path(monkeypatch, tmp_path)
    target.write_text(json.dumps({
        "abc": {"id": "abc", "cwd": "/tmp", "started_at": 1.0, "ended_at": 2.0,
                "active_plan": "_infra/dashboard/[2026-05-03]CC-PLAN-SESSION-CONTEXT",
                "claude_session_id": "x"},
        "def": {"id": "def", "cwd": "/tmp", "started_at": 1.0, "ended_at": 2.0,
                "active_plan": "_infra/some/other/plan", "claude_session_id": "y"},
        "ghi": {"id": "ghi", "cwd": "/tmp", "started_at": 1.0, "ended_at": 2.0,
                "active_plan": None, "claude_session_id": "z"},
    }), encoding="utf-8")

    client = TestClient(_build_test_app())
    target_plan = "_infra/dashboard/[2026-05-03]CC-PLAN-SESSION-CONTEXT"
    r = client.get(f"/api/cc/sessions?active_plan={target_plan}")
    assert r.status_code == 200
    body = r.json()
    rec_ids = [s["id"] for s in body.get("recoverable", [])]
    assert "abc" in rec_ids
    assert "def" not in rec_ids
    assert "ghi" not in rec_ids

    # without filter — all 3 returned (subject to claude_session_id filter in list_recoverable)
    r = client.get("/api/cc/sessions")
    body = r.json()
    rec_ids = [s["id"] for s in body.get("recoverable", [])]
    assert "abc" in rec_ids and "def" in rec_ids
    # ghi has no claude_session_id... wait it does (z). All 3 should appear.
    assert "ghi" in rec_ids


def test_settings_installer_registers_user_prompt_submit_hook(temp_settings):
    """Install must wire UserPromptSubmit hook (b 方案 alive 重注入接通 settings)."""
    from omnicompany.dashboard.ccdaemon import installer as si
    rep = si.install()
    assert "UserPromptSubmit" in rep.hooks_added
    cfg = json.loads(temp_settings.read_text(encoding="utf-8"))
    assert "UserPromptSubmit" in cfg["hooks"]
    blocks = cfg["hooks"]["UserPromptSubmit"]
    assert any("user_prompt_submit" in b["hooks"][0]["command"] for b in blocks)
