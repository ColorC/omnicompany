"""test_workflow_factory_voxel_engine — 直接调用 workflow-factory 管线生成 voxel_engine 包

绕过 CLI 挂起问题，用 Python 直接驱动 PipelineRunner。
同时评估 workflow-factory 元管线的生成能力。
"""

import asyncio
import sys
import os
import logging

# 确保项目根在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("test_wf_voxel_engine")


voxel_engine_REQUIREMENT = (
    "Create a voxel_sandbox game development studio pipeline called 'voxel_engine'. "
    "Namespace: packages/domains/voxel_engine/. "
    "The pipeline has 5 nodes:\n"
    "1. design_parser (SOFT): Accept a game design specification (spec.gdd) "
    "describing a new game mechanic. Parse it into structured code requirements.\n"
    "2. engineer (SOFT): Generate Java engine_mod source code based on the parsed requirements. "
    "Uses LLM. On information insufficiency, can query local codebase mappings.\n"
    "3. compiler_qa (HARD): Run 'gradlew build' in the target workspace directory "
    "and capture compilation results. On FAIL, send error trace back to engineer node.\n"
    "4. paper_model_critic (SOFT): Evaluate game balance and fun factor by simulating "
    "numeric encounters in-memory (no 3D rendering). Output a critique report. "
    "On FAIL (bad design detected), reject upstream and route back to design_parser.\n"
    "5. release_gate (HARD): Final check - all tests passing, all critiques resolved. EMIT result.\n"
    "Key feedback loops: compiler_qa FAIL -> engineer (retry code), "
    "paper_model_critic FAIL -> design_parser (reject design)."
)


async def run_workflow_factory():
    """直接用 Python API 驱动 workflow-factory 管线。"""
    from dotenv import load_dotenv
    load_dotenv()

    # 1. 注册所有管线
    from omnicompany.core.pipelines import register_all
    register_all()

    # 2. 获取 workflow-factory 的 PipelineSpec 和 Bindings
    from omnicompany.packages.services.workflow_factory.pipeline import build_pipeline
    from omnicompany.packages.services.workflow_factory.run import build_bindings

    pipeline = build_pipeline()
    bindings = build_bindings()

    logger.info("Pipeline: %s (%d nodes)", pipeline.name, len(pipeline.nodes))
    logger.info("Bindings: %s", list(bindings.keys()))

    # 3. 验证 bindings 完整性
    node_ids = {n.id for n in pipeline.nodes}
    binding_ids = set(bindings.keys())
    missing = node_ids - binding_ids
    extra = binding_ids - node_ids
    if missing or extra:
        logger.error("Bindings mismatch! Missing: %s, Extra: %s", missing, extra)
        return

    # 4. 构造输入
    input_data = {"text": voxel_engine_REQUIREMENT}

    # 5. 驱动管线
    from omnicompany.bus.sqlite import SQLiteBus
    from omnicompany.runtime.exec.runner import PipelineRunner

    db_dir = os.path.join(os.path.dirname(__file__), "..", "data", "workflow_factory")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "events.db")

    async with SQLiteBus(db_path) as bus:
        runner = PipelineRunner(pipeline, bindings, bus, max_steps=50)
        logger.info("=== Starting workflow-factory pipeline ===")
        result = await runner.run(input_data)
        logger.info("=== Pipeline finished ===")
        logger.info("Final result type: %s", type(result))
        if isinstance(result, dict):
            for k, v in result.items():
                preview = str(v)[:200] if v else "None"
                logger.info("  %s: %s", k, preview)
        else:
            logger.info("Result: %s", str(result)[:500])

    return result


if __name__ == "__main__":
    result = asyncio.run(run_workflow_factory())
