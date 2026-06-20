"""端到端进化工作流测试

流程：
  1. 用 lang_rewrite 管线翻译一个 Python 文件 → 生成 SQLiteBus trace (record_io=True)
  2. 检查是否有 FAIL 节点
  3. 若有，构造 QualityPainSignal，启动 B.1→B.5 进化工作流
  4. 打印诊断报告和实验结果

用法：
    python scripts/test_evolution_e2e.py [--py-file path/to/file.py]
"""
from __future__ import annotations

import asyncio
import argparse
import logging
import os
import pathlib
import sys
import tempfile

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    stream=sys.stderr,
)
# 减少无关噪音
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)

logger = logging.getLogger("evo_e2e")

TS_DIR = pathlib.Path("data/rewrite/ts_phase1")
WORK_DIR = pathlib.Path(tempfile.mkdtemp(prefix="evo_e2e_"))
BOARDS_DB = "evo_e2e_boards.db"
EVENTS_DB = "evo_e2e_events.db"


async def run_pipeline(py_file: pathlib.Path) -> tuple[str | None, str | None]:
    """跑 lang_rewrite 管线，返回 (trace_id, pipeline_id)"""
    from omnicompany.bus.sqlite import SQLiteBus
    from omnicompany.packages.domains.software_engineering.lang_rewrite.pipeline import build_pipeline, DOMAIN
    from omnicompany.packages.domains.software_engineering.lang_rewrite.run import build_bindings
    from omnicompany.runtime.exec.runner import PipelineRunner

    pipeline_input = {
        "source_path": str(py_file),
        "ts_dir": str(TS_DIR),
        "work_dir": str(WORK_DIR),
    }

    pipeline = build_pipeline()
    bindings = build_bindings(pipeline_input)
    pipeline_id = f"{DOMAIN}-pipeline"

    bus = SQLiteBus(EVENTS_DB)
    await bus.connect()

    runner = PipelineRunner(pipeline=pipeline, bindings=bindings, bus=bus)
    try:
        logger.info("Running lang_rewrite pipeline on %s ...", py_file.name)
        await runner.run(pipeline_input)
        trace_id = str(runner.last_trace_id)
        logger.info("Pipeline finished. trace_id=%s", trace_id)
    except Exception as e:
        logger.error("Pipeline failed with exception: %s", e)
        trace_id = str(runner.last_trace_id) if runner.last_trace_id else None
    finally:
        await bus.close()

    return trace_id, pipeline_id


async def check_trace_failure(trace_id: str) -> tuple[str | None, str | None]:
    """检查 trace 是否有 FAIL 节点，返回 (failing_node_id, quality_verdict)"""
    from omnicompany.bus.sqlite import SQLiteBus
    import json

    bus = SQLiteBus(EVENTS_DB)
    await bus.connect()
    events = await bus.read_trace(trace_id)
    await bus.close()

    fail_node = None
    for ev in events:
        payload = ev.payload
        verdict = payload.get("verdict", "")
        if str(verdict).upper() == "FAIL":
            node = payload.get("node", "")
            if node:
                fail_node = node
                logger.info("Found FAIL node: %s", node)

    if fail_node:
        return fail_node, "FAIL"

    # 检查是否有 PARTIAL
    for ev in events:
        payload = ev.payload
        verdict = payload.get("verdict", "")
        if str(verdict).upper() == "PARTIAL":
            node = payload.get("node", "")
            if node:
                logger.info("Found PARTIAL node: %s", node)
                return node, "PARTIAL"

    return None, None


