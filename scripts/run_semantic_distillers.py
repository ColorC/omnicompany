"""run_semantic_distillers — 跑 4 个阶段 I Distiller Router 产出规则候选

Router 不直接写文件（R-06）。本脚本作为调用方：
1. 扫 pilot_identification_auto 目录，构建 findings-bundle
2. 依次调用 4 个 Distiller Router
3. 把 Verdict.output 写到 rules/_candidates/*.candidates.json

L2 审查 candidates 后，手工把条目挪到 rules/*.json（主文件）并填 meaning/confidence。

用法：
    python scripts/run_semantic_distillers.py
    python scripts/run_semantic_distillers.py --findings-root <path>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from omnicompany.packages.domains.gameplay_system.ux.routers.semantic_rule_distiller import (
    ConditionalRuleDistillerRouter,
    InfoDisplayRuleDistillerRouter,
    InteractionRuleDistillerRouter,
    LayoutRuleDistillerRouter,
)
from omnicompany.protocol.anchor import VerdictKind


DEFAULT_FINDINGS_ROOT = Path("/workspace/参考项目/figma/a_series/pilot_identification_auto")


def build_bundle(findings_root: Path) -> dict:
    findings = []
    for md in findings_root.rglob("*_findings.md"):
        if md.name.startswith("manual_"):
            continue
        stem = md.stem
        prefab_name = stem.removesuffix("_findings")
        findings.append(
            {
                "stem": prefab_name,
                "prefab_name": prefab_name,
                "category_dir": md.parent.name,
                "file_path": str(md).replace("\\", "/"),
            }
        )
    findings.sort(key=lambda x: x["stem"])
    return {
        "bundle_root": str(findings_root).replace("\\", "/"),
        "findings": findings,
        "total_count": len(findings),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--findings-root", type=Path, default=DEFAULT_FINDINGS_ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "src" / "omnicompany" / "packages" / "domains" / "gameplay_system" / "ux" / "rules" / "_candidates",
    )
    args = parser.parse_args()

    if not args.findings_root.exists():
        print(f"[ERROR] findings root 不存在: {args.findings_root}")
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)

    bundle = build_bundle(args.findings_root)
    print(f"=== Bundle: {bundle['total_count']} 份 findings ===\n")

    routers = [
        ("interaction", InteractionRuleDistillerRouter()),
        ("info_display", InfoDisplayRuleDistillerRouter()),
        ("layout", LayoutRuleDistillerRouter()),
        ("conditional", ConditionalRuleDistillerRouter()),
    ]

    for name, router in routers:
        verdict = router.run(bundle)
        status = verdict.kind.value
        summary = router.summarize_output(verdict)
        print(f"  [{status}] {router.__class__.__name__:<38} {summary}")
        if verdict.kind != VerdictKind.PASS:
            print(f"    diagnosis: {verdict.diagnosis}")
            continue
        out_path = args.output_dir / f"{name}.candidates.json"
        out_path.write_text(
            json.dumps(verdict.output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"    → {out_path.relative_to(args.output_dir.parents[3])}")

    print()
    print(f"候选已落盘 {args.output_dir}")
    print("下一步 · L2 审 candidates 后手填到 rules/*.json 主文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
