# [OMNI] origin=claude-code domain=services/hypothesis_library/hypothesis ts=2026-04-27T00:00:00Z type=schema
# [OMNI] material_id="material:services.learning.hypothesis_library.hypothesis.dataclass.py"
"""Hypothesis dataclass · 假设条目结构."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Hypothesis:
    """单条假设条目.

    用于真 meta 层针对生成假设时, 从库里挑候选 + LLM 当场组合产新假设.
    全字段自然语言句子 (除 id / category / 离散标签). 不打分.
    """

    id: str
    description: str
    when_applicable: str
    verification_template: str
    examples: tuple[str, ...] = ()
    category: str = "universal"  # 'universal' | 'pattern'
    provenance: str = ""

    def __post_init__(self) -> None:
        # 简单完整性校验
        if not self.id or not self.id.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"Hypothesis.id 应是 snake_case alphanumeric: {self.id!r}")
        if self.category not in ("universal", "pattern"):
            raise ValueError(f"Hypothesis.category 须是 'universal' 或 'pattern': {self.category!r}")
        if len(self.description) < 10:
            raise ValueError(f"Hypothesis.description 过短 (<10 字符): {self.description!r}")
        if len(self.when_applicable) < 10:
            raise ValueError(f"Hypothesis.when_applicable 过短: {self.when_applicable!r}")
