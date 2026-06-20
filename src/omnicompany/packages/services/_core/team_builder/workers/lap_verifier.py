# [OMNI] origin=claude-code domain=omnicompany/workflow_factory ts=2026-04-20T00:00:00Z type=worker
# [OMNI] material_id="material:team_builder.workers.lap_compliance_auditor.worker.py"
"""LAPVerifierWorker — workflow_factory Team Worker (Clean Migration 2026-04-20).

Worker 协议:
  FORMAT_IN  = wf.project_skeleton
  FORMAT_OUT = wf.project_skeleton

职责: LAP 合规审计 (HARD, 确定性 AST 分析). 多维度:
  D1 Format 规范性, D2 Router 规范性, D3 拓扑完整性, D4 Format 链健康度,
  D5 info_audit 覆盖度, D6 Format description 五项语义, D7 skeleton 克隆链检测,
  D8 SOFT 节点 output_token_budget, D9 F-15/P-13 声明即消费 (M2.α).
报告写进 reports['lap_audit'], PASS 贴 lap-audit-passed tag.
"""
from __future__ import annotations

from omnicompany.packages.services._core.omnicompany import Worker
from .._archive.routers_legacy import LAPVerifierRouter as _Legacy


class LAPVerifierWorker(Worker, _Legacy):
    """LAP 合规审计 (D1-D9 多维度静态分析), score < 70 或 critical issue 即 FAIL."""
    pass
