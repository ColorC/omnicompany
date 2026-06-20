# [OMNI] origin=claude-code domain=services/_governance/work_history ts=2026-06-12T12:00:00Z type=config
# [OMNI] material_id="material:governance.work_history.package_init.py"
"""work_history — 工作历史整理部门(原进化部门重组, evolution_v1 已入 _graveyard)。

用户原话(2026-06-12): "建立一个我的工作历史整理部门…工作中心转移至使用便宜模型 review
我的 claude code 和 codex 对话历史，以及各自的 memory，整理出用户的重复需求和重复指正
内容"。直接动因: AI 在 PROJECT_INDEX 里捏造了"常用工作选项"——常用与否必须有历史证据。
"""

from .miner import run_mining, latest_findings

__all__ = ["run_mining", "latest_findings"]
