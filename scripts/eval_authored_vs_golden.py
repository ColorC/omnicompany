# [OMNI] origin=claude-code domain=scripts ts=2026-04-25T00:00:00Z
"""LLM 对照评估 CLI: 评 LLM 产出对黄金样本的差距.

用法:
    python scripts/eval_authored_vs_golden.py \
        --candidate path/to/draft_internal.md \
        --golden path/to/golden_article.md \
        --tier internal \
        [--output report.json]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def main() -> int:
    p = argparse.ArgumentParser(description="LLM 对照评估 (LLM 产出 vs 黄金样本)")
    p.add_argument("--candidate", required=True, help="LLM 产出 markdown 路径")
    p.add_argument("--golden", required=True, help="黄金样本 markdown 路径")
    p.add_argument("--tier", default="internal", choices=["internal", "public"])
    p.add_argument("--output", default=None, help="保存 JSON 报告路径; 不指定则只打印")
    args = p.parse_args()

    cand_path = Path(args.candidate)
    gold_path = Path(args.golden)

    if not cand_path.is_file():
        print(f"ERROR: candidate 不存在 {cand_path}", file=sys.stderr)
        return 2
    if not gold_path.is_file():
        print(f"ERROR: golden 不存在 {gold_path}", file=sys.stderr)
        return 2

    cand_text = cand_path.read_text(encoding="utf-8")
    gold_text = gold_path.read_text(encoding="utf-8")

    print(f"[eval] candidate={cand_path} ({len(cand_text)} chars)")
    print(f"[eval] golden={gold_path} ({len(gold_text)} chars)")
    print(f"[eval] tier={args.tier}")
    print(f"[eval] LLM 评估中...")

    from omnicompany.packages.services.publishing_commons import evaluate_candidate_vs_golden

    result = evaluate_candidate_vs_golden(
        cand_text,
        gold_text,
        tier=args.tier,
        candidate_label=cand_path.name,
        golden_label=gold_path.name,
    )

    if "_parse_error" in result:
        print(f"\n[eval] ERROR: LLM JSON 解析失败: {result.get('_parse_error')}")
        print("raw response (first 1000):")
        print((result.get("_raw") or "")[:1000])
        return 1

    print()
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n[eval] 已保存 {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
