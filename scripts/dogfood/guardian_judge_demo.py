# OMNI-PERSISTENT-SCRIPT
# owner: ai-ide
# purpose: Guardian LLM 复核 demo — 真用 LLMClient 复核 OMNI-035f2 候选, 真验证 LLM 复核价值
"""Guardian LLM 复核 demo (2026-05-08).

直接调 LLMClient (不走完整 ConfigurableAgent loop) 喂 5 个 OMNI-035f2 候选,
真出 LLM verdict (confirmed / legitimate_specialization / ambiguous) + reasoning.

真用例: 真验证 LLM 复核能否真区分"散件应重组" vs "真合理特化子目录".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 添加 omnicompany 到 path
REPO_ROOT = Path("/workspace/omnicompany")
sys.path.insert(0, str(REPO_ROOT / "src"))

from omnicompany.runtime.llm.llm import LLMClient


# 5 个真 OMNI-035f2 候选 (从 patrol12.json 抽)
CANDIDATES = [
    {
        "path": "docs/plans/agent-framework/[2026-04-24]TEAM-BUILDER-REAL-PASS/requirements/csv_to_md/requirement.md",
        "rule_id": "OMNI-035f2",
        "subdir": "requirements",
        "context_files": [
            ("docs/plans/agent-framework/[2026-04-24]TEAM-BUILDER-REAL-PASS/plan.md", 600),
        ],
    },
    {
        "path": "docs/plans/agent-framework/[2026-04-24]TEAM-BUILDER-REAL-PASS/requirements/csv_to_md/fixtures/case_1_basic.csv",
        "rule_id": "OMNI-035f2",
        "subdir": "requirements",
        "context_files": [],
    },
    {
        "path": "docs/plans/diagnosis/[2026-04-25]AUTO-DOCAUTHOR-WORKER/gold_samples/A_gameplay_system_knowledge/DESIGN.md",
        "rule_id": "OMNI-035f2",
        "subdir": "gold_samples",
        "context_files": [
            ("docs/plans/diagnosis/[2026-04-25]AUTO-DOCAUTHOR-WORKER/plan.md", 600),
        ],
    },
    {
        "path": "docs/plans/omnicompany-调研吸收/[2026-04-13]REPO-ABSORPTION-V2/reference_answers/codex/highlights.md",
        "rule_id": "OMNI-035f2",
        "subdir": "reference_answers",
        "context_files": [
            ("docs/plans/omnicompany-调研吸收/[2026-04-13]REPO-ABSORPTION-V2/plan.md", 600),
        ],
    },
    {
        "path": "docs/plans/diagnosis/[2026-05-05]DIAGNOSIS-RECONSOLIDATION/data/anti_patterns/archetypes.yaml",
        "rule_id": "OMNI-035f2",
        "subdir": "anti_patterns",
        "context_files": [
            ("docs/plans/diagnosis/[2026-05-05]DIAGNOSIS-RECONSOLIDATION/plan.md", 400),
        ],
    },
]


SYSTEM_PROMPT = """你是 OmniGuardian 的 LLM 复核 agent.

你收到 OMNI-035f2 候选: docs/plans/[date]TOPIC/ 下子目录第一段不在闭集
(spikes/_archive/samples/data/reports), 死扫报候选, 但真可能是合理特化子目录.

对每条候选给 verdict:
- `confirmed`: 真违规, 应重组到闭集子目录
- `legitimate_specialization`: 真合理特化, 闭集应扩
- `ambiguous`: 真不确定

输出 JSON: `{"verdict": ..., "reasoning": "...", "suggestion": "..."}`. 不打分不数字, 用自然语言论证.
"""


def _load_context(file_path: str, max_chars: int) -> str:
    p = REPO_ROOT / file_path
    if not p.exists():
        return f"(file not found: {file_path})"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... (truncated)"
        return text
    except Exception as e:
        return f"(read error: {e})"


def judge_one(client: LLMClient, candidate: dict) -> dict:
    """真复核一条候选."""
    user_msg = f"""# 候选

- 路径: {candidate['path']}
- 规则: {candidate['rule_id']}
- 子目录第一段: `{candidate['subdir']}` (不在闭集)

# 上下文 (该 plan 顶级 plan.md, 真读 plan 主题)
"""
    for ctx_path, max_chars in candidate["context_files"]:
        user_msg += f"\n## {ctx_path}\n```\n{_load_context(ctx_path, max_chars)}\n```\n"

    user_msg += """
# 你的判断

输出 JSON: `{"verdict": "confirmed" | "legitimate_specialization" | "ambiguous", "reasoning": "...", "suggestion": "..."}`
"""

    response = client.call(
        messages=[{"role": "user", "content": user_msg}],
        system=SYSTEM_PROMPT,
        caller="guardian_judge_demo",
    )
    text = response.content if hasattr(response, "content") else str(response)
    # 真尝试解析 JSON (LLM 可能裹 ```json fence)
    text_clean = text.strip()
    if "```json" in text_clean:
        text_clean = text_clean.split("```json", 1)[1].split("```", 1)[0].strip()
    elif text_clean.startswith("```"):
        text_clean = text_clean.split("```", 1)[1].rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(text_clean)
    except Exception as e:
        parsed = {"verdict": "parse_error", "reasoning": f"raw: {text[:200]}", "suggestion": str(e)}
    return {**parsed, "raw": text[:300]}


def main():
    print("Guardian LLM 复核 demo · 5 OMNI-035f2 候选\n")
    client = LLMClient(role="judge", model="qwen-3.6-plus")
    results = []
    for i, c in enumerate(CANDIDATES, 1):
        print(f"[{i}/{len(CANDIDATES)}] {c['path']}")
        try:
            r = judge_one(client, c)
        except Exception as e:
            r = {"verdict": "error", "reasoning": str(e), "suggestion": ""}
        results.append({"path": c["path"], "subdir": c["subdir"], **r})
        print(f"  → verdict: {r.get('verdict')}")
        print(f"  → reasoning: {r.get('reasoning', '')[:200]}")
        print()

    # 真出汇总
    print("=" * 60)
    print("真复核汇总")
    print("=" * 60)
    from collections import Counter
    by_verdict = Counter(r["verdict"] for r in results)
    for v, n in by_verdict.most_common():
        print(f"  {v}: {n}")
    print()

    # 真出 JSON 给后续报告引用
    out_path = Path(__file__).parent / "verdicts.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"verdicts saved → {out_path}")


if __name__ == "__main__":
    main()
