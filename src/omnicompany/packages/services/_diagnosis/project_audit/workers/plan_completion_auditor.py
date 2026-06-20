# [OMNI] origin=claude-code domain=services/_diagnosis/project_audit/workers ts=2026-06-20T00:00:00Z type=worker status=active
# [OMNI] summary="PlanCompletionAuditorWorker — 据真源(我的原始prompt + 真实代码内容 + 文件树)逐条计划项独立判断做没做完。严禁采信复选框。SOFT。"
# [OMNI] material_id="material:services._diagnosis.project_audit.workers.plan_completion_auditor"
"""PlanCompletionAuditorWorker(SOFT)。

核心铁律(信任层级):**不采信计划文档自己的复选框**。判断只依据三类真源:
- A 类:我亲口给 agent 的原始 prompt(PromptHarvester 采)—— 证明"我到底要做什么"。
- B 类:agent 真写下的代码内容(CodeReader 真读)—— 证明"到底做出了什么"。
- 文件树:全量枚举(TreeEnumerator)—— 证明"存在哪些文件"。
逐条计划项独立判断 done/partial/not_done/uncertain。LLM 不可用时兜底标 uncertain,
绝不静默当成 done,也不让 team 崩。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.packages.services._core.omnicompany import Worker

_ITEM_RE = re.compile(r'^\s*[-*]\s*\[([ xX])\]\s*(.+)$', re.M)


class PlanCompletionAuditorWorker(Worker):
    """逐项核对计划完成度。SOFT(LLM 判断,失败兜底)。"""

    DESCRIPTION = (
        "读项目全部计划文档的每条 checklist;把'我的原始 prompt + 真实代码内容 + 文件树'作为证据喂 LLM,"
        "逐项独立判断 done/partial/not_done/uncertain 并要证据——严禁采信复选框。"
    )
    FORMAT_IN = "project_audit.enriched"
    FORMAT_OUT = "project_audit.report"

    def run(self, input_data: Any) -> Verdict:
        enr = input_data.get(self.FORMAT_IN, input_data) if isinstance(input_data, dict) else input_data
        if not isinstance(enr, dict) or not enr.get("root"):
            return Verdict(kind=VerdictKind.FAIL, diagnosis="enriched 无效", output={})
        rootp = Path(enr["root"])
        all_paths = enr.get("all_paths", [])
        plan_files = enr.get("plan_files", [])
        target = enr.get("target", {}) or {}
        max_plans = int(target.get("max_plans") or 12)

        prompts = enr.get("prompts", []) or []
        code = enr.get("code", []) or []

        # 1) 抽每个计划的 checklist 项
        plans: list[dict] = []
        for pf in plan_files:
            try:
                text = (rootp / pf).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            items = [
                {"raw": m.group(2).strip()[:240], "claimed": "done" if m.group(1).lower() == "x" else "open"}
                for m in _ITEM_RE.finditer(text)
            ]
            if items:
                plans.append({"plan_file": pf, "items": items})

        skipped: list[str] = []
        if len(plans) > max_plans:
            skipped = [p["plan_file"] for p in plans[max_plans:]]
            plans = plans[:max_plans]

        # 2) 组装三类证据摘要(prompt 意图 + 真实代码内容 + 路径)
        prompt_digest = "\n".join(f"· {p['text'][:300]}" for p in prompts[:40]) or "(未采到相关原始 prompt)"
        code_digest = "\n\n".join(
            f"### {c['path']} ({c['bytes']}B)\n{c['head'][:1500]}" for c in code[:18]
        ) or "(未读到代码内容)"
        tree_digest = "\n".join(all_paths[:1200])

        verified: list[dict] = []
        llm_ok = False

        def _fallback(reason: str):
            for p in plans:
                for it in p["items"]:
                    verified.append({
                        "plan_file": p["plan_file"], "item": it["raw"], "claimed": it["claimed"],
                        "verdict": "uncertain", "evidence": "(未独立核对)", "note": reason,
                    })

        try:
            from omnicompany.runtime.llm.llm import LLMClient, _extract_response_text
            client = LLMClient.for_role("runtime_main")
            for p in plans:
                prompt = (
                    "你在审计一个项目某计划的真实完成情况,服务于诚实的作品集。\n"
                    "**信任层级铁律:严禁采信复选框([x]/[ ])。只依据下面三类真源判断:**\n"
                    "【A·我的原始 prompt(我到底要做什么)】\n"
                    f"{prompt_digest[:3500]}\n\n"
                    "【B·真实代码内容节选(到底做出了什么)】\n"
                    f"{code_digest[:7000]}\n\n"
                    "【C·文件树(存在哪些文件)】\n"
                    f"{tree_digest[:4000]}\n\n"
                    f"待判定计划:{p['plan_file']}\n"
                    "对每条计划项,据上面真源判断是否做完。只输出 JSON 数组,元素 "
                    '{"item":"原文","claimed":"done|open","verdict":"done|partial|not_done|uncertain",'
                    '"evidence":"指向的真实文件/代码/prompt 或\'无\'","note":"一句话理由(据真源)"}。\n'
                    f"计划项:\n{json.dumps(p['items'], ensure_ascii=False)}"
                )
                try:
                    resp = client.call(messages=[{"role": "user", "content": prompt}])
                    txt = _extract_response_text(resp)
                    arr = json.loads(txt[txt.find("["): txt.rfind("]") + 1])
                    for a in arr:
                        if isinstance(a, dict):
                            a["plan_file"] = p["plan_file"]
                            verified.append(a)
                    llm_ok = True
                except Exception as e:
                    for it in p["items"]:
                        verified.append({
                            "plan_file": p["plan_file"], "item": it["raw"], "claimed": it["claimed"],
                            "verdict": "uncertain", "evidence": "(LLM 判定失败)", "note": str(e)[:100],
                        })
        except Exception as e:
            _fallback(f"LLM 不可用: {str(e)[:100]}")

        mismatches = [v for v in verified if v.get("claimed") == "done" and v.get("verdict") in ("not_done", "partial")]
        report = {
            "project": target.get("name") or str(rootp),
            "root": str(rootp),
            "real_scale": {
                "total_files": enr.get("total_files"),
                "by_top_dir": enr.get("by_top_dir"),
                "by_ext": dict(list((enr.get("by_ext") or {}).items())[:12]),
                "loc_by_lang": (enr.get("code_meta") or {}).get("loc_by_lang"),
            },
            "evidence_base": {
                "prompts_harvested": (enr.get("prompt_meta") or {}).get("kept"),
                "prompt_meta": enr.get("prompt_meta"),
                "code_files_read": (enr.get("code_meta") or {}).get("files_read"),
                "code_meta": enr.get("code_meta"),
            },
            "prompts": prompts,
            "code": code,
            "verified": verified,
            "skipped": skipped,
            "summary": (
                f"枚举 {enr.get('total_files')} 个文件;采到我的原始 prompt {(enr.get('prompt_meta') or {}).get('kept')} 条、"
                f"真读代码 {(enr.get('code_meta') or {}).get('files_read')} 个文件内容;"
                f"审计 {len(plans)} 个计划、共 {len(verified)} 条计划项;"
                f"{'LLM 据真源独立核对完成' if llm_ok else '⚠ 未能 LLM 核对,多数标 uncertain(需修 LLM 调用)'};"
                f"发现 {len(mismatches)} 条'宣称已做但真源证据不足';略过 {len(skipped)} 个超额计划。"
            ),
        }
        return Verdict(
            kind=VerdictKind.PASS if verified else VerdictKind.PARTIAL,
            output=report,
            diagnosis=None if verified else "项目无可审计的计划项(仅采到 prompt/代码,无 checklist)",
        )
