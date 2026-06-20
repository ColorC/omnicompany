# [OMNI] origin=claude-code domain=services/trace_induction ts=2026-04-22T00:00:00Z type=worker
# [OMNI] material_id="material:learning.trace_induction.trace_db_reader.worker.py"
"""TraceReaderWorker — 确定性 DB 读取 (HARD, Stage 3 Clean Migration 2026-04-22)."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.anchor import Verdict, VerdictKind


class TraceReaderWorker(Worker):
    """从 intent_steps 表读取原始 trace 步骤数据。

    输入 ti.task: {purpose, trace_ids, db_path}
    输出 ti.trace-data: {traces, purpose, trace_count, domain, db_path}
    """

    FORMAT_IN = "ti.task"
    FORMAT_OUT = "ti.trace-data"
    DESCRIPTION = (
        "从 intent_steps 表确定性读取指定 trace_ids 的完整操作记录。"
        "每条记录包含 tool_name、desc、rationale、tool_args_summary、"
        "tool_result、tool_exit_ok、action_class 等字段。"
        "按 trace_id 分组、step_num 排序输出。"
    )

    def run(self, input_data: Any) -> Verdict:
        purpose = input_data.get("purpose", "")
        trace_ids = input_data.get("trace_ids", [])
        if isinstance(trace_ids, str):
            trace_ids = [t.strip() for t in trace_ids.split(",") if t.strip()]
        db_path = input_data.get("db_path", "data/intent_traces.db")
        domain = input_data.get("domain", "")

        if not purpose or not trace_ids:
            return Verdict(
                kind=VerdictKind.FAIL, output=input_data,
                diagnosis="purpose 和 trace_ids 不能为空",
            )

        from omnicompany.packages.services._learning.trace_induction.sop_extractor import read_trace_steps
        traces_raw = read_trace_steps(db_path, trace_ids)

        traces = {}
        for tid, steps in traces_raw.items():
            if steps:
                traces[tid] = [asdict(s) for s in steps]

        if not traces:
            return Verdict(
                kind=VerdictKind.FAIL, output=input_data,
                diagnosis=f"未找到 trace 数据：{trace_ids}",
            )

        return Verdict(
            kind=VerdictKind.PASS,
            output={
                "traces": traces,
                "purpose": purpose,
                "trace_count": len(traces),
                "domain": domain,
                "db_path": db_path,
            },
            diagnosis=f"读取到 {len(traces)} 个 trace，共 {sum(len(v) for v in traces.values())} 步",
            confidence=1.0,
        )
