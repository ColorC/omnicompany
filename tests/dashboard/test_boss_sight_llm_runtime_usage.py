from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omnicompany.runtime.llm.batch import write_batch_status


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def _write_meter(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "timestamp": 1.0,
            "model": "deepseek-v4-pro",
            "role": "runtime_main",
            "caller": "unit.single",
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "cost_usd": 0.001,
            "latency_ms": 20,
            "stop_reason": "end_turn",
        },
        {
            "timestamp": 2.0,
            "model": "deepseek-v4-pro",
            "role": "runtime_main",
            "caller": "governance.plan_steward",
            "input_tokens": 30,
            "output_tokens": 7,
            "cache_read_tokens": 3,
            "cache_creation_tokens": 2,
            "cost_usd": 0.004,
            "latency_ms": 40,
            "stop_reason": "end_turn",
        },
        {
            "timestamp": 3.0,
            "model": "agent-model",
            "role": "agent",
            "caller": "agent_loop.turn_3",
            "input_tokens": 4,
            "output_tokens": 6,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "cost_usd": 0.002,
            "latency_ms": 10,
            "stop_reason": "end_turn",
        },
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("OMNI_WORKSPACE_ROOT", str(tmp_path))
    meter_path = tmp_path / "data" / "llm" / "meter.jsonl"
    status_path = tmp_path / "data" / "llm" / "batch_status.json"
    monkeypatch.setenv("OMNI_LLM_METER_PATH", str(meter_path))
    monkeypatch.setenv("OMNI_LLM_BATCH_STATUS_PATH", str(status_path))

    _write_meter(meter_path)
    write_batch_status(
        "governance.plan_steward",
        {
            "run_id": "governance.plan_steward",
            "status": "running",
            "progress_label": "plans",
            "total": 10,
            "completed": 4,
            "successes": 4,
            "failures": 0,
        },
        status_path=status_path,
    )
    _write_json(
        tmp_path / "data" / "registry" / "plan_governance.json",
        {
            "version": 1,
            "generated_at": "2026-06-13T00:00:00+00:00",
            "model": "deepseek-v4-pro",
            "plans": {"demo": {"project": None}},
        },
    )
    _write_json(
        tmp_path / "data" / "governance" / "work_history" / "latest.json",
        {
            "generated_at": "2026-06-13T00:01:00+00:00",
            "model": "deepseek-v4-pro",
            "messages": 3,
            "chunks": 1,
            "signals": 2,
            "clusters": 1,
            "failures": [],
            "findings": "findings-demo.json",
            "report": "report-demo.md",
        },
    )

    from omnicompany.dashboard.boss_sight.routes import boss_sight_router

    app = FastAPI()
    app.include_router(boss_sight_router)
    return TestClient(app)


def test_llm_runtime_usage_endpoint_summarizes_meter_batch_and_governance(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    response = client.get("/api/boss-sight/llm-runtime")
    assert response.status_code == 200
    body = response.json()

    assert body["available"] is True
    assert body["summary"]["call_count"] == 3
    assert body["summary"]["total_tokens"] == 67
    assert body["by_surface"]["single"]["call_count"] == 1
    assert body["by_surface"]["batch"]["call_count"] == 1
    assert body["by_surface"]["agent"]["call_count"] == 1
    assert body["batch"]["active_count"] == 1
    assert body["batch"]["runs"]["governance.plan_steward"]["completed"] == 4
    assert body["governance"]["plan_steward"]["plan_count"] == 1
    assert body["governance"]["work_history"]["signals"] == 2


def test_usage_endpoint_embeds_internal_llm_runtime_usage(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    from omnicompany.dashboard.boss_sight import usage as usage_mod

    monkeypatch.setattr(
        usage_mod,
        "build_usage",
        lambda force=False: {
            "generated_at": 1.0,
            "source": "unit",
            "claude": {"available": True},
            "codex": {"available": True},
        },
    )

    response = client.get("/api/boss-sight/usage")
    assert response.status_code == 200
    body = response.json()

    assert body["claude"]["available"] is True
    assert body["internal"]["summary"]["call_count"] == 3
    assert body["internal"]["batch"]["active_count"] == 1
