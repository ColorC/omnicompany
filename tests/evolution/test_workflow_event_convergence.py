from pathlib import Path

import pytest

from omnicompany.bus.memory import MemoryBus
from omnicompany.packages.domains.gameplay_system.ux.seven_tuple.runners import batch_runner
from omnicompany.packages.services._core.evolution.workflow.diagnosis import DiagnosisReport
from omnicompany.packages.services._core.evolution.workflow.experiment_runner import ExperimentRunner
from omnicompany.packages.services._core.evolution.workflow.hypothesis import HypothesisBoard
from omnicompany.packages.services._core.evolution.workflow.hypothesis_store import HypothesisBoardStore
from omnicompany.packages.services._core.evolution.workflow.orchestrator import EvolutionOrchestrator
from omnicompany.packages.services._core.evolution.workflow.pain_signal import QualityPainSignal


class _FakeInquiryStore:
    def list_all(self, limit: int = 50) -> list:
        return []

    def submit(self, inquiry) -> None:
        return None


class _FakeShallowTracer:
    def __init__(self, board: HypothesisBoard):
        self.board = board

    async def run(self, pain: QualityPainSignal, format_registry=None) -> HypothesisBoard:
        return self.board


def _board(*, trace_id: str = "trace-evo", status: str = "done") -> HypothesisBoard:
    return HypothesisBoard(
        board_id="board-evo",
        pipeline_id="pipeline-evo",
        trace_id=trace_id,
        quality_verdict="FAIL",
        status=status,
    )


@pytest.mark.asyncio
async def test_orchestrator_emits_lifecycle_events_to_eventbus(tmp_path):
    bus = MemoryBus()
    await bus.connect()
    board = _board()
    store = HypothesisBoardStore(tmp_path / "boards.db")
    orchestrator = EvolutionOrchestrator(
        store=store,
        llm=object(),
        max_cycles=1,
        inquiry_store=_FakeInquiryStore(),
        event_bus=bus,
    )
    orchestrator._shallow_tracer = _FakeShallowTracer(board)

    result = await orchestrator.run(
        QualityPainSignal(
            trace_id=board.trace_id,
            pipeline_id=board.pipeline_id,
            failing_node_id="quality_gate",
            quality_verdict="FAIL",
            expected_format="demo.output",
            actual_output_summary="demo failure",
        )
    )

    events = await bus.read_trace(board.trace_id)
    event_types = [event.event_type for event in events]
    assert result.final_status == "done"
    assert "evolution.workflow.started" in event_types
    assert "evolution.workflow.board_ready" in event_types
    assert event_types[-1] == "evolution.workflow.completed"
    assert events[-1].payload["board_id"] == board.board_id
    assert events[-1].payload["final_status"] == "done"


@pytest.mark.asyncio
async def test_experiment_runner_default_path_and_completion_event(tmp_path):
    bus = MemoryBus()
    await bus.connect()
    board = _board(trace_id="trace-exp", status="diagnosing")
    store = HypothesisBoardStore(tmp_path / "boards.db")
    runner = ExperimentRunner(store=store, llm=object(), event_bus=bus)

    result = await runner.run(
        board,
        DiagnosisReport(
            root_cause_node="node_a",
            root_cause_explanation="no proposed changes",
            comparison_with_success="",
            confidence=0.4,
            uncertainty="empty report",
        ),
    )

    assert runner.experiment_bus_path is None
    assert result.verdict == "failed_to_apply"
    events = await bus.read_trace(board.trace_id)
    assert [event.event_type for event in events] == ["evolution.workflow.experiment_completed"]
    assert events[0].source == "evolution.workflow.experiment_runner"


def test_seven_tuple_batch_runner_is_marked_as_tool():
    path = Path(batch_runner.__file__)
    header = "\n".join(path.read_text(encoding="utf-8").splitlines()[:4])
    assert "type=tool" in header
    assert "tags=tool,runner,batch,gameplay_system_ux,seven_tuple" in header
