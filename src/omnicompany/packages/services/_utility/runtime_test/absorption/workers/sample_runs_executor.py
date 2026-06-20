# [OMNI] origin=claude-code domain=services/absorption_runtime_test/workers ts=2026-04-26T00:00:00Z type=worker
# [OMNI] material_id="material:utility.runtime_test.absorption.sample_runs_executor.subprocess.py"
"""SampleRunsExecutorWorker — Worker #2 (HARD).

真跑目标团队 N 次取样. 用 subprocess 隔离避嵌套 dispatch async loop 冲突.
失败的跑也保留 (verdict=FAIL), 验证器据此可判稳定性.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.anchor import Verdict, VerdictKind

logger = logging.getLogger(__name__)


_PROJECT_ROOT = Path(__file__).resolve().parents[6]


_DISPATCH_RUNNER_SCRIPT = """
import os, sys, json, asyncio
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

target_id = sys.argv[1]
input_path = sys.argv[2]
output_path = sys.argv[3]
max_steps = int(sys.argv[4]) if len(sys.argv) > 4 else 1000

with open(input_path, "r", encoding="utf-8") as f:
    input_data = json.load(f)

from omnicompany.core.dispatch import dispatch
from omnicompany.core.registry import discover
discover()

result = asyncio.run(dispatch(target_id, input_data, max_steps=max_steps))

verdict = "FAIL"
output = {}
diag = ""
if hasattr(result, "kind"):
    verdict = result.kind.value.upper() if hasattr(result.kind, "value") else str(result.kind).upper()
    if hasattr(result, "output") and isinstance(result.output, dict):
        output = result.output
    if hasattr(result, "diagnosis") and result.diagnosis:
        diag = result.diagnosis
elif isinstance(result, dict):
    output = result
    verdict = "PASS"

with open(output_path, "w", encoding="utf-8") as f:
    json.dump({"verdict": verdict, "output": output, "diagnosis": diag}, f, ensure_ascii=False)
"""


def _run_target_subprocess(
    target_team_id: str,
    input_data: dict,
    timeout_sec: int = 1800,
) -> dict:
    """跑一次目标团队 dispatch · 子进程 · 返 verdict/output/elapsed."""
    t0 = datetime.now()

    # 写 input
    with tempfile.NamedTemporaryFile(
        mode="w", suffix="_in.json", delete=False, encoding="utf-8"
    ) as tin:
        json.dump(input_data, tin, ensure_ascii=False)
        in_path = tin.name
    out_path = in_path.replace("_in.json", "_out.json")

    # 写 runner 脚本
    with tempfile.NamedTemporaryFile(
        mode="w", suffix="_runner.py", delete=False, encoding="utf-8"
    ) as tscript:
        tscript.write(_DISPATCH_RUNNER_SCRIPT)
        script_path = tscript.name

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(_PROJECT_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    )

    cmd = [sys.executable, script_path, target_team_id, in_path, out_path, "1000"]

    elapsed = 0.0
    verdict = "FAIL"
    output: dict = {}
    diag = ""

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(_PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            encoding="utf-8",
            errors="replace",
        )
        elapsed = (datetime.now() - t0).total_seconds()
        if Path(out_path).is_file():
            try:
                with open(out_path, "r", encoding="utf-8") as f:
                    parsed = json.load(f)
                if isinstance(parsed, dict):
                    verdict = parsed.get("verdict", "FAIL")
                    output = parsed.get("output", {}) or {}
                    diag = parsed.get("diagnosis", "")
            except Exception as e:
                diag = f"输出 JSON 解析失败: {type(e).__name__}: {e}"
        else:
            diag = f"子进程未产输出文件 (rc={proc.returncode}; stderr 末段: {(proc.stderr or '')[-500:]})"
    except subprocess.TimeoutExpired:
        elapsed = timeout_sec
        diag = f"子进程超时 ({timeout_sec}s)"
    finally:
        for p in (in_path, out_path, script_path):
            try:
                os.unlink(p)
            except OSError:
                pass

    return {
        "verdict": verdict,
        "output": output,
        "elapsed_sec": elapsed,
        "diagnosis": diag,
    }


class SampleRunsExecutorWorker(Worker):
    DESCRIPTION = (
        "真跑目标团队 N 次取样 · subprocess 隔离避嵌套 dispatch async loop 冲突 · 收齐 N 条含失败."
    )
    FORMAT_IN = "absorption_runtime_test.target_metadata"
    FORMAT_OUT = "absorption_runtime_test.sample_runs"

    def run(self, input_data: dict[str, Any]) -> Verdict:
        target_team_id = input_data.get("target_team_id")
        sample_input = input_data.get("sample_input")
        run_count = input_data.get("run_count", 2)

        if not target_team_id:
            return Verdict(kind=VerdictKind.FAIL, diagnosis="缺 target_team_id")
        if not isinstance(sample_input, dict):
            return Verdict(kind=VerdictKind.FAIL, diagnosis="缺 sample_input")
        if not isinstance(run_count, int) or run_count < 2:
            run_count = 2

        runs: list[dict] = []
        successful = 0
        for i in range(run_count):
            logger.info(
                "[SampleRunsExecutor] run %d/%d for %s", i + 1, run_count, target_team_id
            )
            result = _run_target_subprocess(target_team_id, sample_input)
            runs.append({
                "run_id": i + 1,
                "verdict": result["verdict"],
                "output": result["output"],
                "elapsed_sec": result["elapsed_sec"],
                "diagnosis": result["diagnosis"],
            })
            if result["verdict"] in ("PASS", "PARTIAL"):
                successful += 1

        if successful == 0:
            return Verdict(
                kind=VerdictKind.FAIL,
                output={
                    "target_team_id": target_team_id,
                    "runs": runs,
                    "successful_count": 0,
                    "total_count": run_count,
                },
                diagnosis=f"全部 {run_count} 次跑都失败, 没法做后续验证",
            )

        kind = VerdictKind.PASS if successful == run_count else VerdictKind.PARTIAL
        return Verdict(
            kind=kind,
            output={
                "target_team_id": target_team_id,
                "runs": runs,
                "successful_count": successful,
                "total_count": run_count,
            },
            diagnosis=f"取样完成: {successful}/{run_count} 次成功",
            confidence=1.0,
        )
