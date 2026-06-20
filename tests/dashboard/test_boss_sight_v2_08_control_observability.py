from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNI_WORKSPACE_ROOT", str(tmp_path))
    plan_dir = tmp_path / "docs" / "plans" / "dashboard" / "[2026-05-31]v2-08"
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "plan.md").write_text(
        "---\nstatus: active\ntitle: v2-08\n---\n\n- [ ] dual control\n",
        encoding="utf-8",
    )
    guard_dir = tmp_path / "docs" / "guard"
    guard_dir.mkdir(parents=True, exist_ok=True)
    (guard_dir / "project_guard.md").write_text("hard guard stays unchanged\n", encoding="utf-8")
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture(autouse=True)
def reset_singletons(monkeypatch):
    from omnicompany.dashboard.boss_sight.reviewstage import routes as rs_routes
    from omnicompany.dashboard.boss_sight.services import control_observability_store as co_store

    monkeypatch.setattr(co_store, "_singleton", None)
    monkeypatch.setattr(rs_routes, "_store_singleton", None)
    monkeypatch.setattr(rs_routes, "_hub", None)
    yield


@pytest.fixture
def client(tmp_workspace):
    from omnicompany.dashboard.boss_sight.routes import boss_sight_router

    app = FastAPI()
    app.include_router(boss_sight_router)
    return TestClient(app)


def test_control_update_records_actor_reason_and_history(client):
    r = client.get("/api/boss-sight/control")
    assert r.status_code == 200
    body = r.json()
    assert body["by_key"]["controller.auto_wake"]["value"] is True

    r = client.post(
        "/api/boss-sight/control/controller.auto_wake",
        json={"value": False, "actor": "controller", "reason": "pause noisy wakeups"},
    )
    assert r.status_code == 200
    item = r.json()
    assert item["value"] is False
    assert item["updated_by"] == "controller"
    assert item["history"][-1]["previous"] is True
    assert item["history"][-1]["next"] is False
    assert item["history"][-1]["reason"] == "pause noisy wakeups"

    assert client.post(
        "/api/boss-sight/control/unknown.key",
        json={"value": True, "actor": "human"},
    ).status_code == 404
    assert client.post(
        "/api/boss-sight/control/controller.auto_wake",
        json={"value": True, "actor": "worker"},
    ).status_code == 400


def test_permanent_allow_only_writes_user_prefs(tmp_workspace, client):
    guard_file = tmp_workspace / "docs" / "guard" / "project_guard.md"
    plan_file = tmp_workspace / "docs" / "plans" / "dashboard" / "[2026-05-31]v2-08" / "plan.md"
    before_guard = guard_file.read_text(encoding="utf-8")
    before_plan = plan_file.read_text(encoding="utf-8")

    r = client.post(
        "/api/boss-sight/user-prefs/permanent_allow",
        json={
            "scope": "user",
            "tool": "Bash",
            "pattern": "npm run build",
            "reason": "local dashboard build",
            "actor": "human",
        },
    )
    assert r.status_code == 200
    assert r.json()["tool"] == "Bash"

    prefs_path = tmp_workspace / "data" / "boss_sight" / "user_prefs.json"
    prefs = json.loads(prefs_path.read_text(encoding="utf-8"))
    assert prefs["permanent_allow"][0]["pattern"] == "npm run build"
    assert guard_file.read_text(encoding="utf-8") == before_guard
    assert plan_file.read_text(encoding="utf-8") == before_plan

    r = client.post(
        "/api/boss-sight/user-prefs/permanent_allow",
        json={"scope": "user", "tool": "Write", "actor": "controller"},
    )
    assert r.status_code == 400


def test_observability_defaults_and_dimension_filtering(client):
    r = client.get("/api/boss-sight/observability/settings")
    assert r.status_code == 200
    settings = r.json()
    assert settings["dimensions"] == {
        "click": True,
        "selection": True,
        "toggle_change": True,
        "view_dwell": True,
    }

    r = client.post(
        "/api/boss-sight/observability/settings",
        json={"dimensions": {"selection": False}, "actor": "human", "reason": "privacy"},
    )
    assert r.status_code == 200
    assert r.json()["dimensions"]["selection"] is False

    r = client.post(
        "/api/boss-sight/observability/event",
        json={"dimension": "selection", "surface": "review-stage", "target": "doc", "value": "selected"},
    )
    assert r.status_code == 200
    assert r.json()["recorded"] is False
    assert r.json()["reason"] == "dimension_disabled"

    r = client.post(
        "/api/boss-sight/observability/event",
        json={"dimension": "click", "surface": "review-stage", "target": "accept"},
    )
    assert r.status_code == 200
    assert r.json()["recorded"] is True

    r = client.get("/api/boss-sight/observability/recent", params={"limit": 10})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["dimension"] == "click"
    assert items[0]["target"] == "accept"

    assert client.post(
        "/api/boss-sight/observability/event",
        json={"dimension": "mousemove", "surface": "dashboard"},
    ).status_code == 400


def test_briefing_and_ctx_expose_control_and_observability(client):
    client.post(
        "/api/boss-sight/control/reviewstage.push_to_user",
        json={"value": False, "actor": "human", "reason": "manual review only"},
    )
    client.post(
        "/api/boss-sight/observability/event",
        json={"dimension": "view_dwell", "surface": "dashboard-shell", "target": "/"},
    )

    briefing = client.get("/api/boss-sight/briefing")
    assert briefing.status_code == 200
    body = briefing.json()
    assert body["controls"]["by_key"]["reviewstage.push_to_user"]["value"] is False
    assert body["observability"]["recent"][0]["dimension"] == "view_dwell"

    ctx = client.get("/api/boss-sight/ctx")
    assert ctx.status_code == 200
    ctx_body = ctx.json()
    assert ctx_body["controls"]["by_key"]["reviewstage.push_to_user"]["updated_by"] == "human"
    assert ctx_body["observability"]["settings"]["dimensions"]["click"] is True
