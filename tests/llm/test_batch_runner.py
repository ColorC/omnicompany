from __future__ import annotations

from pathlib import Path

from omnicompany.runtime.llm.batch import (
    JsonCheckpoint,
    load_json_checkpoint,
    read_batch_status,
    run_parallel_items,
    write_json_checkpoint,
)


def test_run_parallel_items_isolates_failures_and_preserves_success_order():
    def worker(value: int) -> int:
        if value == 2:
            raise ValueError("bad item")
        return value * 10

    logs: list[str] = []
    result = run_parallel_items(
        [1, 2, 3],
        worker,
        workers=3,
        item_label=lambda index, item: f"chunk {index}:{item}",
        echo=logs.append,
        progress_label="map",
        progress_every=1,
    )

    assert result.completed == 3
    assert result.total == 3
    assert result.results == [10, 30]
    assert result.failures == ["chunk 1:2: bad item"]
    assert result.failure_details[0].index == 1
    assert result.ok is False
    assert logs[-1] == "  map 3/3 ok=2 failed=1"


def test_run_parallel_items_writes_batch_status(tmp_path: Path):
    status_path = tmp_path / "batch_status.json"

    result = run_parallel_items(
        [1, 2],
        lambda value: value + 1,
        workers=2,
        progress_label="unit",
        progress_every=1,
        status_run_id="unit.batch",
        status_path=status_path,
    )

    status = read_batch_status(status_path=status_path)
    assert result.ok is True
    assert status["unit.batch"]["status"] == "completed"
    assert status["unit.batch"]["total"] == 2
    assert status["unit.batch"]["completed"] == 2
    assert status["unit.batch"]["successes"] == 2
    assert status["unit.batch"]["failures"] == 0
    assert status["unit.batch"]["progress_label"] == "unit"


def test_json_checkpoint_roundtrip_with_meta(tmp_path: Path):
    checkpoint = JsonCheckpoint(
        data_path=tmp_path / "signals.json",
        meta_path=tmp_path / "signals.meta.json",
    )

    write_json_checkpoint(
        checkpoint,
        [{"kind": "need", "gist": "run real tests"}],
        meta={"messages": 5, "chunks": 1},
        indent=1,
    )

    loaded = load_json_checkpoint(checkpoint)
    assert loaded.ok is True
    assert loaded.data == [{"kind": "need", "gist": "run real tests"}]
    assert loaded.meta == {"messages": 5, "chunks": 1}
    assert loaded.error is None


def test_json_checkpoint_missing_returns_configured_error(tmp_path: Path):
    checkpoint = JsonCheckpoint(
        data_path=tmp_path / "missing.json",
        missing_error="no signals checkpoint",
    )

    loaded = load_json_checkpoint(checkpoint)
    assert loaded.ok is False
    assert loaded.error == "no signals checkpoint"


def test_governance_consumers_use_runtime_batch_authority():
    root = Path(__file__).resolve().parents[2]
    steward = (
        root / "src/omnicompany/packages/services/_governance/plan_steward/steward.py"
    ).read_text(encoding="utf-8")
    miner = (
        root / "src/omnicompany/packages/services/_governance/work_history/miner.py"
    ).read_text(encoding="utf-8")

    for text in (steward, miner):
        assert "ThreadPoolExecutor" not in text
        assert "as_completed" not in text

    assert "run_parallel_items" in steward
    assert "run_parallel_items" in miner
    assert "JsonCheckpoint" in miner
    assert "load_json_checkpoint" in miner
    assert "write_json_checkpoint" in miner