async def run_evolution(trace_id: str, pipeline_id: str, failing_node: str, py_file: pathlib.Path):
    """启动 B.1→B.5 进化工作流"""
    from omnicompany.packages.services._core.evolution.workflow.orchestrator import EvolutionOrchestrator
    from omnicompany.packages.services._core.evolution.workflow.hypothesis_store import HypothesisBoardStore
    from omnicompany.packages.services._core.evolution.workflow.pain_signal import QualityPainSignal

    store = HypothesisBoardStore(BOARDS_DB)

    pain = QualityPainSignal(
        pipeline_id=pipeline_id,
        trace_id=trace_id,
        failing_node_id=failing_node,
        quality_verdict="FAIL",
        expected_format="TypeScript code that passes tsc --strict",
        actual_output_summary=f"Translation of {py_file.name} failed at node {failing_node}",
        bus_path=EVENTS_DB,
        pipeline_input={
            "source_path": str(py_file),
            "ts_dir": str(TS_DIR),
            "work_dir": str(WORK_DIR),
        },
    )

    orchestrator = EvolutionOrchestrator(
        store=store,
        bus_path=EVENTS_DB,
        max_cycles=2,
    )

    logger.info("Starting evolution orchestrator (B.1→B.5) ...")
    result = await orchestrator.run(pain)

    print("\n" + "="*60)
    print("进化工作流结果")
    print("="*60)
    print(f"最终状态: {result.final_status}")
    print(f"运行轮数: {result.cycles}")
    print(f"Board ID: {result.board.board_id}")
    print()

    if result.diagnosis_reports:
        report = result.diagnosis_reports[-1]
        print(f"[B.2 诊断]")
        print(f"  根因节点: {report.root_cause_node}")
        print(f"  错误类别: {report.error_category}")
        print(f"  置信度:   {report.confidence:.2f}")
        print(f"  解释:     {report.root_cause_explanation[:120]}")
        if report.proposed_changes:
            ch = report.proposed_changes[0]
            print(f"  变更类型: {ch.change_type}")
            print(f"  变更节点: {ch.target_node}")
            print(f"  描述:     {ch.change_description[:100]}")
        if report.format_adequacy_check:
            print(f"  Format充分性检查: {len(report.format_adequacy_check)} 节点")
        print()

    if result.experiment_results:
        exp = result.experiment_results[-1]
        print(f"[B.3 实验]")
        print(f"  实验状态: {exp.verdict}")
        print(f"  改善分数: {exp.improvement_score:.2f}")
        if exp.applied:
            print(f"  补丁已应用: 是")
        if exp.notes:
            print(f"  备注: {exp.notes[:120]}")
        print()

    print("="*60)
    return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--py-file",
        default="src/omnicompany/runtime/embedding_client.py",
        help="Python 文件路径（要翻译的源文件）",
    )
    parser.add_argument(
        "--skip-pipeline",
        help="跳过管线执行，直接用此 trace_id 进行进化",
    )
    args = parser.parse_args()

    py_file = pathlib.Path(args.py_file)
    if not py_file.exists():
        print(f"文件不存在: {py_file}")
        sys.exit(1)

    if args.skip_pipeline:
        trace_id = args.skip_pipeline
        pipeline_id = "lang_rewrite-pipeline"
        logger.info("Skipping pipeline, using trace_id=%s", trace_id)
    else:
        trace_id, pipeline_id = await run_pipeline(py_file)

    if not trace_id:
        print("管线未产生 trace，退出")
        sys.exit(1)

    print(f"\ntrace_id: {trace_id}")
    print(f"pipeline_id: {pipeline_id}")

    failing_node, quality_verdict = await check_trace_failure(trace_id)
    if not failing_node:
        print("\n所有节点 PASS，管线成功完成，无需进化！")
        sys.exit(0)

    print(f"发现 FAIL 节点: {failing_node}，启动进化工作流...\n")
    await run_evolution(trace_id, pipeline_id, failing_node, py_file)


if __name__ == "__main__":
    asyncio.run(main())


async def continue_board(board_id: str, extra_cycles: int = 5):
    """从已有 board 继续进化"""
    from omnicompany.packages.services._core.evolution.workflow.orchestrator import EvolutionOrchestrator
    from omnicompany.packages.services._core.evolution.workflow.hypothesis_store import HypothesisBoardStore

    store = HypothesisBoardStore(BOARDS_DB)
    orch = EvolutionOrchestrator(
        store=store, bus_path=EVENTS_DB,
        max_cycles=extra_cycles,
    )
    result = await orch.continue_from_board(board_id)
    print(f"\n{'='*60}")
    print(f"继续进化结果 (board={board_id[:8]})")
    print(f"{'='*60}")
    print(result.summary())
