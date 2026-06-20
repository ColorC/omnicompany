"""手动触发 lang_rewrite_verifier 对 rs_phase1 做冒烟验证 + 自动修复。

用法：
  python scripts/run_smoke_verifier.py
  python scripts/run_smoke_verifier.py --work-dir data/rewrite/rs_phase1
"""

import asyncio
import logging
import pathlib
import sys
import time

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.WARNING, format='%(message)s')

from omnicompany.packages.domains.software_engineering.lang_rewrite_verifier.pipeline import build_pipeline
from omnicompany.packages.domains.software_engineering.lang_rewrite_verifier.run import build_bindings
from omnicompany.runtime.exec.runner import PipelineRunner
from omnicompany.bus.memory import MemoryBus

# ── 参数解析 ──────────────────────────────────────────────────────────────────

args = sys.argv[1:]
work_dir_override = None
for i, a in enumerate(args):
    if a == "--work-dir" and i + 1 < len(args):
        work_dir_override = args[i + 1]

RS_DIR = pathlib.Path(work_dir_override or "data/rewrite/rs_phase1").resolve()

print(f"=== LangRewrite Smoke Verifier ===")
print(f"Rust project: {RS_DIR}")
print()

# ── 构建管线 ──────────────────────────────────────────────────────────────────

pipeline = build_pipeline()
bindings = build_bindings({"model": None})

print(f"Pipeline nodes ({len(pipeline.nodes)}): {[n.id for n in pipeline.nodes]}")
print()

# ── 运行 ──────────────────────────────────────────────────────────────────────

async def main():
    t0 = time.time()
    bus = MemoryBus()
    runner = PipelineRunner(
        pipeline=pipeline,
        bindings=bindings,
        bus=bus,
        max_steps=60,
    )

    result = await runner.run({
        "work_dir":   str(RS_DIR),
        "rs_dir":     str(RS_DIR),
        "target_lang": "rust",
    })

    elapsed = time.time() - t0
    print()
    print(f"{'=' * 55}")
    print(f"Elapsed: {elapsed:.1f}s")

    if result is None:
        print("❌  管线无结果（可能 HALT）")
        return

    verdict = result.get("smoke_passed")
    if verdict:
        passed = result.get("passed_cases", [])
        print(f"[PASS]  冒烟测试全部通过: {passed}")
    else:
        print(f"[FAIL]  未能通过冒烟测试")
        diagnosis = result.get("diagnosis") or result.get("error_text", "")
        print(f"    {str(diagnosis)[:400]}")

asyncio.run(main())
