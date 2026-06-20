"""材料统一 T2 — reviewstage kind/tier 由 Format tags 扩展。"""
from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omnicompany.bus.sqlite import SQLiteBus
from omnicompany.dashboard.boss_sight.controller.tools import SubmitToReviewstageRouter
from omnicompany.dashboard.boss_sight.reviewstage import routes as rs_routes
from omnicompany.dashboard.boss_sight.reviewstage.material_types import (
    registered_review_kinds,
    registered_review_tiers,
    review_material_tags,
)
from omnicompany.dashboard.boss_sight.reviewstage.store import MaterialKind, MaterialStore
from omnicompany.packages.services._core.omnicompany.formats import register_formats
from omnicompany.protocol.format import Format, create_builtin_registry


def _isolate_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNI_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv("OMNICOMPANY_DB_DIR", raising=False)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _registry_with_novel_review_kind():
    registry = create_builtin_registry()
    register_formats(registry)
    registry.register(
        Format(
            id="omni.review-material.novel-chapter",
            name="小说章节审阅材料",
            description="一份需要进入 reviewstage 的小说章节材料, 通过 Format tag 扩展 kind/tier。",
            parent="omni.review-material",
            tags=[
                "omni.material",
                "content.review",
                "review.kind.novel_chapter",
                "review.tier.optional",
            ],
            json_schema={
                "type": "object",
                "properties": {"id": {"type": "string"}, "title": {"type": "string"}},
            },
        )
    )
    return registry


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


def test_registered_review_kind_and_tier_come_from_format_tags():
    registry = _registry_with_novel_review_kind()

    assert "novel_chapter" in registered_review_kinds(registry)
    assert "optional" in registered_review_tiers(registry)
    assert "novel_chapter" not in {item.value for item in MaterialKind}
    assert review_material_tags("novel_chapter", "optional") == [
        "review.kind.novel_chapter",
        "review.tier.optional",
    ]


def test_store_accepts_format_registered_kind_without_enum_change(tmp_path, monkeypatch):
    ws = _isolate_workspace(tmp_path, monkeypatch)
    store = MaterialStore(
        root=ws / "data" / "boss_sight" / "reviewstage",
        format_registry=_registry_with_novel_review_kind(),
    )

    material = store.create(
        kind="novel_chapter",
        tier="optional",
        title="Novel Chapter Draft",
        inline_content="Chapter 1 body",
        source_plan_id="story/novel",
    )

    assert material.kind == "novel_chapter"
    assert material.tier == "optional"
    events = _query_events("omni.review-material")
    assert len(events) == 1
    assert "review.kind.novel_chapter" in events[0].tags
    assert "review.tier.optional" in events[0].tags


def test_adjust_tier_accepts_format_registered_tier(tmp_path, monkeypatch):
    ws = _isolate_workspace(tmp_path, monkeypatch)
    store = MaterialStore(
        root=ws / "data" / "boss_sight" / "reviewstage",
        format_registry=_registry_with_novel_review_kind(),
    )
    material = store.create(
        kind="markdown",
        tier="important",
        title="Review Note",
        inline_content="Ready for optional tier",
        source_plan_id="story/novel",
    )

    updated = store.adjust_tier(material.id, new_tier="optional", by="controller")

    assert updated.tier == "optional"
    assert updated.history[-1]["event"] == "tier_change"
    assert updated.history[-1]["to"] == "optional"


def test_store_rejects_unregistered_kind(tmp_path, monkeypatch):
    ws = _isolate_workspace(tmp_path, monkeypatch)
    store = MaterialStore(root=ws / "data" / "boss_sight" / "reviewstage")

    try:
        store.create(
            kind="novel_chapter",
            tier="important",
            title="Novel Chapter Draft",
            inline_content="Chapter 1 body",
            source_plan_id="story/novel",
        )
    except ValueError as exc:
        assert "review.kind.novel_chapter" in str(exc)
    else:
        raise AssertionError("unregistered review kind should be rejected")


def test_http_create_accepts_format_registered_kind(tmp_path, monkeypatch):
    ws = _isolate_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(rs_routes, "_hub", None)
    monkeypatch.setattr(
        rs_routes,
        "_store_singleton",
        MaterialStore(
            root=ws / "data" / "boss_sight" / "reviewstage",
            format_registry=_registry_with_novel_review_kind(),
        ),
    )
    app = FastAPI()
    app.include_router(rs_routes.reviewstage_router)
    client = TestClient(app)

    response = client.post(
        "/api/boss-sight/reviewstage",
        json={
            "kind": "novel_chapter",
            "tier": "optional",
            "title": "Novel Chapter Draft",
            "source_plan_id": "story/novel",
            "inline_content": "Chapter 1 body",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["kind"] == "novel_chapter"
    assert response.json()["tier"] == "optional"


def test_submit_tool_schema_no_longer_hard_codes_kind_enum():
    props = SubmitToReviewstageRouter.INPUT_SCHEMA["properties"]

    assert "enum" not in props["kind"]
    assert "enum" not in props["tier"]
    assert "review.kind.*" in props["kind"]["description"]
