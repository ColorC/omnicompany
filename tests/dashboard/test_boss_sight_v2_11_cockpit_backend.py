from __future__ import annotations

import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNI_WORKSPACE_ROOT", str(tmp_path))

    plan_dir = tmp_path / "docs" / "plans" / "dashboard" / "[2026-06-02]v2-11-backend"
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "plan.md").write_text(
        "---\nstatus: in_progress\ntitle: v2-11 Backend First\n---\n\n- [ ] cockpit contract\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "plans" / "dashboard" / "project.md").write_text(
        "---\ntitle: Dashboard Project\n---\n\nProject context\n",
        encoding="utf-8",
    )
    standards = tmp_path / "docs" / "standards"
    standards.mkdir(parents=True, exist_ok=True)
    (standards / "review_policy.md").write_text("Review policy boundary", encoding="utf-8")

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    sessions = {
        "controller-main": {"provider": "controller", "alive": True, "cwd": str(tmp_path)},
        "chat-running": {
            "provider": "claude_code",
            "alive": True,
            "active_plan": "dashboard/[2026-06-02]v2-11-backend",
            "cwd": str(tmp_path),
            "started_at": time.time() - 120,
        },
        "chat-blocked": {
            "provider": "codex",
            "alive": False,
            "status": "blocked",
            "active_plan": "dashboard/[2026-06-02]v2-11-backend",
            "cwd": str(tmp_path),
        },
    }
    (data_dir / "cc_sessions.json").write_text(json.dumps(sessions), encoding="utf-8")
    return tmp_path


@pytest.fixture(autouse=True)
def reset_singletons(monkeypatch):
    from omnicompany.dashboard.boss_sight.reviewstage import routes as rs_routes
    from omnicompany.dashboard.boss_sight.services import control_observability_store as co_store

    monkeypatch.setattr(rs_routes, "_store_singleton", None)
    monkeypatch.setattr(rs_routes, "_hub", None)
    monkeypatch.setattr(co_store, "_singleton", None)
    yield


@pytest.fixture
def client(tmp_workspace):
    from omnicompany.dashboard.boss_sight.routes import boss_sight_router

    app = FastAPI()
    app.include_router(boss_sight_router)
    return TestClient(app)


def _seed_reviewstage():
    from omnicompany.dashboard.boss_sight.reviewstage.routes import get_store

    store = get_store()
    mandatory = store.create(
        kind="markdown",
        tier="mandatory",
        title="Mandatory design checkpoint",
        source_plan_id="dashboard/[2026-06-02]v2-11-backend",
        source_subagent_id="chat-running",
        inline_content="# checkpoint\n",
    )
    pushed = store.create(
        kind="markdown",
        tier="important",
        title="Important pushed material",
        source_plan_id="dashboard/[2026-06-02]v2-11-backend",
        source_subagent_id="chat-running",
        inline_content="# pushed\n",
    )
    store.mark_pushed(pushed.id, reason="Needs user decision")
    store.add_comment(pushed.id, content="Please turn this into a todo.", author="user")

    accepted = store.create(
        kind="markdown",
        tier="important",
        title="Accepted background material",
        source_plan_id="dashboard/[2026-06-02]v2-11-backend",
        inline_content="# accepted\n",
    )
    store.set_verdict(accepted.id, "accepted", by="user", reason="ok")
    return mandatory, pushed, accepted


