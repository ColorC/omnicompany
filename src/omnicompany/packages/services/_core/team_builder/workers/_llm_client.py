# [OMNI] origin=claude-code domain=services/team_builder/workers ts=2026-04-23T00:00:00Z type=shim
# [OMNI] material_id="material:team_builder.workers.llm_client_shim.reexport.py"
"""shim · `call_llm_json` 提升到 omnicompany/llm_client.py 作共享层 (2026-04-23).

保留本文件避免破坏现有 `from ._llm_client import call_llm_json` import.
新代码请直接 `from omnicompany.packages.services._core.omnicompany import call_llm_json`.
"""
from omnicompany.packages.services._core.omnicompany.llm_client import call_llm_json

__all__ = ["call_llm_json"]
