"""材料统一 T1 — 公司级材料写入口发布 FactoryEvent。"""
from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omnicompany.bus.sqlite import SQLiteBus
from omnicompany.dashboard.boss_sight import progress
from omnicompany.dashboard.boss_sight.captures import routes as capture_routes
from omnicompany.dashboard.boss_sight.reviewstage.store import (
    MaterialKind,
    MaterialStore,
    MaterialTier,
)
from omnicompany.core import projects_registry


def _isolate_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNI_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv("OMNICOMPANY_DB_DIR", raising=False)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    return tmp_path


async def _query_events_async(event_type: str):
    bus = SQLiteBus()
    await bus.connect()
    try:
        return await bus.query(event_type=event_type, limit=50)
    finally:
        await bus.close()


def _query_events(event_type: str):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_query_events_async(event_type))
    finally:
        loop.close()


def test_progress_add_entry_publishes_material_event(tmp_path, monkeypatch):
    ws = _isolate_workspace(tmp_path, monkeypatch)

    entry = progress.add_entry("project", "demo-project", "first note", by="agent")

    assert (ws / "data" / "boss_sight" / "progress.json").is_file()
    events = _query_events("omni.progress-entry")
    assert len(events) == 1
    event = events[0]
    assert event.source == "boss_sight.progress"
    assert event.payload["id"] == entry["id"]
    assert event.payload["ref_id"] == "demo-project"
    assert event.payload["text"] == "first note"
    assert "omni.material" in event.tags


def test_project_set_and_remove_publish_material_events(tmp_path, monkeypatch):
    _isolate_workspace(tmp_path, monkeypatch)

    item = projects_registry.set_project("demo", name="Demo", group="other", by="agent")
    assert projects_registry.remove_project("demo") is True

    events = _query_events("omni.project")
    assert [event.source for event in events] == ["core.projects_registry", "core.projects_registry"]
    assert events[0].payload["id"] == item["id"]
    assert events[0].payload["name"] == "Demo"
    assert events[1].payload["id"] == "demo"
    assert events[1].payload["deleted"] is True


def test_capture_route_publishes_material_event_from_async_endpoint(tmp_path, monkeypatch):
    ws = _isolate_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(capture_routes, "_captures_root", lambda: ws / "captures")
    app = FastAPI()
    app.include_router(capture_routes.captures_router)
    client = TestClient(app)

    response = client.post(
        "/api/boss-sight/captures",
        json={
            "capture_kind": "element_comment",
            "title": "Button note",
            "comment": "check this button",
            "url": "http://127.0.0.1:8210/",
            "route": "/boss-sight",
            "target": {"selector": "#send", "label": "Send"},
            "enqueue": True,
        },
    )

    assert response.status_code == 200, response.text
    saved_path = response.json()["saved_path"]
    events = _query_events("omni.capture")
    assert len(events) == 1
    assert events[0].source == "boss_sight.captures"
    assert events[0].payload["path"] == saved_path
    assert events[0].payload["capture_kind"] == "element_comment"
    assert events[0].payload["target"]["selector"] == "#send"


def test_reviewstage_create_publishes_review_material_event(tmp_path, monkeypatch):
    ws = _isolate_workspace(tmp_path, monkeypatch)
    store = MaterialStore(root=ws / "data" / "boss_sight" / "reviewstage")

    material = store.create(
        kind=MaterialKind.markdown,
        tier=MaterialTier.important,
        title="Review note",
        inline_content="# Note",
        source_plan_id="demo/plan",
    )

    events = _query_events("omni.review-material")
    assert len(events) == 1
    assert events[0].source == "boss_sight.reviewstage"
    assert events[0].payload["id"] == material.id
    assert events[0].payload["kind"] == "markdown"
    assert events[0].payload["tier"] == "important"
    assert events[0].payload["source_plan_id"] == "demo/plan"


def test_query_material_events_reads_unified_material_stream(tmp_path, monkeypatch):
    _isolate_workspace(tmp_path, monkeypatch)

    progress.add_entry("project", "demo-project", "first note", by="agent")
    projects_registry.set_project("demo", name="Demo", group="other", by="agent")

    from omnicompany.packages.services._core.omnicompany.material_events import query_material_events

    progress_events = query_material_events(event_type="omni.progress-entry")

    assert len(progress_events) == 1
    assert progress_events[0].event_type == "omni.progress-entry"
    assert progress_events[0].payload["ref_id"] == "demo-project"
    assert "omni.material" in progress_events[0].tags


def test_publish_material_event_failure_is_best_effort(monkeypatch):
    from omnicompany.packages.services._core.omnicompany import material_events

    async def fail_publish(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(material_events, "_publish_material_event_async", fail_publish)

    event_id = material_events.publish_material_event(
        "omni.progress-entry",
        {"id": "entry-1", "ref_type": "project", "ref_id": "demo", "text": "x"},
        source="test",
    )

    assert event_id is None
