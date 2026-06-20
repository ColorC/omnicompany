# [OMNI] origin=claude-code domain=tests/guardian ts=2026-04-23T00:00:00Z type=test
"""Smoke tests for sentinel._run_once.

These tests exercise the wake/cooldown/state transition without touching the
real project sentinel state and without invoking real LLM or long patrol work.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from omnicompany.packages.services._core.guardian import sentinel
from omnicompany.packages.services._core.guardian.sentinel import (
    _run_once,
    read_sentinel_state,
    write_activity_ts,
    write_sentinel_state,
)


@pytest.fixture
def fresh_state(tmp_path: Path):
    (tmp_path / ".omni").mkdir()
    return tmp_path


def test_run_once_no_activity_returns_false(fresh_state: Path):
    did = _run_once(fresh_state, cooldown_s=0, llm_cooldown_s=0, verbose=False)
    assert did is False


def test_run_once_cooldown_blocks(fresh_state: Path):
    write_activity_ts(fresh_state, source="smoke")
    write_sentinel_state(
        fresh_state,
        {
            "last_patrol_ts": datetime.now(timezone.utc).isoformat(),
            "last_processed_activity_ts": "2000-01-01T00:00:00+00:00",
        },
    )

    did = _run_once(fresh_state, cooldown_s=3600, llm_cooldown_s=0, verbose=False)
    assert did is False


def test_run_once_runs_patrol_and_updates_state(
    fresh_state: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from omnicompany.packages.services._core import guardian as guardian_pkg
    from omnicompany.packages.services._core.guardian import tow_truck
    from omnicompany.packages.services._core.guardian import workspace_pollution
    from omnicompany.packages.services._core.guardian import workers

    calls: dict[str, object] = {}

    def fake_run_patrol(**kwargs):
        calls["patrol_kwargs"] = kwargs
        return {"files_scanned": 3, "violations_found": 1, "scan_mode": "test"}

    class FakeHygieneScanWorker:
        def run(self, input_data):
            calls["hygiene_input"] = input_data

            class Verdict:
                output = {"violation_count": 0, "candidate_count": 0, "by_rule": {}}

            return Verdict()

    class FakeTow:
        def __init__(self, project_root):
            calls["tow_root"] = project_root

        def escalate_overdue_tickets(self, threshold_days):
            calls["tow_threshold_days"] = threshold_days
            return {"escalated_count": 0, "escalated_ticket_ids": []}

    def fake_workspace_scan(omni_root):
        calls["workspace_root"] = omni_root
        return {"total_tickets": 0, "by_root": {}}

    monkeypatch.setattr(guardian_pkg, "run_patrol", fake_run_patrol)
    monkeypatch.setattr(workers, "HygieneScanWorker", FakeHygieneScanWorker)
    monkeypatch.setattr(tow_truck, "OmniTow", FakeTow)
    monkeypatch.setattr(workspace_pollution, "run_workspace_pollution_scan", fake_workspace_scan)

    write_sentinel_state(
        fresh_state,
        {
            "last_patrol_ts": "2020-01-01T00:00:00+00:00",
            "last_llm_patrol_ts": datetime.now(timezone.utc).isoformat(),
            "last_processed_activity_ts": "2000-01-01T00:00:00+00:00",
            "patrol_count": 4,
            "llm_patrol_count": 2,
        },
    )
    write_activity_ts(fresh_state, source="sentinel-smoke-test")

    did = _run_once(
        fresh_state,
        cooldown_s=0,
        llm_cooldown_s=999999999,
        verbose=False,
    )

    assert did is True
    patrol_kwargs = calls["patrol_kwargs"]
    assert patrol_kwargs["project_root"] == fresh_state
    assert patrol_kwargs["full_scan"] is True
    assert patrol_kwargs["use_llm"] is False
    assert patrol_kwargs["use_agent"] is False

    state = read_sentinel_state(fresh_state)
    assert state["patrol_count"] == 5
    assert state["llm_patrol_count"] == 2
    assert state["last_patrol_ts"]
