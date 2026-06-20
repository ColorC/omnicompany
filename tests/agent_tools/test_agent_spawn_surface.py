from __future__ import annotations

import json
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

import pytest

from omnicompany.packages.services._core.agent.routers.agent_spawn import AgentRouter
from omnicompany.packages.services._core.agent.routers.single_tool import ToolContext
from omnicompany.packages.services._core.agent.spawn_surface import (
    AGENT_SPAWN_SURFACE_VERSION,
    ENTRY_AGENT_TOOL,
    ENTRY_CONTROLLER_SPAWN,
    ENTRY_EXTERNAL_WORKER_AS_AGENT,
    ENTRY_EXTERNAL_WORKER_RUN,
    ENTRY_INTERNAL_LOOP,
    ENTRY_TEAMRUNNER_NODE,
    ENTRY_WORKFLOW_RUN,
    agent_spawn_metadata,
    describe_agent_spawn_surface,
    ensure_agent_spawn_metadata,
    get_agent_spawn_entry,
    list_agent_spawn_entries,
)


def test_agent_spawn_surface_declares_canonical_launch_entries():
    entries = list_agent_spawn_entries()
    entry_ids = {entry.entry_id for entry in entries}

    assert {
        ENTRY_AGENT_TOOL,
        ENTRY_EXTERNAL_WORKER_RUN,
        ENTRY_CONTROLLER_SPAWN,
        ENTRY_WORKFLOW_RUN,
        ENTRY_EXTERNAL_WORKER_AS_AGENT,
        ENTRY_TEAMRUNNER_NODE,
        ENTRY_INTERNAL_LOOP,
    } <= entry_ids
    launch_ids = {entry.entry_id for entry in list_agent_spawn_entries(launch_only=True)}
    assert launch_ids == {
        ENTRY_AGENT_TOOL,
        ENTRY_EXTERNAL_WORKER_RUN,
        ENTRY_CONTROLLER_SPAWN,
        ENTRY_WORKFLOW_RUN,
    }
    assert ENTRY_TEAMRUNNER_NODE not in launch_ids
    assert ENTRY_INTERNAL_LOOP not in launch_ids
    assert all(entry.use_when and entry.new_usage_rule for entry in entries)
    assert "ExternalAgentRouter" not in json.dumps(describe_agent_spawn_surface())


def test_agent_spawn_metadata_is_authoritative():
    meta = agent_spawn_metadata(ENTRY_EXTERNAL_WORKER_RUN, entrypoint="unit")

    assert meta["agent_spawn_surface"] == AGENT_SPAWN_SURFACE_VERSION
    assert meta["agent_spawn_entry"] == ENTRY_EXTERNAL_WORKER_RUN
    assert meta["agent_spawn_kind"] == "external-worker"
    assert meta["agent_spawn_launch_surface"] is True
    assert meta["entrypoint"] == "unit"

    with pytest.raises(KeyError):
        get_agent_spawn_entry("new_unapproved_spawn_path")


def test_ensure_agent_spawn_metadata_normalizes_reserved_fields():
    meta = ensure_agent_spawn_metadata(
        ENTRY_EXTERNAL_WORKER_RUN,
        {
            "agent_spawn_entry": ENTRY_TEAMRUNNER_NODE,
            "agent_spawn_kind": "user-supplied-wrong-kind",
            "agent_spawn_surface": "stale",
            "caller": "test",
        },
    )

    assert meta["agent_spawn_surface"] == AGENT_SPAWN_SURFACE_VERSION
    assert meta["agent_spawn_entry"] == ENTRY_TEAMRUNNER_NODE
    assert meta["agent_spawn_kind"] == "adapter"
    assert meta["agent_spawn_launch_surface"] is False
    assert meta["caller"] == "test"


def test_agent_router_dry_run_marks_spawn_surface(monkeypatch):
    monkeypatch.setenv("OMNI_AGENT_DRY_RUN", "1")
    router = AgentRouter.__new__(AgentRouter)

    out = router._execute(
        {
            "description": "surface test",
            "prompt": "read only",
            "subagent_type": "Explore",
        },
        ToolContext(),
    )

    data = json.loads(out)
    assert data["dry_run"] is True
    assert data["agent_spawn_surface"] == AGENT_SPAWN_SURFACE_VERSION
    assert data["agent_spawn_entry"] == ENTRY_AGENT_TOOL
    assert data["agent_spawn_kind"] == "agent-tool"
