# [OMNI] origin=claude-code domain=lap_auditor/run.py ts=2026-04-08T03:23:36Z
# [OMNI] material_id="material:diagnosis.lap_auditor.runtime_bindings.python"
"""lap_auditor — bindings"""

from __future__ import annotations

from omnicompany.packages.services._diagnosis.lap_auditor.routers import (
    ContextGetterRouter,
    ReportFormatterRouter,
    SpecAuditorRouter,
)
from omnicompany.runtime.llm.llm import LLMClient
from omnicompany.runtime.routing.router import Router


def build_bindings(input_dict: dict | None = None) -> dict[str, Router]:
    client = LLMClient.for_role("runtime_main", tools=[])
    return {
        "context_getter": ContextGetterRouter(),
        "spec_auditor": SpecAuditorRouter(client=client),
        "report_formatter": ReportFormatterRouter(),
    }
