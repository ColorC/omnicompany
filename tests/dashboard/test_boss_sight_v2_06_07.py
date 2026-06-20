from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omnicompany.dashboard.boss_sight.reviewstage import MaterialStore


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNI_WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture(autouse=True)
def reset_reviewstage_store(monkeypatch):
    from omnicompany.dashboard.boss_sight.reviewstage import routes as rs_routes
    monkeypatch.setattr(rs_routes, "_store_singleton", None)
    monkeypatch.setattr(rs_routes, "_hub", None)
    yield


@pytest.fixture
def store(tmp_workspace):
    from omnicompany.dashboard.boss_sight.reviewstage import routes as rs_routes

    s = MaterialStore(root=tmp_workspace / "data" / "boss_sight" / "reviewstage")
    rs_routes._store_singleton = s
    return s


@pytest.fixture
def client(store):
    from omnicompany.dashboard.boss_sight.routes import boss_sight_router
    from omnicompany.dashboard.boss_sight.reviewstage.routes import reviewstage_router

    app = FastAPI()
    app.include_router(boss_sight_router)
    app.include_router(reviewstage_router)
    return TestClient(app)


def test_briefing_all_green_empty_state(client):
    r = client.get("/api/boss-sight/briefing")
    assert r.status_code == 200
    body = r.json()
    assert body["severity"] == "calm"
    assert body["all_green"] is True
    assert body["summary"]["review_total"] == 0
    assert body["next_actions"][0]["priority"] == "calm"


def test_briefing_surfaces_mandatory_review_blocker(client, store):
    mat = store.create(
        kind="markdown",
        tier="mandatory",
        title="Blocking review",
        inline_content="# Blocking",
        source_plan_id="dashboard/v2-07",
    )

    r = client.get("/api/boss-sight/briefing")
    assert r.status_code == 200
    body = r.json()
    assert body["severity"] == "critical"
    assert body["all_green"] is False
    assert body["summary"]["mandatory_unaccepted"] == 1
    assert body["review"]["recent"][0]["id"] == mat.id
    assert any(a["target"] == "reviewstage" for a in body["next_actions"])


def test_comment_feedback_state_machine(client, store):
    mat = store.create(
        kind="markdown",
        tier="important",
        title="Needs comment",
        inline_content="# Doc",
        source_plan_id="dashboard/v2-07",
    )

    r = client.post(
        f"/api/boss-sight/reviewstage/{mat.id}/comment",
        json={"content": "Please turn this into todo", "author": "user"},
    )
    assert r.status_code == 200
    comment = r.json()
    assert comment["feedback_status"] == "delivered"
    assert comment["feedback_history"][0]["status"] == "delivered"

    r = client.post(
        f"/api/boss-sight/reviewstage/{mat.id}/comments/{comment['id']}/feedback",
        json={"status": "to_todo", "by": "controller", "note": "created todo"},
    )
    assert r.status_code == 200
    assert r.json()["feedback_status"] == "to_todo"

    r = client.post(
        f"/api/boss-sight/reviewstage/{mat.id}/comments/{comment['id']}/feedback",
        json={"status": "todo_done", "by": "controller"},
    )
    assert r.status_code == 200
    assert r.json()["feedback_status"] == "todo_done"

    fresh = store.get(mat.id)
    assert fresh is not None
    assert any(h.get("event") == "comment_feedback" and h.get("to") == "todo_done" for h in fresh.history)


def test_comment_feedback_rejects_unknown_comment(client, store):
    mat = store.create(
        kind="markdown",
        tier="important",
        title="Doc",
        inline_content="# Doc",
        source_plan_id="dashboard/v2-07",
    )
    r = client.post(
        f"/api/boss-sight/reviewstage/{mat.id}/comments/cmt_missing/feedback",
        json={"status": "read"},
    )
    assert r.status_code == 404


def test_reviewstage_batch_verdict_tier_and_delete(client, store):
    a = store.create(kind="markdown", tier="important", title="A", inline_content="a")
    b = store.create(kind="markdown", tier="important", title="B", inline_content="b")
    c = store.create(kind="markdown", tier="important", title="C", inline_content="c")

    r = client.post(
        "/api/boss-sight/reviewstage/batch_verdict",
        json={"ids": [a.id, b.id, "mat_missing"], "verdict": "accepted", "reason": "batch"},
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body["changed_ids"]) == {a.id, b.id}
    assert body["not_found"] == ["mat_missing"]
    assert store.get(a.id).status == "accepted"
    assert store.get(b.id).status == "accepted"

    r = client.post(
        "/api/boss-sight/reviewstage/batch_tier",
        json={"ids": [a.id, b.id], "new_tier": "mandatory"},
    )
    assert r.status_code == 200
    assert store.get(a.id).tier == "mandatory"
    assert store.get(b.id).tier == "mandatory"

    r = client.post(
        "/api/boss-sight/reviewstage/batch_delete",
        json={"ids": [a.id, c.id], "include_pending": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["deleted_ids"] == [a.id]
    assert body["skipped_pending"] == 1
    assert store.get(a.id) is None
    assert store.get(c.id) is not None
