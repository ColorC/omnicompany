"""End-to-end resume coverage for the T5 batch executor + miner assembly.

The existing test_batch_runner.py only unit-tests run_parallel_items and the
JsonCheckpoint round-trip in isolation. This file drives the real wiring in
work_history.miner.run_mining: the map phase runs through runtime.llm.batch
(run_parallel_items, per-item failure isolation), the surviving signals are
checkpointed to _last_signals.json, the run is interrupted, and a second pass
resumes from that on-disk product.

No real LLM: call_json is replaced by a deterministic fake keyed on `caller`,
so what is exercised is batch.py + the resume assembly, not a mock standing in
for the main flow.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnicompany.packages.services._governance.work_history import miner


def _msgs(n: int) -> list[dict[str, str]]:
    """n user messages, each long enough to land in its own map chunk."""
    return [
        {"ts": f"2026-06-1{i}T00:00:00+00:00", "src": "claude", "proj": "omni", "text": f"do task number {i} please " + "x" * 40}
        for i in range(n)
    ]


class _FakeCallJson:
    """Deterministic stand-in for runtime.llm.structured.call_json.

    Routes by `caller`: map calls return one signal derived from the chunk;
    a configured chunk index raises to exercise per-item failure isolation.
    Records every map chunk it actually processed so the test can prove the
    resume pass did NOT re-run already-completed map work.
    """

    def __init__(self, *, fail_chunk_token: str | None = None, interrupt_cluster: bool = False):
        self.fail_chunk_token = fail_chunk_token
        self.interrupt_cluster = interrupt_cluster
        self.map_chunks_seen: list[str] = []
        self.cluster_calls = 0
        self.reduce_calls = 0

    def __call__(self, *, system, user, schema=None, model=None, caller="", max_tokens=8000, **kw):
        if caller == "governance.work_history.map":
            self.map_chunks_seen.append(user)
            if self.fail_chunk_token and self.fail_chunk_token in user:
                raise RuntimeError("map LLM boom for this chunk")
            # one need signal per chunk, gist carries the chunk's task number
            num = user.split("do task number ", 1)[1].split(" ", 1)[0]
            return {"signals": [{"kind": "need", "gist": f"task {num}", "quote": user[:60], "project": "omni"}]}
        if caller.startswith("governance.work_history.cluster"):
            self.cluster_calls += 1
            if self.interrupt_cluster:
                # a true interruption AFTER the map checkpoint was written:
                # not an Exception, so miner's per-batch try/except cannot swallow it.
                raise KeyboardInterrupt("process killed mid-run")
            # echo each input line as a cluster (kind is stamped by miner, not us)
            lines = [ln for ln in user.splitlines() if ln.strip()]
            return {"clusters": [{"title": ln[:18], "count": 1, "projects": ["omni"], "examples": [ln[:60]]} for ln in lines]}
        if caller == "governance.work_history.reduce":
            self.reduce_calls += 1
            return {
                "recurring_needs": [{"title": "t", "count": 2, "projects": ["omni"], "examples": ["q"], "quick_action_hint": None}],
                "recurring_corrections": [],
            }
        raise AssertionError(f"unexpected caller {caller!r}")


@pytest.fixture
def wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point out_dir() at tmp and stub message/memory sourcing; keep batch.py real."""
    monkeypatch.setenv("OMNI_WORKSPACE_ROOT", str(tmp_path))
    # each message -> its own map chunk, so failure isolation is per-message
    monkeypatch.setattr(miner, "CHUNK_CHARS", 1)
    monkeypatch.setattr(miner, "_collect", lambda days, source: _msgs(4))
    monkeypatch.setattr(miner, "memory_snippets", lambda: [])
    out = tmp_path / "data" / "governance" / "work_history"
    return tmp_path, out


def test_resume_skips_completed_map_and_keeps_failed_isolated(wired, monkeypatch: pytest.MonkeyPatch):
    """First pass: map fails one chunk (isolated), checkpoint written, run interrupted
    at cluster. Resume pass: reads the on-disk signals, does NOT re-run map, finishes."""
    _root, out = wired

    # --- pass 1: real map via batch.py; chunk "number 2" fails; cluster interrupts ---
    fake1 = _FakeCallJson(fail_chunk_token="do task number 2", interrupt_cluster=True)
    monkeypatch.setattr(miner, "call_json", fake1)

    logs: list[str] = []
    with pytest.raises(KeyboardInterrupt):
        miner.run_mining(from_signals=False, echo=logs.append)

    # map ran through batch.py for all 4 chunks, isolating the one failure
    assert len(fake1.map_chunks_seen) == 4
    # checkpoint exists with only the 3 successful chunks' signals (failed one absent)
    signals_path = out / "_last_signals.json"
    assert signals_path.is_file()
    saved = json.loads(signals_path.read_text(encoding="utf-8"))
    saved_tasks = sorted(s["gist"] for s in saved)
    assert saved_tasks == ["task 0", "task 1", "task 3"]  # "task 2" failed -> not persisted
    # the interruption hit cluster after the checkpoint, so no findings were produced
    assert not list(out.glob("findings-*.json"))

    # --- pass 2: resume from the on-disk signals; map must NOT be called again ---
    fake2 = _FakeCallJson()  # no failures, no interrupt
    monkeypatch.setattr(miner, "call_json", fake2)

    result = miner.run_mining(from_signals=True, echo=logs.append)

    assert result["ok"] is True
    # resume consumed the checkpoint instead of re-running the (completed) map work
    assert fake2.map_chunks_seen == []
    assert fake2.cluster_calls >= 1 and fake2.reduce_calls == 1
    assert result["signals"] == 3  # the 3 already-completed chunks, not re-mined
    findings_files = list(out.glob("findings-*.json"))
    assert len(findings_files) == 1
    # latest.json points at the produced findings -> resume reached a real artifact
    latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    assert latest["findings"] == findings_files[0].name


def test_rerun_map_fills_previously_failed_item(wired, monkeypatch: pytest.MonkeyPatch):
    """A full re-map pass (from_signals=False) with the previously-failing chunk now
    healthy re-runs batch.py and back-fills the missing item into the checkpoint."""
    _root, out = wired

    # pass 1: chunk "number 2" fails, others succeed, checkpoint has 3 of 4
    fake1 = _FakeCallJson(fail_chunk_token="do task number 2")
    monkeypatch.setattr(miner, "call_json", fake1)
    r1 = miner.run_mining(from_signals=False, echo=lambda s: None)
    assert r1["ok"] is True and r1["signals"] == 3
    after_1 = sorted(s["gist"] for s in json.loads((out / "_last_signals.json").read_text(encoding="utf-8")))
    assert after_1 == ["task 0", "task 1", "task 3"]

    # pass 2: re-map with nothing failing -> batch.py covers all 4, failed item filled
    fake2 = _FakeCallJson()
    monkeypatch.setattr(miner, "call_json", fake2)
    r2 = miner.run_mining(from_signals=False, echo=lambda s: None)
    assert len(fake2.map_chunks_seen) == 4
    assert r2["signals"] == 4
    after_2 = sorted(s["gist"] for s in json.loads((out / "_last_signals.json").read_text(encoding="utf-8")))
    assert after_2 == ["task 0", "task 1", "task 2", "task 3"]  # "task 2" back-filled
