"""测试 evolution workflow 对 lang_rewrite 管线错误的诊断能力

直接构造 QualityPainSignal（R-06 场景：client.rs cargo check 失败），
触发 B.1~B.5 进化工作流看看能诊断出什么。

不重跑管线——避免 AgentFixer 在 redis 问题上无限循环。
"""

import asyncio
import logging
import pathlib
import sys

sys.path.insert(0, "src")
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("test_evo_rewrite")

from omnicompany.packages.services._core.evolution.workflow.orchestrator import EvolutionOrchestrator
from omnicompany.packages.services._core.evolution.workflow.hypothesis_store import HypothesisBoardStore
from omnicompany.packages.services._core.evolution.workflow.pain_signal import QualityPainSignal

RS_DIR = pathlib.Path("data/rewrite/rs_phase1")
BUS_DB = "data/rewrite/rs_phase1/lang_rewrite_events.db"
BOARD_STORE_DB = "data/rewrite/rs_phase1/evolution_boards.db"

# 从上次 test_evolution 运行中记录的 trace_id（事件在 lang_rewrite_events.db）
KNOWN_TRACE_ID = "01KNEE8V516NWTKZJKXB25B13P"

# 读取 client.rs 当前内容作为输出摘要（给 DiagnosisAgent 看）
_client_rs = RS_DIR / "src" / "client.rs"
_client_rs_snippet = ""
if _client_rs.exists():
    content = _client_rs.read_text(encoding="utf-8")
    # 只取前 60 行（问题的 use 语句在开头）
    lines = content.splitlines()[:60]
    _client_rs_snippet = "\n".join(lines)


async def main():
    logger.info("=== 构造 R-06 QualityPainSignal → 触发进化工作流 ===")

    pain = QualityPainSignal(
        trace_id=KNOWN_TRACE_ID,
        pipeline_id="lang_rewrite",
        failing_node_id="type_checker",
        quality_verdict=(
            "cargo check 失败：client.rs 使用了 redis crate 但 Cargo.toml 中未声明依赖。"
            "AgentFixer 只能修改 .rs 文件，无法修改 Cargo.toml，"
            "导致 agent_fixer 在错误上停滞（无效迭代直到 max_steps 耗尽）。"
            "这是 AgentFixer 行动空间的结构性盲区——缺少构建配置修改能力（R-06）。"
        ),
        expected_format="rewrite.checked-code",
        actual_output_summary=(
            "=== cargo check 错误摘要 ===\n"
            "error[E0433]: failed to resolve: use of unresolved module or unlinked crate `redis`\n"
            "error[E0432]: unresolved import `redis`\n"
            "error[E0282]: type annotations needed\n"
            "共 18 个编译错误，全部源于 `redis` crate 在 Cargo.toml [dependencies] 中未声明。\n\n"
            "=== client.rs 开头（触发错误的 use 语句）===\n"
            f"{_client_rs_snippet}\n\n"
            "=== Cargo.toml [dependencies] 现状 ===\n"
            "tokio = { version = \"1\", features = [\"full\"] }\n"
            "serde = { version = \"1\", features = [\"derive\"] }\n"
            "serde_json = \"1\"\n"
            "rusqlite = { version = \"0.31\", features = [\"bundled\"] }\n"
            "uuid = { version = \"1\", features = [\"v7\"] }\n"
            "# 注意：redis 未声明！\n\n"
            "=== AgentFixer 行为记录 ===\n"
            "round 1: 77 行错误 → 代码修改后仍有 77 行错误\n"
            "round 2: 75 行错误 → 修改后仍有 75 行错误（错误数停滞）\n"
            "round 3: 81 行错误 → 修改后错误数反而增加\n"
            "结论：AgentFixer 无法解决 redis crate 未声明问题——它只能修改 .rs 文件不能修改 Cargo.toml"
        ),
        severity="hard",
        bus_path=BUS_DB,
        pipeline_input={
            "source_path": "src/omnicompany/bus/client.py",
            "target_lang": "rust",
        },
    )

    store = HypothesisBoardStore(BOARD_STORE_DB)

    orch = EvolutionOrchestrator(
        store=store,
        bus_path=BUS_DB,
        max_cycles=3,
    )

    import time
    t0 = time.time()
    try:
        result = await orch.run(pain)
        elapsed = time.time() - t0

        logger.info("进化工作流完成: %.0fs", elapsed)
        print("\n" + "=" * 60)
        print("EVOLUTION RESULT")
        print("=" * 60)
        print(result.summary())
        print(f"\nStatus: {result.final_status}")
        print(f"Cycles: {result.cycles}")

        if result.diagnosis_reports:
            print(f"\n--- Diagnosis Reports ({len(result.diagnosis_reports)}) ---")
            for i, dr in enumerate(result.diagnosis_reports, 1):
                print(f"\n[{i}] root_cause_node: {dr.root_cause_node}")
                print(f"    error_category: {dr.error_category}")
                print(f"    explanation: {dr.root_cause_explanation[:400]}")
                if dr.proposed_changes:
                    pc = dr.proposed_changes[0]
                    print(f"    proposed_change: [{pc.change_type}] {pc.target_node}")
                    print(f"      → {pc.change_description[:200]}")

        if result.experiment_results:
            print(f"\n--- Experiment Results ({len(result.experiment_results)}) ---")
            for i, exp in enumerate(result.experiment_results, 1):
                an = result.analysis_results[i - 1] if i <= len(result.analysis_results) else None
                print(f"[{i}] target={exp.proposed_change.target_node} verdict={an.verdict if an else '?'}")

    except Exception as e:
        logger.error("进化工作流失败: %s", e, exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
