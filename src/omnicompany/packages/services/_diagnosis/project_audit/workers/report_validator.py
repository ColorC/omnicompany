# [OMNI] origin=claude-code domain=services/_diagnosis/project_audit/workers ts=2026-06-19T00:00:00Z type=worker status=active
# [OMNI] summary="ReportValidatorWorker — 校验审计报告成形(real_scale + verified 存在)。HARD,紧跟 SOFT 审计做当场拦截(P-04)。"
# [OMNI] material_id="material:services._diagnosis.project_audit.workers.report_validator"
"""ReportValidatorWorker(HARD)— SOFT 审计的紧下游硬校验(team 规范 P-04)。"""
from __future__ import annotations

from typing import Any

from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.packages.services._core.omnicompany import Worker


class ReportValidatorWorker(Worker):
    """校验报告结构完整。HARD。"""

    DESCRIPTION = "校验 project_audit.report 含 project / real_scale / verified 三键且 verified 非空,作为 SOFT 审计的当场拦截。"
    FORMAT_IN = "project_audit.report"
    FORMAT_OUT = "project_audit.report"

    def run(self, input_data: Any) -> Verdict:
        rpt = input_data.get(self.FORMAT_IN, input_data) if isinstance(input_data, dict) else input_data
        if not isinstance(rpt, dict):
            return Verdict(kind=VerdictKind.FAIL, diagnosis="report 非 dict", output={})
        for k in ("project", "real_scale", "verified"):
            if k not in rpt:
                return Verdict(kind=VerdictKind.FAIL, diagnosis=f"report 缺键: {k}", output=rpt)
        if not isinstance(rpt.get("verified"), list):
            return Verdict(kind=VerdictKind.FAIL, diagnosis="verified 非 list", output=rpt)
        return Verdict(kind=VerdictKind.PASS, output=rpt)
