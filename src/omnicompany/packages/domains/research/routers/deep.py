# [OMNI] origin=ai-ide domain=research/routers ts=2026-06-14T00:00:00Z type=router status=active
# [OMNI] summary="SOTA 核心两节点: Planner(先搜后拆+多视角真拆题) + Orchestrator(并行子研究+上下文隔离+反思有界迭代)。"
# [OMNI] why="对齐开源 SOTA: open_deep_research 的子图隔离 + anthropic 的编排者-工人两级并行 + STORM 多视角召回 + gpt-researcher 递归衰减。DAG 不支持循环,故迭代循环塞进 Orchestrator 节点内,用 run_parallel_items 扇出。"
# [OMNI] tags=research,router,planner,orchestrator,sota
"""Planner + Orchestrator —— 公开调研管线的 SOTA 核心。

Planner(LLM·中端): 先用原题搜一小撮背景 → 拆成互不重叠子主题(各带 goal/perspective/queries/boundary),
  视角多样含'基础覆盖'+'冷门/替代'兜底,拆几个按复杂度档位。
Orchestrator(节点内循环): for round in range(max_rounds): 并行派子研究员(run_parallel_items,各自独立局部上下文)
  → 反思看覆盖账本指缺口 + 打捞未用上的检索料 → 有缺口且未到轮上限则带衰减广度再来一轮,否则停。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.runtime.routing.router import Router

from .. import library, prompts
from .._llm import safe_json
from .._paths import DATA_ROOT
from ..sources.web import web_fetch, web_search


def _det_subtopics(topic: str) -> list[dict]:
    """planner 失败时的确定性兜底拆题(保证有子主题、管线不空跑)。

    顺序 = 重要性优先: 基础覆盖 → 冷门/替代(规格强调的防漏安全网,放第二位保证 max_subtopics≥2 时不被截掉)→ 对比选型。
    """
    return [
        {"id": "base", "goal": f"{topic} 是什么、主流方案", "perspective": "基础覆盖",
         "queries": [topic, f"{topic} 综述"], "boundary": ""},
        {"id": "niche", "goal": f"{topic} 的冷门/替代/反对方案", "perspective": "冷门与替代",
         "queries": [f"{topic} 开源 替代", f"{topic} underrated 2026"], "boundary": ""},
        {"id": "compare", "goal": f"{topic} 的可选方案对比选型", "perspective": "对比选型",
         "queries": [f"{topic} 对比 选型", f"{topic} alternatives"], "boundary": ""},
    ]


# ── 节点: 规划/拆题 ───────────────────────────────────────────────────────
class Planner(Router):
    """先搜后拆: 拿原题搜一小撮背景, 喂中端模型产互不重叠的多视角子主题。"""

    DESCRIPTION = "规划: 先搜后拆 + 多视角互不重叠子主题(中端模型)"
    FORMAT_IN = "research.intake"
    FORMAT_OUT = "research.plan"
    REQUIRED_CONTEXT = ["topic", "run_dir"]

    def run(self, input_data: Any) -> Verdict:
        ctx = input_data if isinstance(input_data, dict) else {}
        topic = ctx["topic"]
        run_dir = Path(ctx["run_dir"])
        max_subtopics = int(ctx.get("max_subtopics", 4) or 4)

        # 先搜后拆: 拿原题搜一小撮背景, 让拆题有据(避免凭空臆造子问题)
        bg = web_search(topic, num=5)
        background = [{"title": h.get("title", ""), "snippet": h.get("snippet", "")} for h in bg]

        plan = safe_json(
            prompts.PLANNER_SYSTEM,
            {"topic": topic, "background": background, "max_subtopics": max_subtopics},
            prompts.PLANNER_SCHEMA,
            model=prompts.MID_MODEL,
            caller="research.planner",
            max_tokens=2500,
            default=None,
        )
        if plan and plan.get("subtopics"):
            subtopics = plan["subtopics"][:max_subtopics]
            brief = plan.get("brief", topic)
            degraded = False
        else:
            subtopics = _det_subtopics(topic)[:max_subtopics]
            brief = topic
            degraded = True

        # 补 id(模型可能没给)
        for i, st in enumerate(subtopics):
            st.setdefault("id", f"st{i+1}")

        (run_dir / "plan.json").write_text(
            json.dumps({"brief": brief, "subtopics": subtopics, "degraded": degraded},
                       ensure_ascii=False, indent=2), encoding="utf-8")

        return Verdict(
            kind=VerdictKind.PASS,
            output={
                "topic": topic, "topic_norm": ctx["topic_norm"], "run_dir": str(run_dir),
                "brief": brief, "subtopics": subtopics, "existing": ctx.get("existing"),
                "max_rounds": int(ctx.get("max_rounds", 2) or 2),
                "max_subtopics": max_subtopics,
                "workers": int(ctx.get("workers", 4) or 4),
            },
            diagnosis=f"拆出 {len(subtopics)} 个子主题{'(兜底)' if degraded else ''}: "
                      + ", ".join(st.get("perspective", st.get("goal", ""))[:10] for st in subtopics),
            granted_tags=["domain.research", "stage.plan"],
        )


# ── 子研究员(run_parallel_items 的 worker,独立局部上下文)────────────────
def _research_subtopic(topic: str, st: dict, *, max_queries: int, fetch_top: int) -> dict:
    """一个子主题的独立研究: 多 query 搜 → 抓 top 页 → 单页摘要(第一道收缩)→ 抽带来源发现。

    返回只含'压缩发现 + 原始片段',不共享可变上下文 —— 隔离即在此(每次调用独立闭包/局部变量)。
    """
    queries = (st.get("queries") or [st.get("goal") or topic])[:max_queries]
    hits: list[dict] = []
    seen: set[str] = set()
    for q in queries:
        for h in web_search(q, num=4):
            u = (h.get("url") or "").strip()
            if u and u not in seen:
                seen.add(u)
                hits.append(h)
    raw_snippets = [{"title": h.get("title", ""), "url": h.get("url", ""),
                     "snippet": h.get("snippet", "")} for h in hits]

    docs: list[dict] = []
    for h in hits[:fetch_top]:
        text = web_fetch(h["url"])
        snapshot_path = library.save_snapshot(h["url"], text) if text else None  # 源原文落本地快照
        summary = (h.get("snippet") or "")[:600]
        if text and len(text) > 800:
            s = safe_json(
                prompts.PAGE_SUMMARY_SYSTEM,
                {"goal": st.get("goal", topic), "url": h["url"], "text": text[:6000]},
                prompts.PAGE_SUMMARY_SCHEMA, caller="research.summarize", max_tokens=600,
                default=None,
            )
            if s and s.get("summary"):
                summary = s["summary"]
        elif text:
            summary = text[:600]
        docs.append({"title": h.get("title", ""), "url": h["url"], "summary": summary,
                     "snapshot_path": snapshot_path})

    findings: list[dict] = []
    if docs:
        ex = safe_json(
            prompts.EXTRACT_SYSTEM,
            {"topic": topic, "subtopic": st.get("goal", ""),
             "docs": [{k: v for k, v in d.items() if k != "snapshot_path"} for d in docs]},
            prompts.EXTRACT_SCHEMA, caller="research.extract", max_tokens=1800, default=None,
        )
        if ex and ex.get("findings"):
            findings = ex["findings"]

    def _src(d: dict) -> dict:
        s = {"url": d["url"], "title": d["title"], "kind": "web"}
        if d.get("snapshot_path"):
            s["snapshot_path"] = d["snapshot_path"]
        return s

    return {
        "subtopic_id": st.get("id", ""),
        "perspective": st.get("perspective", ""),
        "goal": st.get("goal", ""),
        "findings": findings,
        "sources": [_src(d) for d in docs],
        "raw_snippets": raw_snippets,
    }


def _reflect(topic: str, covered: list[str], findings: list[dict], raw_titles: list[str],
             max_gaps: int) -> dict:
    """看覆盖账本指缺口 + 打捞未用上的料(中端模型)。

    关键: 区分"模型说没缺口"和"模型没答上(限流/超时)"——后者不能当成已覆盖完整(否则深研静默退化成浅研还自称完整)。
    失败返 reflect_failed=True,由编排者保守处理。
    """
    out = safe_json(
        prompts.REFLECT_SYSTEM,
        {"topic": topic, "covered": sorted(set(covered)),
         "claims": [f.get("claim", "") for f in findings][:40],
         "salvage_pool": raw_titles[:30]},
        prompts.REFLECT_SCHEMA, model=prompts.MID_MODEL, caller="research.reflect",
        max_tokens=1500, default=None,
    )
    if out is None:
        return {"open_gaps": [], "salvage": [], "reflect_failed": True}
    gaps = out.get("open_gaps") or []
    for i, g in enumerate(gaps):
        g.setdefault("id", f"gap{i+1}")
    out["open_gaps"] = gaps[:max_gaps]
    out["reflect_failed"] = False
    return out


# ── 节点: 编排(并行子研究 + 反思有界迭代)──────────────────────────────────
class Orchestrator(Router):
    """节点内循环: 并行派子研究员 → 反思指缺口 → 带衰减广度再来一轮(有界)。"""

    DESCRIPTION = "编排: 并行子研究(隔离)+ 反思有界迭代深挖"
    FORMAT_IN = "research.plan"
    FORMAT_OUT = "research.gathered"
    REQUIRED_CONTEXT = ["topic", "run_dir", "subtopics"]

    def run(self, input_data: Any) -> Verdict:
        from omnicompany.runtime.llm.batch import run_parallel_items

        ctx = input_data if isinstance(input_data, dict) else {}
        topic = ctx["topic"]
        run_dir = Path(ctx["run_dir"])
        subtopics = ctx.get("subtopics") or []
        max_rounds = int(ctx.get("max_rounds", 2) or 2)
        workers = int(ctx.get("workers", 4) or 4)
        max_subtopics = int(ctx.get("max_subtopics", 4) or 4)
        max_queries, fetch_top = 3, 2

        all_findings: list[dict] = []
        all_sources: list[dict] = []
        raw_titles: list[str] = []
        covered: list[str] = []
        seen_src: set[str] = set()
        last_gaps: list[dict] = []
        rounds_done = 0
        total_failures = 0
        reflect_failed = False

        for rnd in range(max(1, max_rounds)):
            def _work(st: dict, _t=topic, _mq=max_queries, _ft=fetch_top) -> dict:
                return _research_subtopic(_t, st, max_queries=_mq, fetch_top=_ft)

            res = run_parallel_items(
                subtopics, _work, workers=workers,
                status_run_id=run_dir.name, progress_label=f"research-r{rnd+1}",
            )
            total_failures += len(res.failures)  # 子研究 worker 级异常计数(便于事后定位)
            for r in res.results:
                all_findings.extend(r.get("findings") or [])
                for s in (r.get("sources") or []):
                    u = s.get("url", "")
                    if u and u not in seen_src:
                        seen_src.add(u)
                        all_sources.append(s)
                for rs in (r.get("raw_snippets") or []):
                    if rs.get("title"):
                        raw_titles.append(rs["title"])
                if r.get("perspective"):
                    covered.append(r["perspective"])
            rounds_done = rnd + 1

            if rnd >= max_rounds - 1:
                break
            refl = _reflect(topic, covered, all_findings, raw_titles, max_gaps=max(1, max_subtopics // 2))
            if refl.get("reflect_failed"):
                reflect_failed = True  # 反思失败 ≠ 覆盖完整:保守停在已有结果,coverage 标记不可信
                break
            last_gaps = refl.get("open_gaps") or []
            # salvage(打捞未引用): 撞见但没用上的料也变成下一轮焦点(SOTA 召回)
            salvage_focus = [{"id": f"salv{i+1}", "goal": t, "perspective": "打捞", "queries": [t]}
                             for i, t in enumerate(refl.get("salvage") or []) if t]
            next_focus = (last_gaps + salvage_focus)[: max(1, max_subtopics)]  # 衰减: 封顶 max_subtopics
            if not next_focus:
                break
            subtopics = next_focus

        coverage = {
            "covered": sorted(set(covered)),
            "open": [g.get("perspective") or g.get("goal", "") for g in last_gaps],
            "reflect_failed": reflect_failed,  # True=覆盖判定不可信(反思没答上,非"已完整")
        }
        cov_dir = DATA_ROOT / "coverage"
        cov_dir.mkdir(parents=True, exist_ok=True)
        (cov_dir / f"{run_dir.name}.json").write_text(
            json.dumps({"topic": topic, "rounds": rounds_done, **coverage},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        (run_dir / "gathered.json").write_text(
            json.dumps({"findings": all_findings, "sources": all_sources, "coverage": coverage,
                        "rounds": rounds_done, "worker_failures": total_failures}, ensure_ascii=False,
                       indent=2), encoding="utf-8")

        diag = (f"{rounds_done} 轮 · {len(all_findings)} 条发现 · {len(all_sources)} 源 · "
                f"覆盖 {len(coverage['covered'])} 视角")
        if total_failures:
            diag += f" · {total_failures} 个子研究 worker 异常"
        if reflect_failed:
            diag += " · ⚠反思失败(覆盖判定不可信)"
        return Verdict(
            kind=VerdictKind.PASS,
            output={
                "topic": topic, "topic_norm": ctx["topic_norm"], "run_dir": str(run_dir),
                "findings": all_findings, "sources": all_sources, "coverage": coverage,
                "rounds": rounds_done, "existing": ctx.get("existing"),
            },
            confidence=1.0 if all_findings else 0.0,
            diagnosis=diag,
            granted_tags=["domain.research", "stage.gathered"],
        )
