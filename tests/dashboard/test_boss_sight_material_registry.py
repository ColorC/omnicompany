"""BOSS SIGHT material registry convergence tests."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNI_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv("OMNICOMPANY_DB_DIR", raising=False)

    plan_dir = tmp_path / "docs" / "plans" / "dashboard" / "[2026-05-31]v2-10"
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "plan.md").write_text(
        "---\nstatus: active\ntitle: v2-10 Material Registry\n---\n\n- [ ] map materials\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "plans" / "dashboard" / "project.md").write_text(
        "---\ntitle: Dashboard Project\n---\n\nProject boundary\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "PROGRESS.md").write_text("Current progress checkpoint", encoding="utf-8")
    standards = tmp_path / "docs" / "standards" / "_global"
    standards.mkdir(parents=True, exist_ok=True)
    (standards / "verification_invariants.md").write_text("Verification standard", encoding="utf-8")
    (standards / "root_guard.md").write_text("Root guard boundary", encoding="utf-8")
    reports = tmp_path / "docs" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "[2026-06-01]QUALITY-AUDIT.md").write_text("Audit report", encoding="utf-8")

    prompt_dir = tmp_path / "src" / "omnicompany" / "dashboard" / "boss_sight" / "controller" / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / "system.md").write_text("Controller prompt", encoding="utf-8")

    package_dir = tmp_path / "src" / "omnicompany" / "packages" / "services" / "demo"
    (package_dir / "workers").mkdir(parents=True, exist_ok=True)
    (package_dir / "materials.py").write_text("MATERIAL = 'demo'\n", encoding="utf-8")
    (package_dir / "team_demo.py").write_text("TeamSpec = object\ndef build_demo(): pass\n", encoding="utf-8")
    (package_dir / "workers" / "planner.py").write_text("def run(): pass\n", encoding="utf-8")

    from omnicompany.core.projects_registry import set_project
    from omnicompany.dashboard.boss_sight.material_registry import invalidate_material_registry_cache
    from omnicompany.dashboard.boss_sight.progress import add_entry
    from omnicompany.packages.services._core.omnicompany.formats import CAPTURE
    from omnicompany.packages.services._core.omnicompany.material_events import publish_material_event

    set_project(
        "registry-demo",
        name="Registry Event Project",
        group="dashboard",
        plan_categories=["dashboard"],
        by="test",
    )
    add_entry("project", "registry-demo", "Progress from material event", by="test")
    publish_material_event(
        CAPTURE.id,
        {
            "capture_kind": "debug_start",
            "title": "Debug Capture",
            "comment": "Captured from event stream",
            "route": "/debug",
            "path": str(tmp_path / "captures" / "debug.md"),
        },
        source="test.capture",
    )
    invalidate_material_registry_cache()

    return tmp_path


@pytest.fixture(autouse=True)
def reset_singletons(monkeypatch):
    from omnicompany.dashboard.boss_sight.reviewstage import routes as rs_routes

    monkeypatch.setattr(rs_routes, "_store_singleton", None)
    monkeypatch.setattr(rs_routes, "_hub", None)
    yield


@pytest.fixture
def client(tmp_workspace):
    from omnicompany.dashboard.boss_sight.routes import boss_sight_router

    app = FastAPI()
    app.include_router(boss_sight_router)
    return TestClient(app)


def test_material_registry_classifies_context_and_executors(client):
    r = client.get("/api/boss-sight/material-registry", params={"limit": 200})
    assert r.status_code == 200
    body = r.json()
    items = body["items"]
    kinds = {item["kind"] for item in items}

    assert {
        "plan",
        "project",
        "standard",
        "guard",
        "progress",
        "capture",
        "audit",
        "prompt",
        "worker",
        "team",
        "material_definition",
    }.issubset(kinds)

    plan = next(item for item in items if item["kind"] == "plan")
    assert plan["layer"] == "context"
    assert plan["role"] == "direction"
    assert plan["status"] == "active"
    assert plan["format_id"] == "omni.plan"
    assert "omni.material" in plan["tags"]
    assert any(rel["label"] == "belongs_to_project" for rel in plan["relations"])

    project = next(item for item in items if item["kind"] == "project")
    assert project["source"] == "events"
    assert project["format_id"] == "omni.project"
    assert project["event_source"] == "core.projects_registry"

    progress = next(item for item in items if item["kind"] == "progress")
    assert progress["source"] == "events"
    assert progress["format_id"] == "omni.progress-entry"
    assert any(rel["label"] == "progress_for_project" for rel in progress["relations"])

    capture = next(item for item in items if item["kind"] == "capture")
    assert capture["source"] == "events"
    assert capture["format_id"] == "omni.capture"

    definitions = [item for item in items if item["kind"] == "material_definition"]
    assert definitions
    assert {item["source"] for item in definitions} == {"format_registry"}
    assert {"omni.plan", "omni.project", "omni.capture"}.issubset({item["format_id"] for item in definitions})

    worker = next(item for item in items if item["kind"] == "worker")
    assert worker["layer"] == "executor"
    assert worker["role"] == "executor"
    assert worker["open_ref"]["type"] == "worker"


def test_material_registry_filters(client):
    r = client.get("/api/boss-sight/material-registry", params={"kind": "guard"})
    assert r.status_code == 200
    guard_body = r.json()
    assert guard_body["items"]
    assert {item["kind"] for item in guard_body["items"]} == {"guard"}

    r = client.get("/api/boss-sight/material-registry", params={"role": "executor"})
    assert r.status_code == 200
    executor_kinds = {item["kind"] for item in r.json()["items"]}
    assert {"worker", "team"}.issubset(executor_kinds)

    r = client.get("/api/boss-sight/material-registry", params={"layer": "context", "status": "active"})
    assert r.status_code == 200
    assert any(item["kind"] == "plan" for item in r.json()["items"])

    r = client.get("/api/boss-sight/material-registry", params={"kind": "project"})
    assert r.status_code == 200
    project_items = r.json()["items"]
    assert project_items
    assert {item["format_id"] for item in project_items} == {"omni.project"}

    r = client.get("/api/boss-sight/material-registry", params={"q": "Verification"})
    assert r.status_code == 200
    assert any(item["kind"] == "standard" for item in r.json()["items"])


def _registry_item(*, status, with_relation):
    from omnicompany.dashboard.boss_sight.material_registry import (
        MaterialRegistryItem,
        MaterialRelation,
    )

    return MaterialRegistryItem(
        uri="omni://material/omni.project/ghost",
        id="omni.project/ghost",
        title="Ghost Project",
        kind="project",
        role="direction",
        layer="context",
        status=status,
        open_ref={"type": "project", "id": "ghost"},
        entity_uri="omni://project/ghost",
        # 活跃记录元数据更丰富(多一条 relation): 旧逻辑下它会在 dedup 里夺胜。
        relations=[MaterialRelation(kind="plan", id="p/1", label="belongs_to_plan")] if with_relation else [],
    )


@pytest.mark.parametrize("tombstone_first", [False, True])
def test_dedup_tombstone_wins_over_richer_active(tombstone_first):
    """同 id 的活跃记录(元数据更丰富) vs 删除墓碑: 墓碑必须权威获胜, 不论先后顺序。"""
    from omnicompany.dashboard.boss_sight.material_registry import _dedup

    active = _registry_item(status="active", with_relation=True)  # 更丰富(有 relation)
    tombstone = _registry_item(status="deleted", with_relation=False)  # 更稀疏

    items = [tombstone, active] if tombstone_first else [active, tombstone]
    deduped = _dedup(items)

    assert len(deduped) == 1
    winner = deduped[0]
    assert winner.id == "omni.project/ghost"
    assert winner.status == "deleted", "墓碑应对同一 id 权威获胜, 而非元数据更丰富的活跃记录"


def test_removed_project_absent_from_default_view_and_visible_under_deleted_filter(tmp_workspace):
    """走真实 set/remove project 事件流: 删除后默认(活跃)视图不显示该项目, 仅 status=deleted 时可见。"""
    from omnicompany.core.projects_registry import remove_project, set_project
    from omnicompany.dashboard.boss_sight.material_registry import (
        build_material_registry,
        invalidate_material_registry_cache,
    )

    set_project(
        "ghost-proj",
        name="Ghost Project",
        group="dashboard",
        plan_categories=["dashboard"],
        by="test",
    )
    assert remove_project("ghost-proj") is True
    invalidate_material_registry_cache()

    default_view = build_material_registry(kind="project", ws=tmp_workspace)
    default_ids = {i["id"] for i in default_view["items"]}
    assert "omni.project/ghost-proj" not in default_ids, "已删项目不应出现在默认活跃视图"
    assert all(i["status"] != "deleted" for i in default_view["items"])

    deleted_view = build_material_registry(kind="project", status="deleted", ws=tmp_workspace)
    deleted = next(i for i in deleted_view["items"] if i["id"] == "omni.project/ghost-proj")
    assert deleted["status"] == "deleted"


def test_ctx_exposes_material_registry_summary(client):
    r = client.get("/api/boss-sight/ctx")
    assert r.status_code == 200
    body = r.json()
    plan_index = body["plan_index"]
    registry = body["material_registry"]

    assert plan_index["plans"]
    assert {item["format_id"] for item in plan_index["plans"]} == {"omni.plan"}
    assert registry["total"] >= 8
    assert registry["counts"]["by_layer"]["context"] >= 1
    assert registry["counts"]["by_layer"]["executor"] >= 1
    assert any(item["kind"] in {"guard", "standard"} for item in registry["execution_boundaries"])
    assert any(item["kind"] in {"worker", "team"} for item in registry["executors"])
