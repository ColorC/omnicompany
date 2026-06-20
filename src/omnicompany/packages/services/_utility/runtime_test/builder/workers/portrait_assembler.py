# [OMNI] origin=claude-code domain=services/runtime_test_builder/workers ts=2026-04-27T00:00:00Z type=worker
# [OMNI] material_id="material:utility.runtime_test.builder.portrait_assembler_implementation.py"
"""PortraitAssemblerWorker — Worker #4 (HARD, sink).

接 hypothesis_evidence + hypothesis_set + target_profile, 装终态 portrait_with_meta.
"""
from __future__ import annotations

from typing import Any, ClassVar

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.anchor import Verdict, VerdictKind


def _pick(input_data: dict, mirror_key: str) -> dict:
    m = input_data.get(mirror_key)
    return dict(m) if isinstance(m, dict) else {}


class PortraitAssemblerWorker(Worker):
    DESCRIPTION = (
        "装终态 portrait_with_meta · 综合 target_profile + hypotheses_proposed + hypothesis_evidence."
    )
    FORMAT_IN: ClassVar[list[str]] = [
        "runtime_test_builder.hypothesis_evidence",
        "runtime_test_builder.hypothesis_set",
        "runtime_test_builder.target_profile",
    ]
    FORMAT_IN_MODE: ClassVar[str] = "and"
    FORMAT_OUT: ClassVar[str] = "runtime_test_builder.portrait_with_meta"

    def run(self, input_data: dict[str, Any]) -> Verdict:
        evidence = _pick(input_data, "_from_HypothesisVerifierDispatcherWorker")
        hyp_set = _pick(input_data, "_from_HypothesisProposerWorker")
        profile = _pick(input_data, "_from_TargetExplorerWorker")

        target_team_id = (
            evidence.get("target_team_id")
            or hyp_set.get("target_team_id")
            or input_data.get("target_team_id", "?")
        )

        hypotheses = hyp_set.get("hypotheses") or []
        results = evidence.get("results") or []

        # 镜像简化: 提案清单 (id + description + importance + library_match_id)
        proposed_brief = [
            {
                "hypothesis_id": h.get("hypothesis_id"),
                "description": h.get("description"),
                "importance": h.get("importance"),
                "source": h.get("source"),
                "library_match_id": h.get("library_match_id"),
            }
            for h in hypotheses
        ]

        # 镜像简化: 验证清单
        evidence_brief = [
            {
                "hypothesis_id": r.get("hypothesis_id"),
                "status": r.get("status"),
                "executed_via": r.get("executed_via"),
                "signals_first": (r.get("signals") or [None])[0] if r.get("signals") else None,
            }
            for r in results
        ]

        verified_pass = sum(1 for r in results if r.get("status") == "verified_pass")
        verified_fail = sum(1 for r in results if r.get("status") == "verified_fail")
        pending = sum(1 for r in results if r.get("status") == "pending_manual")
        errors = sum(1 for r in results if r.get("status") == "execution_error")
        total = len(results)
        verified_total = verified_pass + verified_fail

        # verdict 派生
        # 仅在已实测假设里算; pending 不入分母 (但记入 portrait pending_hypotheses)
        if verified_total == 0:
            # 全 pending → FAIL meta-level (无信号)
            verdict_str = "FAIL"
            verdict_kind = VerdictKind.FAIL
        else:
            pass_rate = verified_pass / verified_total
            if pass_rate >= 0.8:
                verdict_str = "PASS"
                verdict_kind = VerdictKind.PASS
            elif pass_rate >= 0.4:
                verdict_str = "PARTIAL"
                verdict_kind = VerdictKind.PARTIAL
            else:
                verdict_str = "FAIL"
                verdict_kind = VerdictKind.FAIL

        # what_well / what_misses
        what_well: list[str] = []
        what_misses: list[str] = []
        pending_list: list[str] = []

        for r in results:
            hid = r.get("hypothesis_id", "?")
            via = r.get("executed_via", "?")
            sig0 = (r.get("signals") or [""])[0] or r.get("evidence_excerpt", "")
            if r.get("status") == "verified_pass":
                what_well.append(f"假设 `{hid}` 通过 ({via}): {sig0[:200]}")
            elif r.get("status") == "verified_fail":
                what_misses.append(f"假设 `{hid}` 未过 ({via}): {sig0[:200]}")
            elif r.get("status") == "pending_manual":
                pending_list.append(f"假设 `{hid}` (待 Phase D / L1): {via}")
            elif r.get("status") == "execution_error":
                what_misses.append(f"假设 `{hid}` 执行失败 ({via}): {sig0[:200]}")

        if not what_well:
            what_well.append("尚无已验证通过的假设")
        if not what_misses:
            what_misses.append("尚无已验证失败的假设")

        # target_profile_brief
        profile_brief = (
            f"target `{target_team_id}` (path: {profile.get('package_path','?')}). "
            f"输出形态: {(profile.get('output_format_summary') or '?')[:200]} "
            f"设计目的: {(profile.get('design_purpose') or '?')[:200]}"
        )

        # portrait_paragraph
        portrait = (
            f"meta 测试团队针对 target `{target_team_id}` 提出 {len(hypotheses)} 条假设, "
            f"实测 {verified_total} 条 (其中 PASS={verified_pass}, FAIL={verified_fail}), "
            f"待跑 {pending} 条. "
            f"综合 verdict={verdict_str}. "
        )
        if profile.get("design_purpose"):
            portrait += f"target 设计目的: {profile['design_purpose'][:200]} "
        if hyp_set.get("novelty_signals"):
            portrait += f"新颖角度: {'; '.join(hyp_set['novelty_signals'][:3])[:300]} "
        if hyp_set.get("skipped_universal_ids"):
            portrait += f"跳过的通用假设: {', '.join(hyp_set['skipped_universal_ids'])} "

        if len(portrait) < 150:
            portrait += " (本次产物为真 meta 层 v2 实施 · 假设清单见 hypotheses_proposed 字段, 待 L1 抽样审.)"

        physical_metrics = {
            "hypothesis_count": len(hypotheses),
            "verified_pass_count": verified_pass,
            "verified_fail_count": verified_fail,
            "pending_count": pending,
            "execution_error_count": errors,
            "total_results": total,
        }

        # ── 渲染 markdown 文档 (给人直接看) ──
        md_lines: list[str] = []
        md_lines.append(f"# 真 meta 层画像 · {target_team_id}")
        md_lines.append("")
        md_lines.append(f"**总评**: {verdict_str}")
        md_lines.append(
            f"**实测情况**: {verified_pass} 条通过 / {verified_fail} 条未通过 / "
            f"{pending} 条待人工跟进 / {errors} 条执行出错 (共 {total} 条)"
        )
        md_lines.append("")
        md_lines.append("## target 探包简述")
        md_lines.append("")
        md_lines.append(profile_brief)
        md_lines.append("")
        md_lines.append("## 综合段落")
        md_lines.append("")
        md_lines.append(portrait)
        md_lines.append("")
        md_lines.append(f"## 提出的假设清单 ({len(hypotheses)} 条)")
        md_lines.append("")
        for h in hypotheses:
            hid = h.get("hypothesis_id", "?")
            src = h.get("source", "?")
            imp = h.get("importance", "?")
            match = h.get("library_match_id")
            match_str = f"对应库: {match}" if match else "对应库: 无 (novel)"
            md_lines.append(f"### `{hid}` · {src} / {imp} / {match_str}")
            md_lines.append("")
            md_lines.append(f"**主张**: {h.get('description', '?')}")
            md_lines.append("")
            md_lines.append(f"**为什么对此 target 关键**: {h.get('rationale_for_this_target', '?')}")
            md_lines.append("")
            md_lines.append(f"**怎么验**: {h.get('verification_recipe', '?')}")
            if h.get("falsifiability"):
                md_lines.append("")
                md_lines.append(f"**可证伪方式**: {h['falsifiability']}")
            md_lines.append("")
        md_lines.append("## 每条假设的验证状态")
        md_lines.append("")
        for r in results:
            hid = r.get("hypothesis_id", "?")
            status = r.get("status", "?")
            via = r.get("executed_via", "?")
            md_lines.append(f"### `{hid}`")
            md_lines.append("")
            md_lines.append(f"- **状态**: {status}")
            md_lines.append(f"- **跑过的方式**: {via}")
            if r.get("evidence_excerpt"):
                md_lines.append(f"- **证据摘要**: {r['evidence_excerpt']}")
            if r.get("signals"):
                md_lines.append("- **信号**:")
                for s in r["signals"]:
                    if s:
                        md_lines.append(f"  - {s}")
            md_lines.append("")
        md_lines.append("## 做得好的方面")
        md_lines.append("")
        for s in what_well:
            md_lines.append(f"- {s}")
        md_lines.append("")
        md_lines.append("## 漏掉/未通过的方面")
        md_lines.append("")
        for s in what_misses:
            md_lines.append(f"- {s}")
        md_lines.append("")
        if pending_list:
            md_lines.append("## 待人工跟进的假设")
            md_lines.append("")
            for s in pending_list:
                md_lines.append(f"- {s}")
            md_lines.append("")
        md_lines.append("## 物理度量")
        md_lines.append("")
        md_lines.append(f"- 假设总数: {len(hypotheses)}")
        md_lines.append(f"- 真验证通过: {verified_pass}")
        md_lines.append(f"- 真验证未过: {verified_fail}")
        md_lines.append(f"- 待人工跟进: {pending}")
        md_lines.append(f"- 执行出错: {errors}")
        md_lines.append(f"- 验证总记录数: {total}")

        markdown_report = "\n".join(md_lines)

        report = {
            "verdict": verdict_str,
            "target_team_id": target_team_id,
            "target_profile_brief": profile_brief,
            "hypotheses_proposed": proposed_brief,
            "hypotheses_evidence": evidence_brief,
            "portrait_paragraph": portrait,
            "what_target_does_well": what_well,
            "what_target_misses": what_misses,
            "pending_hypotheses": pending_list,
            "physical_metrics": physical_metrics,
            "markdown_report": markdown_report,
        }

        return Verdict(
            kind=verdict_kind,
            output=report,
            diagnosis=(
                f"meta portrait: {verdict_str} · "
                f"{verified_pass}/{verified_total} verified PASS · {pending} pending"
            ),
            confidence=1.0,
        )
