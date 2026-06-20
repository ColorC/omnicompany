# [OMNI] origin=claude-code domain=services/hypothesis_library/__init__ ts=2026-04-27T00:00:00Z type=config
# [OMNI] material_id="material:services.learning.hypothesis_library.package.exports_helpers.py"
"""hypothesis_library · 假设库 (库模块, 非 team).

提供:
- UNIVERSAL_HYPOTHESES: 4 条候选地基假设
- PATTERNS: 5 条现成验证模式
- ALL_HYPOTHESES: 合并

Phase C 真 meta 层 import 用.
"""
from __future__ import annotations

from .hypothesis import Hypothesis
from .universal_hypotheses import UNIVERSAL_HYPOTHESES
from .patterns import PATTERNS


ALL_HYPOTHESES: list[Hypothesis] = list(UNIVERSAL_HYPOTHESES) + list(PATTERNS)


def find_by_id(hyp_id: str) -> Hypothesis | None:
    """按 id 找假设. 找不到返 None."""
    for h in ALL_HYPOTHESES:
        if h.id == hyp_id:
            return h
    return None


def filter_by_category(category: str) -> list[Hypothesis]:
    """按 category 过滤 (universal / pattern)."""
    return [h for h in ALL_HYPOTHESES if h.category == category]


def render_for_prompt(hyps: list[Hypothesis]) -> str:
    """渲染成给 LLM 看的 markdown 段子."""
    if not hyps:
        return "(空假设清单)"
    parts = []
    for h in hyps:
        parts.append(f"### `{h.id}` ({h.category})")
        parts.append(f"- 主张: {h.description}")
        parts.append(f"- 适用: {h.when_applicable}")
        parts.append(f"- 怎么验: {h.verification_template}")
        if h.examples:
            parts.append("- 例子:")
            for ex in h.examples:
                parts.append(f"  - {ex}")
        parts.append(f"- 来源: {h.provenance}")
        parts.append("")
    return "\n".join(parts)


__all__ = [
    "Hypothesis",
    "UNIVERSAL_HYPOTHESES",
    "PATTERNS",
    "ALL_HYPOTHESES",
    "find_by_id",
    "filter_by_category",
    "render_for_prompt",
]
