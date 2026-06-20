# [OMNI] origin=claude-code domain=scripts ts=2026-04-25T00:00:00Z type=script status=active
"""Phase 4c · v2.2 ComparisonEvaluatorAgent 跑 4 份产物 vs 黄金样本.

每份独立 MemoryBus 实例 + 独立 agent 实例, 减少跨 run 状态污染.
输出 evaluations/v2_2_phase_4c_evaluations.json.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# (job_id, label, tier, candidate_filename, golden_path_relative_to_workspace_root)
JOBS = [
    ("v2_2_run_1_modest", "art_internal", "internal",
     "draft_internal.md",
     "../content_drafts/2026-04-25/internal/article_agent_first_llm_first_lessons.md"),
    ("v2_2_run_2_wr_internal", "wr_internal", "internal",
     "draft_internal.md",
     "../content_drafts/2026-04-25/internal/work_report_two_weeks.md"),
    ("v2_2_run_3_wr_public", "wr_public", "public",
     "draft_public.md",
     "../content_drafts/2026-04-25/public/work_report_core_only.md"),
    ("v2_2_run_4_art_public", "art_public", "public",
     "draft_public.md",
     "../content_drafts/2026-04-25/public/article_agent_engineering_disciplines.md"),
]


async def _eval_one(job_id: str, label: str, tier: str, cand_file: str, gold_path: str) -> dict:
    from omnicompany.bus.memory import MemoryBus
    from omnicompany.packages.services.publishing_commons.comparison_evaluator_agent import ComparisonEvaluatorAgent

    bus = MemoryBus()
    agent = ComparisonEvaluatorAgent(bus=bus)
    candidate_path = f"data/services/report_author/jobs/{job_id}/{cand_file}"

    print(f"\n=== eval {label} ({tier}) ===")
    print(f"  candidate: {candidate_path}")
    print(f"  golden:    {gold_path}")

    verdict = await agent.run({
        "candidate_path": candidate_path,
        "golden_path": gold_path,
        "tier": tier,
        "candidate_label": f"v2_2_{label}",
        "golden_label": f"golden_{label}",
    })

    out = {
        "label": label,
        "tier": tier,
        "candidate_path": candidate_path,
        "golden_path": gold_path,
        "verdict_kind": verdict.kind.value,
        "diagnosis": verdict.diagnosis,
        "output": verdict.output,
    }
    print(f"  → kind={verdict.kind.value} overall={verdict.output.get('overall', '?')}")
    return out


async def main():
    results = []
    for job_id, label, tier, cand_file, gold_path in JOBS:
        try:
            r = await _eval_one(job_id, label, tier, cand_file, gold_path)
        except Exception as e:
            print(f"  !! exception: {type(e).__name__}: {e}")
            r = {
                "label": label,
                "tier": tier,
                "verdict_kind": "exception",
                "exception": f"{type(e).__name__}: {e}",
            }
        results.append(r)

    out_path = Path("data/services/publishing_commons/evaluations/v2_2_phase_4c_evaluations.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== summary ===")
    print(f"saved {len(results)} evaluations to {out_path}")
    overall_scores = []
    for r in results:
        if r.get("output"):
            o = r["output"].get("overall")
            print(f"  {r['label']:<15} overall={o} kind={r['verdict_kind']}")
            if isinstance(o, (int, float)):
                overall_scores.append(o)
        else:
            print(f"  {r['label']:<15} {r.get('exception', 'no output')}")
    if overall_scores:
        avg = sum(overall_scores) / len(overall_scores)
        n_pass = sum(1 for s in overall_scores if s >= 7.5)
        print(f"  avg={avg:.2f}  ≥7.5: {n_pass}/{len(overall_scores)}")


if __name__ == "__main__":
    asyncio.run(main())