def test_cockpit_contract_aggregates_backend_attention_and_notifications(client):
    mandatory, pushed, accepted = _seed_reviewstage()

    r = client.get("/api/boss-sight/cockpit", params={"attention_limit": 20, "notification_limit": 20})
    assert r.status_code == 200
    body = r.json()

    assert body["active_plan"]["plan_id"] == "dashboard/[2026-06-02]v2-11-backend"
    assert body["summary"]["review_total"] == 3
    assert body["summary"]["running_agents_total"] == 2
    assert body["running_agents"]["blocked_count"] == 1
    assert body["material_registry"]["total"] >= 3

    reasons = {item["reason"] for item in body["attention"]["items"]}
    assert "mandatory_material_unaccepted" in reasons
    assert "pushed_pending_material" in reasons
    assert "comment_feedback_delivered" in reasons
    assert "subagent_blocked" in reasons

    mandatory_item = next(item for item in body["attention"]["items"] if item["reason"] == "mandatory_material_unaccepted")
    assert mandatory_item["priority"] == "critical"
    assert mandatory_item["target"]["id"] == mandatory.id
    assert mandatory_item["open_ref"]["url"].endswith(mandatory.id)

    pushed_item = next(item for item in body["attention"]["items"] if item["reason"] == "pushed_pending_material")
    assert pushed_item["target"]["id"] == pushed.id
    assert "Open review" in {action["label"] for action in pushed_item["actions"]}

    notification_events = {item["event"] for item in body["notifications"]["items"]}
    assert {"created", "pushed", "comment", "verdict"}.issubset(notification_events)
    assert any(item["target"]["id"] == accepted.id and item["event"] == "verdict" for item in body["notifications"]["items"])

    assert body["top_actions"][0]["kind"] == "resolve_attention"


def test_attention_endpoint_and_ctx_share_same_cockpit_semantics(client):
    _seed_reviewstage()

    attention = client.get("/api/boss-sight/attention", params={"attention_limit": 10})
    assert attention.status_code == 200
    attention_body = attention.json()
    assert attention_body["attention"]["critical_count"] >= 1
    assert any(item["reason"] == "subagent_blocked" for item in attention_body["attention"]["items"])

    ctx = client.get("/api/boss-sight/ctx")
    assert ctx.status_code == 200
    ctx_body = ctx.json()
    assert "cockpit" in ctx_body
    assert ctx_body["cockpit"]["active_plan"]["plan_id"] == "dashboard/[2026-06-02]v2-11-backend"
    assert any(item["reason"] == "mandatory_material_unaccepted" for item in ctx_body["cockpit"]["attention"])


def test_cockpit_actions_resolve_material_plan_and_blocked_agent_targets(client):
    _seed_reviewstage()

    body = client.get("/api/boss-sight/cockpit", params={"attention_limit": 20}).json()
    mandatory_item = next(item for item in body["attention"]["items"] if item["reason"] == "mandatory_material_unaccepted")
    blocked_item = next(item for item in body["attention"]["items"] if item["reason"] == "subagent_blocked")

    review_target = next(action["target"] for action in mandatory_item["actions"] if action["kind"] == "open_review")
    review = client.post("/api/boss-sight/actions/resolve", json={"target": review_target})
    assert review.status_code == 200
    assert review.json()["resolved"]["type"] == "review_material"

    plan_target = next(action["target"] for action in mandatory_item["actions"] if action["kind"] == "open_plan")
    plan = client.post("/api/boss-sight/actions/execute", json={
        "kind": "open_plan",
        "target": plan_target,
        "actor": "human",
    })
    assert plan.status_code == 200
    assert plan.json()["resolved"]["id"] == "dashboard/[2026-06-02]v2-11-backend"
    assert plan.json()["event"]["status"] == "succeeded"

    session_target = next(action["target"] for action in blocked_item["actions"] if action["kind"] == "open_session")
    session = client.post("/api/boss-sight/actions/execute", json={
        "kind": "open_session",
        "target": session_target,
        "actor": "controller",
    })
    assert session.status_code == 200
    assert session.json()["resolved"]["type"] == "cc_session"
    assert session.json()["resolved"]["id"] == "chat-blocked"


