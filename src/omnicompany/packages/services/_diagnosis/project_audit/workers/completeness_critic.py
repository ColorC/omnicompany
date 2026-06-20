# [OMNI] origin=claude-code domain=services/_diagnosis/project_audit/workers ts=2026-06-20T00:00:00Z type=worker status=active
# [OMNI] summary="CompletenessCritic — 完整性临界(plan §四):每个 owned 项目是否都有到-bar 的页、皆全貌非抽样、内容可追溯到真源;不全 FAIL 打回。"
# [OMNI] material_id="material:services._diagnosis.project_audit.workers.completeness_critic"
"""CompletenessCritic(HARD)。

堵死"写太短就结束"(上一版我写到实际内容 1% 就收手)。逐项核对:
1. 每个 owned 项目都有报告 + 页(缺一 FAIL)。
2. 页内容达-bar:正文字数过门槛、有图或可玩 demo、可追溯到真源(报告里有 prompt/代码证据)。
3. 不静默放过:任何缺失明确列入 missing 并指出打回哪里。
确定性规则判断(HARD),不依赖 LLM —— 完整性是可数的,不该靠"感觉够了"。
"""
from __future__ import annotations

from typing import Any

from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.packages.services._core.omnicompany import Worker


class CompletenessCritic(Worker):
    """完整性临界。HARD,确定性规则。"""

    DESCRIPTION = (
        "核对每个 owned 项目是否都有到-bar 的作品页(有报告+有页+正文够长+有图/demo+可追溯真源);"
        "缺一即 FAIL 并列出 missing 与打回点——堵死'抽样/写太短就收手'。"
    )
    FORMAT_IN = "project_audit.completeness_seed"
    FORMAT_OUT = "project_audit.completeness"

    def run(self, input_data: Any) -> Verdict:
        seed = input_data.get(self.FORMAT_IN, input_data) if isinstance(input_data, dict) else input_data
        if not isinstance(seed, dict):
            return Verdict(kind=VerdictKind.FAIL, diagnosis="completeness_seed 非 dict", output={})

        owned = list(seed.get("owned_projects") or [])
        reports = seed.get("reports") or {}
        pages = seed.get("pages") or {}
        bar = int(seed.get("bar_min_chars") or 1500)

        if not owned:
            return Verdict(kind=VerdictKind.FAIL, diagnosis="owned_projects 为空,无从判断完整性",
                           output={"pass": False, "covered": [], "missing": [],
                                   "summary": "未提供应覆盖的项目清单(先跑 ProjectDiscoverer)"})

        covered: list[str] = []
        missing: list[dict] = []
        for proj in owned:
            rpt = reports.get(proj)
            pg = pages.get(proj)
            problems = []
            if not rpt:
                problems.append("无 project_audit 真源报告(未遍历核实)")
            else:
                eb = (rpt.get("evidence_base") or {}) if isinstance(rpt, dict) else {}
                if not eb.get("prompts_harvested") and not (rpt.get("prompts") if isinstance(rpt, dict) else None):
                    problems.append("报告未采到原始 prompt(A 类真源缺失)")
                if not eb.get("code_files_read"):
                    problems.append("报告未读代码内容(B 类真源缺失)")
            if not pg:
                problems.append("无作品页")
            else:
                if (pg.get("chars") or 0) < bar:
                    problems.append(f"页正文仅 {pg.get('chars')} 字 < {bar} 门槛(疑抽样/写太短)")
                if not pg.get("has_image") and not pg.get("has_demo"):
                    problems.append("无真实图也无可玩 demo")
                if pg.get("traceable") is False:
                    problems.append("页内容无法追溯到真源(疑二手/夸大)")
            if problems:
                missing.append({"project": proj, "reason": "; ".join(problems)})
            else:
                covered.append(proj)

        ok = not missing
        summary = (
            f"应覆盖 owned 项目 {len(owned)} 个;到-bar 覆盖 {len(covered)} 个;"
            f"缺/不达标 {len(missing)} 个。"
            + ("✅ 完整性达标:全覆盖、皆有真源报告+到-bar 页。"
               if ok else
               "❌ 未达标,打回:" + "; ".join(f"[{m['project']}]{m['reason']}" for m in missing))
        )
        return Verdict(
            kind=VerdictKind.PASS if ok else VerdictKind.FAIL,
            output={"pass": ok, "covered": covered, "missing": missing, "summary": summary},
            diagnosis=None if ok else f"完整性未达标:{len(missing)} 个项目缺失/不达标",
        )
