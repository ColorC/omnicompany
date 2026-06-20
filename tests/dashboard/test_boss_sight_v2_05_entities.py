from __future__ import annotations

import json
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omnicompany.dashboard.boss_sight.entity_registry import (
    extract_entity_mentions,
    make_entity_uri,
    resolve_entity_uri,
    search_entities,
)
from omnicompany.dashboard.boss_sight.reviewstage import MaterialStore


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNI_WORKSPACE_ROOT", str(tmp_path))
    plan_dir = tmp_path / "docs" / "plans" / "dashboard" / "[2026-05-31]ROADMAP"
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "plan.md").write_text(
        "---\nstatus: active\ntitle: Roadmap\n---\n\n- [ ] ship ultra search\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "plans" / "dashboard" / "project.md").write_text(
        "---\ntitle: Dashboard\n---\n\nProject dashboard\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "guide.md").write_text("Ultra search guide", encoding="utf-8")
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "cc_sessions.json").write_text(
        json.dumps({
            "sess-1": {
                "provider": "claude_code",
                "active_plan": "dashboard/[2026-05-31]ROADMAP",
                "cwd": str(tmp_path),
                "alive": True,
            }
        }),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture(autouse=True)
def reset_singleton_store(monkeypatch):
    from omnicompany.dashboard.boss_sight.reviewstage import routes as rs_routes
    monkeypatch.setattr(rs_routes, "_store_singleton", None)
    monkeypatch.setattr(rs_routes, "_hub", None)
    yield


def test_entity_search_and_resolve_share_registry(tmp_workspace):
    store = MaterialStore(root=tmp_workspace / "data" / "boss_sight" / "reviewstage")
    mat = store.create(
        kind="markdown",
        tier="important",
        title="Briefing Material",
        inline_content="# Briefing",
        source_plan_id="dashboard/[2026-05-31]ROADMAP",
    )
    from omnicompany.dashboard.boss_sight.reviewstage import routes as rs_routes
    rs_routes._store_singleton = store

    hits = search_entities("Roadmap", ws=tmp_workspace)
    assert any(h["kind"] == "plan" and h["display"] == "@plan:Roadmap" for h in hits)

    material_hits = search_entities("Briefing", ws=tmp_workspace)
    assert any(h["kind"] == "review_material" and h["id"] == mat.id for h in material_hits)

    uri = make_entity_uri("plan", "dashboard/[2026-05-31]ROADMAP")
    resolved = resolve_entity_uri(uri, ws=tmp_workspace)
    assert resolved is not None
    assert resolved["open_ref"] == {"type": "plan", "id": "dashboard/[2026-05-31]ROADMAP"}


def test_entity_index_covers_declared_kinds(tmp_workspace):
    packages = tmp_workspace / "src" / "omnicompany" / "packages" / "domains" / "demo"
    (packages / "workers").mkdir(parents=True, exist_ok=True)
    (packages / "materials.py").write_text("MATERIAL = 'demo'\n", encoding="utf-8")
    (packages / "team_demo.py").write_text("TeamSpec = object\ndef build_demo(): pass\n", encoding="utf-8")
    (packages / "workers" / "planner.py").write_text("def run(): pass\n", encoding="utf-8")

    store = MaterialStore(root=tmp_workspace / "data" / "boss_sight" / "reviewstage")
    store.create(
        kind="markdown",
        tier="important",
        title="Briefing Material",
        inline_content="# Briefing",
        source_plan_id="dashboard/[2026-05-31]ROADMAP",
    )
    from omnicompany.dashboard.boss_sight.reviewstage import routes as rs_routes
    rs_routes._store_singleton = store

    hits = search_entities("", limit=100, ws=tmp_workspace)
    kinds = {h["kind"] for h in hits}

    assert {
        "plan",
        "project",
        "file",
        "review_material",
        "material",
        "team",
        "worker",
        "cc_session",
        "subagent",
        "settings",
        "command",
    }.issubset(kinds)


def test_entity_routes_search_and_resolve(tmp_workspace):
    from omnicompany.dashboard.boss_sight.routes import boss_sight_router

    app = FastAPI()
    app.include_router(boss_sight_router)
    client = TestClient(app)

    r = client.get("/api/boss-sight/search", params={"q": "Roadmap"})
    assert r.status_code == 200
    assert any(item["kind"] == "plan" for item in r.json()["items"])

    uri = "omni://plan/" + quote("dashboard/[2026-05-31]ROADMAP", safe="")
    r = client.get("/api/boss-sight/entities/resolve", params={"uri": uri})
    assert r.status_code == 200
    assert r.json()["display"] == "@plan:Roadmap"

    r = client.get("/api/boss-sight/entities", params={"q": "review", "kind": "command", "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "command"
    assert body["count"] >= 1
    assert all(item["kind"] == "command" for item in body["items"])


def test_reviewstage_comment_stores_structured_mentions(tmp_workspace):
    from omnicompany.dashboard.boss_sight.reviewstage import routes as rs_routes
    from omnicompany.dashboard.boss_sight.reviewstage.routes import reviewstage_router

    store = MaterialStore(root=tmp_workspace / "data" / "boss_sight" / "reviewstage")
    rs_routes._store_singleton = store
    mat = store.create(
        kind="markdown",
        tier="important",
        title="Doc",
        inline_content="# Doc",
        source_plan_id="dashboard/[2026-05-31]ROADMAP",
    )

    app = FastAPI()
    app.include_router(reviewstage_router)
    client = TestClient(app)

    plan_uri = make_entity_uri("plan", "dashboard/[2026-05-31]ROADMAP")
    r = client.post(
        f"/api/boss-sight/reviewstage/{mat.id}/comment",
        json={
            "content": "请 @plan:Roadmap 看一下这段",
            "target": {"mentions": [{"uri": plan_uri, "display": "@plan:Roadmap"}]},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["target"]["mentions"][0]["uri"] == plan_uri
    assert body["target"]["mentions"][0]["display"] == "@plan:Roadmap"
    fresh = store.get(mat.id)
    assert fresh is not None
    assert fresh.history[-1]["mention_count"] == 1


def test_display_mention_without_uri_is_not_guessed_when_ambiguous(tmp_workspace):
    (tmp_workspace / "docs" / "plans" / "ops" / "[2026-05-31]ROADMAP").mkdir(parents=True)
    (tmp_workspace / "docs" / "plans" / "ops" / "[2026-05-31]ROADMAP" / "plan.md").write_text(
        "---\nstatus: active\ntitle: Roadmap\n---\n",
        encoding="utf-8",
    )

    mentions = extract_entity_mentions("请 @plan:Roadmap 看一下", ws=tmp_workspace)
    assert mentions
    assert mentions[0].get("ambiguous") is True
    assert len(mentions[0]["candidates"]) == 2