def test_cockpit_actions_advance_comment_feedback_and_audit_events(client):
    _mandatory, pushed, _accepted = _seed_reviewstage()

    body = client.get("/api/boss-sight/cockpit", params={"attention_limit": 20}).json()
    comment_item = next(item for item in body["attention"]["items"] if item["kind"] == "review_comment")
    action_targets = {action["kind"]: action["target"] for action in comment_item["actions"]}
    assert action_targets["acknowledge_attention"]["type"] == "review_comment"
    assert action_targets["mark_todo"]["material_id"] == pushed.id

    read = client.post("/api/boss-sight/actions/execute", json={
        "kind": "acknowledge_attention",
        "target": action_targets["acknowledge_attention"],
        "actor": "human",
        "note": "seen",
    })
    assert read.status_code == 200
    assert read.json()["effect"] == "comment_feedback"
    assert read.json()["feedback_status"] == "read"

    todo = client.post("/api/boss-sight/actions/execute", json={
        "kind": "mark_todo",
        "target": action_targets["mark_todo"],
        "actor": "controller",
        "note": "converted by cockpit action",
    })
    assert todo.status_code == 200
    assert todo.json()["previous_feedback_status"] == "read"
    assert todo.json()["feedback_status"] == "to_todo"

    done = client.post("/api/boss-sight/actions/execute", json={
        "kind": "complete_todo",
        "target": action_targets["complete_todo"],
        "actor": "controller",
        "note": "closed",
    })
    assert done.status_code == 200
    assert done.json()["feedback_status"] == "todo_done"

    from omnicompany.dashboard.boss_sight.reviewstage.routes import get_store

    material = get_store().get(pushed.id)
    assert material is not None
    comment = material.comments[0]
    assert comment.feedback_status == "todo_done"
    feedback_history = [event for event in material.history if event.get("event") == "comment_feedback"]
    assert [event["to"] for event in feedback_history[-3:]] == ["read", "to_todo", "todo_done"]

    attention = client.get("/api/boss-sight/attention", params={"attention_limit": 20}).json()
    assert not any(item["id"] == comment_item["id"] for item in attention["attention"]["items"])

    events = client.get("/api/boss-sight/actions/events").json()
    assert events["count"] >= 3
    assert {item["kind"] for item in events["items"][:3]} == {"complete_todo", "mark_todo", "acknowledge_attention"}


def test_cockpit_actions_return_auditable_errors(client):
    _seed_reviewstage()

    unknown = client.post("/api/boss-sight/actions/execute", json={
        "kind": "not_real",
        "target": {"type": "controller", "id": "main"},
        "actor": "human",
    })
    assert unknown.status_code == 400
    assert unknown.json()["detail"]["event"]["status"] == "failed"
    assert "unsupported cockpit action" in unknown.json()["detail"]["error"]

    missing = client.post("/api/boss-sight/actions/resolve", json={
        "target": {"type": "plan", "id": "dashboard/missing-plan"},
    })
    assert missing.status_code == 404

    wrong_target = client.post("/api/boss-sight/actions/execute", json={
        "kind": "mark_todo",
        "target": {"type": "review_material", "id": "mat_missing"},
        "actor": "human",
    })
    assert wrong_target.status_code == 400
    assert "requires a review_comment target" in wrong_target.json()["detail"]["error"]

    events = client.get("/api/boss-sight/actions/events").json()
    assert any(item["status"] == "failed" and item["kind"] == "not_real" for item in events["items"])


