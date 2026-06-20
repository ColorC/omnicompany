from __future__ import annotations

import json

from omnicompany.runtime.llm.llm import LLMCallRecord, LLMMeter


def _record(caller: str = "unit.single") -> LLMCallRecord:
    return LLMCallRecord(
        model="deepseek-v4-pro",
        role="runtime_main",
        caller=caller,
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.001,
        latency_ms=12,
        stop_reason="end_turn",
    )


def test_singleton_meter_persists_jsonl(monkeypatch, tmp_path):
    meter_path = tmp_path / "meter.jsonl"
    monkeypatch.setenv("OMNI_LLM_METER_PATH", str(meter_path))
    LLMMeter._instance = None
    meter = LLMMeter.get_instance()
    meter.reset()

    meter.record(_record("governance.plan_steward"))

    lines = meter_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["caller"] == "governance.plan_steward"
    assert payload["input_tokens"] == 10
    assert payload["output_tokens"] == 5
    assert payload["cost_usd"] == 0.001


def test_fresh_meter_does_not_persist_by_default(monkeypatch, tmp_path):
    meter_path = tmp_path / "meter.jsonl"
    monkeypatch.setenv("OMNI_LLM_METER_PATH", str(meter_path))

    meter = LLMMeter()
    meter.record(_record())

    assert not meter_path.exists()
