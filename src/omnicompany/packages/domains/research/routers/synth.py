# [OMNI] origin=ai-ide domain=research/routers ts=2026-06-14T00:00:00Z type=router status=active
# [OMNI] summary="Synthesize(接地带引用综合) + ClaimVerify(对抗式逐条核源)。"
# [OMNI] why="对齐 SOTA: open_deep_research 的引用接地 + anthropic 的 CitationAgent 逐条挂源。综合走便宜档,核源走中端逐条抓原始来源判 supported/unsupported(并行)。"
# [OMNI] tags=research,router,synthesize,verify,citation,sota
"""Synthesize + ClaimVerify。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.runtime.routing.router import Router

from .. import prompts
from .._llm import safe_json
from ..sources.web import web_fetch

_VERIFY_CAP = 10  # 核源逐条抓源费时, 封顶最关键的前 N 条(token/时间硬闸)


class Synthesize(Router):
    """把各子研究的带来源发现综合成接地、带引用、不打分的结论。"""

    DESCRIPTION = "综合: 据带来源发现产接地带引用结论(便宜档,失败降级)"
    FORMAT_IN = "research.gathered"
    FORMAT_OUT = "research.synthesis"
    REQUIRED_CONTEXT = ["topic", "run_dir"]

    def run(self, input_data: Any) -> Verdict:
        ctx = input_data if isinstance(input_data, dict) else {}
        topic = ctx["topic"]
        run_dir = Path(ctx["run_dir"])
        findings = ctx.get("findings") or []
        sources = ctx.get("sources") or []
        coverage = ctx.get("coverage") or {}

        synth: dict[str, Any] = {"summary": "", "findings": [], "keywords": [], "aliases": [],
                                 "perspectives_open": []}
        synth_ok = False
        if findings:
            res = safe_json(
                prompts.SYNTH_SYSTEM,
                {"topic": topic,
                 "findings": [{"claim": f.get("claim", ""), "source_url": f.get("source_url", "")}
                              for f in findings][:60],
                 "covered": coverage.get("covered", []), "open": coverage.get("open", [])},
                prompts.SYNTH_SCHEMA, caller="research.synthesize", max_tokens=4000, default=None,
            )
            if res:
                synth = res
                synth_ok = True
        if not synth_ok and not synth.get("summary"):
            synth["summary"] = ("(综合失败/无发现,已存原始过程待复跑)" if findings
                                else "(本轮未收集到发现;可能限流/网络,或题目过窄)")

        # 覆盖账本里没探到的角度并进 perspectives_open(去重)
        open_p = list(dict.fromkeys((synth.get("perspectives_open") or []) + (coverage.get("open") or [])))
        synth["perspectives_open"] = [p for p in open_p if p]

        (run_dir / "synthesis.json").write_text(
            json.dumps({"synth": synth, "synth_ok": synth_ok}, ensure_ascii=False, indent=2),
            encoding="utf-8")

        return Verdict(
            kind=VerdictKind.PASS,
            output={
                "topic": topic, "topic_norm": ctx["topic_norm"], "run_dir": str(run_dir),
                "synthesis": synth, "sources": sources, "coverage": coverage,
                "existing": ctx.get("existing"), "synth_ok": synth_ok,
            },
            diagnosis=f"综合{'成功' if synth_ok else '降级'}: {len(synth.get('findings') or [])} 条发现",
            granted_tags=["domain.research", "stage.synthesized"],
        )


class ClaimVerify(Router):
    """对抗式核源: 逐条 finding 抓它声称的来源页,判 supported/partial/unsupported,写回 support。"""

    DESCRIPTION = "核源: 逐条断言抓原始来源判 supported/unsupported(中端,并行)"
    FORMAT_IN = "research.synthesis"
    FORMAT_OUT = "research.verified"
    REQUIRED_CONTEXT = ["topic", "run_dir"]

    def run(self, input_data: Any) -> Verdict:
        from omnicompany.runtime.llm.batch import run_parallel_items

        ctx = input_data if isinstance(input_data, dict) else {}
        run_dir = Path(ctx["run_dir"])
        synth = ctx.get("synthesis") or {}
        findings = synth.get("findings") or []

        # 只核有来源的;封顶前 N 条(硬闸)。超上限的带源 finding **显式标 unverified**,
        # 绝不留空(留空会在报告里和 supported 一样"干净",伪装成已核可信)。
        src_findings = [(i, f) for i, f in enumerate(findings) if f.get("source_url")]
        to_verify = src_findings[:_VERIFY_CAP]
        skipped = src_findings[_VERIFY_CAP:]
        for i, _f in skipped:
            findings[i]["support"] = "unverified"
            findings[i]["support_note"] = f"超核源上限({_VERIFY_CAP})未核"

        def _verify(pair: tuple[int, dict]) -> dict:
            i, f = pair
            page = web_fetch(f["source_url"], max_chars=5000)
            if not page:
                return {"i": i, "support": "unverified", "note": "来源抓取失败,未能核验"}
            v = safe_json(
                prompts.VERIFY_SYSTEM,
                {"claim": f.get("claim", ""), "source_url": f["source_url"], "page": page[:4500]},
                prompts.VERIFY_SCHEMA, model=prompts.MID_MODEL, caller="research.verify",
                max_tokens=400, default=None,
            )
            if v is None:  # 核验调用失败(限流/超时)≠ 无支撑:标 unverified 保守,别给未挣得的判定
                return {"i": i, "support": "unverified", "note": "核验调用失败(限流/超时)"}
            return {"i": i, "support": v.get("support", "unverified"), "note": v.get("note", "")}

        verified = 0
        if to_verify:
            res = run_parallel_items(to_verify, _verify, workers=4,
                                     status_run_id=run_dir.name, progress_label="research-verify")
            for r in res.results:
                idx = r["i"]
                if 0 <= idx < len(findings):
                    findings[idx]["support"] = r["support"]
                    if r.get("note"):
                        findings[idx]["support_note"] = r["note"]
                    verified += 1

        synth["findings"] = findings
        n_unsup = sum(1 for f in findings if f.get("support") == "unsupported")
        n_unverified = sum(1 for f in findings if f.get("support") == "unverified")
        (run_dir / "verified.json").write_text(
            json.dumps(synth, ensure_ascii=False, indent=2), encoding="utf-8")

        diag = f"核源 {verified} 条 · {n_unsup} 条无来源支撑"
        if n_unverified:
            diag += f" · {n_unverified} 条未核(超上限/抓取或核验失败,已标 unverified)"
        return Verdict(
            kind=VerdictKind.PASS,
            output={
                "topic": ctx["topic"], "topic_norm": ctx["topic_norm"], "run_dir": str(run_dir),
                "synthesis": synth, "sources": ctx.get("sources") or [],
                "coverage": ctx.get("coverage") or {}, "existing": ctx.get("existing"),
            },
            diagnosis=diag,
            granted_tags=["domain.research", "stage.verified"],
        )