def test_workflow_summary_tracks_unresolved_resolved_actions_and_ctx_briefing(client):
    _mandatory, pushed, _accepted = _seed_reviewstage()

    initial = client.get("/api/boss-sight/workflow-summary").json()
    assert initial["status"] == "blocked"
    assert initial["summary"]["critical_count"] >= 2
    assert initial["summary"]["comment_unresolved_count"] == 1
    assert initial["comment_feedback"]["by_status"]["delivered"] == 1
    assert "mandatory_material_unaccepted" in initial["unresolved"]["by_reason"]
    assert initial["summary"]["blocked_agent_count"] == 1

    comment_item = next(item for item in initial["unresolved"]["items"] if item["kind"] == "review_comment")
    targets = {action["kind"]: action["target"] for action in comment_item["actions"]}
    for kind, actor in [
        ("acknowledge_attention", "human"),
        ("mark_todo", "controller"),
        ("complete_todo", "controller"),
    ]:
        r = client.post("/api/boss-sight/actions/execute", json={
            "kind": kind,
            "target": targets[kind],
            "actor": actor,
            "note": f"{kind} via workflow test",
        })
        assert r.status_code == 200

    failed = client.post("/api/boss-sight/actions/execute", json={
        "kind": "not_real",
        "target": {"type": "controller", "id": "main"},
        "actor": "human",
    })
    assert failed.status_code == 400

    after = client.get("/api/boss-sight/workflow-summary").json()
    assert after["comment_feedback"]["by_status"]["todo_done"] == 1
    assert after["summary"]["comment_unresolved_count"] == 0
    assert after["summary"]["comment_todo_done_count"] == 1
    assert after["summary"]["action_succeeded_count"] >= 3
    assert after["summary"]["action_failed_count"] >= 1
    assert after["action_history"]["last_failed"]["kind"] == "not_real"
    assert any(item["material_id"] == pushed.id for item in after["comment_feedback"]["recent_resolved"])
    assert not any(
        item.get("target", {}).get("comment_id") == comment_item["target"]["comment_id"]
        for item in after["unresolved"]["items"]
    )

    ctx = client.get("/api/boss-sight/ctx").json()
    assert ctx["workflow_summary"]["comment_feedback"]["by_status"]["todo_done"] == 1
    assert ctx["workflow_summary"]["action_history"]["failed_count"] >= 1

    briefing = client.get("/api/boss-sight/briefing").json()
    assert briefing["workflow_summary"]["summary"]["comment_todo_done_count"] == 1
    assert briefing["workflow_summary"]["action_history"]["last_failed"]["kind"] == "not_real"


def test_controller_prompt_builder_injects_workflow_summary(tmp_workspace):
    _seed_reviewstage()

    from omnicompany.bus.memory import MemoryBus
    from omnicompany.dashboard.boss_sight.controller.prompt_builder import ControllerPromptBuilder

    builder = ControllerPromptBuilder(template="", bus=MemoryBus(), workspace_root=str(tmp_workspace))
    message = builder.build_initial_messages({"prompt": "当前状态如何？"})[0]["content"]

    assert "## workflow summary" in message
    assert "status=blocked" in message
    assert "comment_feedback_by_status: delivered=1" in message
    assert "mandatory_material_unaccepted" in message
    assert "blocked_agents_top_" in message


@pytest.mark.asyncio
async def test_controller_waker_injected_event_message_includes_workflow_summary(tmp_workspace):
    from unittest.mock import MagicMock

    from omnicompany.dashboard.boss_sight.services.controller_waker import ControllerWaker

    _seed_reviewstage()

    ctrl = MagicMock()
    ctrl.id = "ctrl"
    ctrl.provider = "controller"
    ctrl.ended_at = None
    ctrl.archived = False
    ctrl.started_at = 1000.0
    sub = MagicMock()
    sub.id = "chat-running"
    sub.provider = "claude_code"

    mgr = MagicMock()
    mgr._event_subscribers = []
    mgr.subscribe_events = lambda cb: mgr._event_subscribers.append(cb)
    mgr._sessions = {"ctrl": ctrl, "chat-running": sub}
    submit_calls = []

    async def fake_submit(session, prompt, record_history=True):
        submit_calls.append((session.id, prompt, record_history))

    mgr.submit_user_prompt = fake_submit

    waker = ControllerWaker(chat_manager=mgr, aggregator=None)
    waker.attach()
    mgr._event_subscribers[0](sub, "subagent.completed", {
        "subagent_id": "chat-running",
        "provider": "claude_code",
        "active_plan": "dashboard/[2026-06-02]v2-11-backend",
        "verdict": "PASS",
        "last_assistant_preview": "done",
    }, [])

    import asyncio

    await asyncio.sleep(0.05)

    assert len(submit_calls) == 1
    _, prompt, record_history = submit_calls[0]
    assert record_history is True
    assert "event_type: subagent.completed" in prompt
    assert "## workflow summary" in prompt
    assert "mandatory_material_unaccepted" in prompt
    assert "comment_feedback_by_status: delivered=1" in prompt
