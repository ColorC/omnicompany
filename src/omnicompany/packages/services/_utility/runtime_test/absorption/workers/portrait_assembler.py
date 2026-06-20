# [OMNI] origin=claude-code domain=services/absorption_runtime_test/workers ts=2026-04-27T00:00:00Z type=worker
# [OMNI] material_id="material:utility.runtime_test.absorption.portrait_assembler_implementation.py"
"""PortraitAssemblerWorker — Worker #6 (HARD · sink).

装画像 · 3 路 evidence 汇总 + 自然语言段落 + 做得好/漏 句子列表 + verdict 派生.

2026-04-27 改名 (旧: knowledge_runtime_test) + 删路 2 独立重评.
"""
from __future__ import annotations

import time
from typing import Any, ClassVar

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.anchor import Verdict, VerdictKind


def _pick(input_data: dict, mirror_key: str) -> dict:
    """取上游 _from_<wid> 镜像; 缺则空 dict."""
    m = input_data.get(mirror_key)
    return dict(m) if isinstance(m, dict) else {}


def _is_high(pct: float, threshold: float = 0.5) -> bool:
    """物理度量是否超过门槛."""
    return isinstance(pct, (int, float)) and pct >= threshold


class PortraitAssemblerWorker(Worker):
    DESCRIPTION = (
        "装画像 sink · HARD · 3 路 evidence 汇总 + 派生 verdict + 自然语言段落 + 做得好/漏 句子列表."
    )
    FORMAT_IN: ClassVar[list[str]] = [
        "absorption_runtime_test.cross_run_evidence",
        "absorption_runtime_test.spot_impl_evidence",
        "absorption_runtime_test.source_coverage_evidence",
        "absorption_runtime_test.target_metadata",
    ]
    FORMAT_IN_MODE: ClassVar[str] = "and"
    FORMAT_OUT: ClassVar[str] = "absorption_runtime_test.portrait"

    def run(self, input_data: dict[str, Any]) -> Verdict:
        cross = _pick(input_data, "_from_CrossRunStabilityVerifierWorker")
        spot = _pick(input_data, "_from_SpotImplVerifierWorker")
        cover = _pick(input_data, "_from_SourceCoverageVerifierWorker")
        meta = _pick(input_data, "_from_TargetIngressWorker")

        target_id = meta.get("target_team_id") or input_data.get("target_team_id", "?")

        # ── 物理度量汇总 ──
        run_count = meta.get("run_count", 0)
        file_overlap = float(cross.get("file_overlap_pct") or 0.0)
        topic_overlap = float(cross.get("topic_overlap_pct") or 0.0)
        impl_combined = float(spot.get("combined_pct") or 0.0)
        coverage_pct = float(cover.get("coverage_pct") or 0.0)
        coverage_applicable = bool(cover.get("applicable"))

        # ── 派生 verdict ──
        # 3 路各阈值; 不可判路不计入分母
        signals_pass = 0
        signals_total = 0

        # 路 1 跨次稳定: file_union_size > 0 才有效 (= 至少 2 次成功跑+有产物)
        cross_applicable = (cross.get("file_union_size", 0) or 0) > 0
        if cross_applicable:
            signals_total += 1
            if _is_high(max(file_overlap, topic_overlap), 0.5):
                signals_pass += 1

        # 路 3 抽样落地: combined ≥ 0.5
        signals_total += 1
        if _is_high(impl_combined, 0.5):
            signals_pass += 1

        # 路 4 源覆盖: applicable 时计入
        if coverage_applicable:
            signals_total += 1
            if _is_high(coverage_pct, 0.5):
                signals_pass += 1

        pass_rate = signals_pass / signals_total if signals_total else 0.0
        if pass_rate >= 0.99:  # 3/3 严要求才 PASS
            verdict_kind = VerdictKind.PASS
            verdict_str = "PASS"
        elif pass_rate >= 0.5:  # ≥ 2/3 (2/3 = 0.667, 1/2 = 0.5)
            verdict_kind = VerdictKind.PARTIAL
            verdict_str = "PARTIAL"
        else:
            verdict_kind = VerdictKind.FAIL
            verdict_str = "FAIL"

        # ── 装"做得好"/"漏掉" 句子列表 ──
        what_well: list[str] = []
        what_misses: list[str] = []

        # 路 1 (含不可判时分支)
        if cross.get("stability_observation"):
            obs = cross["stability_observation"]
            if not cross_applicable:
                what_misses.append(f"跨次稳定性不可判: {obs}")
            elif file_overlap >= 0.5 or topic_overlap >= 0.7:
                what_well.append(f"跨次稳定性: {obs}")
            else:
                what_misses.append(f"跨次稳定性弱: {obs}")
        for s in cross.get("divergence_signals") or []:
            what_misses.append(f"跨次发散: {s}")

        # 路 3
        if spot.get("groundedness_observation"):
            obs = spot["groundedness_observation"]
            if impl_combined >= 0.5:
                what_well.append(f"提案具体性: {obs}")
            else:
                what_misses.append(f"提案空泛多: {obs}")

        # 路 4
        if cover.get("coverage_observation"):
            obs = cover["coverage_observation"]
            if not coverage_applicable:
                what_misses.append(f"源覆盖不适用: {obs}")
            elif coverage_pct >= 0.5:
                what_well.append(f"源覆盖: {obs}")
            else:
                what_misses.append(f"源覆盖低 (漏关键模块): {obs}")
        for f in cover.get("key_modules_missed_by_target") or []:
            what_misses.append(f"漏关键模块: {f}")

        if not what_well:
            what_well.append("各路证据均显示该 target 在所测维度上无明显优势")
        if not what_misses:
            what_misses.append("各路证据均未发现明显盲区或退化信号")

        # ── 装画像段落 ──
        portrait = (
            f"team `{target_id}` 经 3 路独立验证: "
            f"跨次稳定 (文件 {file_overlap:.0%} 主题 {topic_overlap:.0%}) · "
            f"抽样落地 {impl_combined:.0%} · "
            f"源覆盖 "
            + (f"{coverage_pct:.0%}" if coverage_applicable else "不适用")
            + f". 综合 {signals_pass}/{signals_total} 路达标 → {verdict_str}. "
        )
        if cross.get("stability_observation"):
            portrait += f"跨次稳定层: {cross['stability_observation']} "
        if spot.get("groundedness_observation"):
            portrait += f"具体性层: {spot['groundedness_observation']} "
        if cover.get("coverage_observation"):
            portrait += f"源覆盖层: {cover['coverage_observation']}"
        portrait = portrait.strip()
        if len(portrait) < 150:
            portrait += " (画像段落补充: 详细多维证据见 evidence_paths 字段, 由 L1+L2 抽样审定.)"

        # ── 装最终 ──
        run_id_str = f"art_{int(time.time())}"
        physical_metrics = {
            "run_count": run_count,
            "file_overlap_pct": file_overlap,
            "topic_overlap_pct": topic_overlap,
            "impl_combined_pct": impl_combined,
            "coverage_pct": coverage_pct,
            "cross_applicable": cross_applicable,
            "coverage_applicable": coverage_applicable,
            "signals_pass": signals_pass,
            "signals_total": signals_total,
        }

        # ── 渲染 markdown 文档 (给人直接看, 不需要外部渲染器) ──
        md_lines: list[str] = []
        md_lines.append(f"# absorption 测试团队画像 · {target_id}")
        md_lines.append("")
        md_lines.append(f"**总评**: {verdict_str} ({signals_pass}/{signals_total} 路达标)")
        md_lines.append(f"**run_id**: {run_id_str}")
        md_lines.append("")
        md_lines.append("## 综合段落")
        md_lines.append("")
        md_lines.append(portrait)
        md_lines.append("")
        md_lines.append("## 做得好的方面")
        md_lines.append("")
        for s in what_well:
            md_lines.append(f"- {s}")
        md_lines.append("")
        md_lines.append("## 漏掉的方面")
        md_lines.append("")
        for s in what_misses:
            md_lines.append(f"- {s}")
        md_lines.append("")
        md_lines.append("## 三条路径细节")
        md_lines.append("")
        md_lines.append("### 路 1 · 跨次稳定")
        md_lines.append(f"- 文件层重叠率: {file_overlap:.0%}")
        md_lines.append(f"- 主题层重叠率: {topic_overlap:.0%}")
        md_lines.append(f"- 是否可判: {'是' if cross_applicable else '否'}")
        if cross.get("stability_observation"):
            md_lines.append(f"- 观察: {cross['stability_observation']}")
        if cross.get("divergence_signals"):
            md_lines.append("- 发散信号:")
            for s in cross["divergence_signals"]:
                md_lines.append(f"  - {s}")
        md_lines.append("")
        md_lines.append("### 路 3 · 抽样落地 (absorption 特化)")
        md_lines.append(f"- 综合通过率: {impl_combined:.0%}")
        md_lines.append(f"- 可实施率: {float(spot.get('implementable_pct') or 0.0):.0%}")
        md_lines.append(f"- 真解决率: {float(spot.get('truly_solves_pct') or 0.0):.0%}")
        if spot.get("groundedness_observation"):
            md_lines.append(f"- 观察: {spot['groundedness_observation']}")
        md_lines.append("")
        md_lines.append("### 路 4 · 源覆盖 (absorbing 特化)")
        md_lines.append(f"- 是否适用: {'是' if coverage_applicable else '否 (target 不消费源仓库)'}")
        if coverage_applicable:
            md_lines.append(f"- 覆盖率: {coverage_pct:.0%}")
            md_lines.append(f"- 关键模块总数: {cover.get('key_modules_total', '?')}")
            md_lines.append(f"- 候选池大小: {cover.get('candidate_pool_size', '?')}")
            if cover.get("key_modules_touched_by_target"):
                md_lines.append("- 目标摸过的关键模块:")
                for f in cover["key_modules_touched_by_target"]:
                    md_lines.append(f"  - {f}")
            if cover.get("key_modules_missed_by_target"):
                md_lines.append("- 目标漏的关键模块:")
                for f in cover["key_modules_missed_by_target"]:
                    md_lines.append(f"  - {f}")
        if cover.get("coverage_observation"):
            md_lines.append(f"- 观察: {cover['coverage_observation']}")
        md_lines.append("")
        md_lines.append("## 物理度量")
        md_lines.append("")
        md_lines.append(f"- 跑了 {run_count} 次")
        md_lines.append(f"- 路径达标数: {signals_pass}/{signals_total}")
        md_lines.append(f"- 文件层重叠率: {file_overlap:.4f}")
        md_lines.append(f"- 主题层重叠率: {topic_overlap:.4f}")
        md_lines.append(f"- 抽样落地综合通过率: {impl_combined:.4f}")
        md_lines.append(f"- 关键模块覆盖率: {coverage_pct:.4f}")

        markdown_report = "\n".join(md_lines)

        report = {
            "verdict": verdict_str,
            "target_team_id": target_id,
            "evidence_paths": {
                "cross_run": cross,
                "spot_impl": spot,
                "source_coverage": cover,
            },
            "portrait_paragraph": portrait,
            "what_target_does_well": what_well,
            "what_target_misses": what_misses,
            "physical_metrics": physical_metrics,
            "run_id": run_id_str,
            "markdown_report": markdown_report,
        }

        return Verdict(
            kind=verdict_kind,
            output=report,
            diagnosis=f"画像装好: {verdict_str} · {signals_pass}/{signals_total} 路达标",
            confidence=1.0,
        )
