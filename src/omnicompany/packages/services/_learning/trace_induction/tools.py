# [OMNI] origin=claude-code domain=trace_induction/tools.py ts=2026-04-08T03:23:37Z
# [OMNI] material_id="material:learning.trace_induction.agent_tool.induce_pipeline.py"
"""Trace-induction tools exposed to agent loops."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from typing import ClassVar

from omnicompany.packages.services._core.agent.routers.single_tool import SingleToolRouter
from omnicompany.runtime.agent.agent_loop_tools import ToolContext
from omnicompany.runtime.exec.tool_executor import ToolExecutor

logger = logging.getLogger(__name__)


async def _dispatch_induction(*, purpose: str, trace_ids: str, domain: str):
    from omnicompany.core.dispatch import dispatch
    from omnicompany.core.registry import discover

    discover()
    return await dispatch(
        "trace-induction",
        {"purpose": purpose, "trace_ids": trace_ids, "domain": domain},
        max_steps=50,
    )


def _run_async_from_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


def _induce_pipeline_call(args: dict, executor: ToolExecutor | None, ctx: ToolContext) -> str:
    purpose = args.get("purpose", "")
    trace_ids_str = args.get("trace_ids", "")
    domain = args.get("domain", "")

    if not purpose or not trace_ids_str:
        return json.dumps({"status": "error", "message": "purpose and trace_ids are required"})

    try:
        result = _run_async_from_sync(
            _dispatch_induction(purpose=purpose, trace_ids=trace_ids_str, domain=domain)
        )
        if isinstance(result, dict):
            return json.dumps(
                {
                    "status": result.get("status", "unknown"),
                    "pipeline_name": result.get("pipeline_name", ""),
                    "registered": result.get("registered", False),
                    "summary": result.get("summary", ""),
                },
                ensure_ascii=False,
            )
        return json.dumps({"status": "unknown", "raw": str(result)[:500]})
    except Exception as e:
        logger.exception("induce_pipeline failed")
        return json.dumps({"status": "error", "message": str(e)})


class InducePipelineTool(SingleToolRouter):
    TOOL_NAME: ClassVar[str] = "induce_pipeline"
    DESCRIPTION: ClassVar[str] = (
        "Trigger trace induction when an agent notices it is repeating the same operation "
        "pattern. Provide the operation purpose and related trace ids; the system will "
        "derive an SOP, draft requirements, and ask Workflow Factory to create a pipeline."
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "purpose": {
                "type": "string",
                "description": "Description of the repeated operation purpose.",
            },
            "trace_ids": {
                "type": "string",
                "description": "Related trace ids, separated by commas.",
            },
            "domain": {
                "type": "string",
                "description": "Optional domain identifier.",
            },
        },
        "required": ["purpose", "trace_ids"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = False
    IS_READONLY: ClassVar[bool] = False

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        return _induce_pipeline_call(args, self._executor, ctx)
