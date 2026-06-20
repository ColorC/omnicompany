# [OMNI] origin=codex domain=dashboard/boss_sight ts=2026-06-13T07:10:00+08:00 type=infra status=active
# [OMNI] material_id="material:dashboard.boss_sight.reviewstage.material_type_registry.py"
"""Reviewstage material kind/tier resolution backed by Format tags."""
from __future__ import annotations

import threading
from collections.abc import Iterable
from typing import Any

from omnicompany.protocol.format import FormatRegistry

_DEFAULT_REGISTRY: FormatRegistry | None = None
_DEFAULT_REGISTRY_LOCK = threading.Lock()


def default_review_format_registry() -> FormatRegistry:
    """进程级共享 Format 注册表 — 审阅台生产路径用它解析 review.kind.* 扩展。

    扩展一种新审阅材料类型 = 往这个注册表 register 一个带 `review.kind.<name>` tag 的
    Format, 生产 MaterialStore(经 get_store) 即可识别, 无需改 enum。内置 5 个 kind 由
    DEFAULT_REVIEW_KINDS 兜底, 与本注册表无关。lazy 构建 + 缓存, 避免 import 期循环。
    """
    global _DEFAULT_REGISTRY
    with _DEFAULT_REGISTRY_LOCK:
        if _DEFAULT_REGISTRY is None:
            from omnicompany.protocol.format import create_builtin_registry
            reg = create_builtin_registry()
            try:
                from omnicompany.packages.services._core.omnicompany.formats import (
                    register_formats as _register_company_formats,
                )
                _register_company_formats(reg)
            except Exception:  # noqa: BLE001
                pass  # 公司材料 Format 注册失败不应阻断审阅台启动
            _DEFAULT_REGISTRY = reg
        return _DEFAULT_REGISTRY

DEFAULT_REVIEW_KINDS: tuple[str, ...] = (
    "image",
    "markdown",
    "html",
    "key_question",
    "custom_web_template",
)

DEFAULT_REVIEW_TIERS: tuple[str, ...] = (
    "mandatory",
    "important",
    "processual",
    "ignored",
)

REVIEW_KIND_TAG_PREFIX = "review.kind."
REVIEW_TIER_TAG_PREFIX = "review.tier."


def _value(value: Any) -> str:
    raw = value.value if hasattr(value, "value") else value
    return str(raw or "").strip()


def _tag_values(registry: FormatRegistry | None, prefix: str) -> set[str]:
    if registry is None:
        return set()
    values: set[str] = set()
    for fmt in registry.all_formats():
        for tag in fmt.tags:
            if tag.startswith(prefix):
                value = tag[len(prefix):].strip()
                if value:
                    values.add(value)
    return values


def registered_review_kinds(registry: FormatRegistry | None = None) -> set[str]:
    """Known review material kinds.

    Defaults preserve the existing five kinds. Extensions are discovered from
    registered Format tags such as `review.kind.novel_chapter`.
    """
    return set(DEFAULT_REVIEW_KINDS) | _tag_values(registry, REVIEW_KIND_TAG_PREFIX)


def registered_review_tiers(registry: FormatRegistry | None = None) -> set[str]:
    return set(DEFAULT_REVIEW_TIERS) | _tag_values(registry, REVIEW_TIER_TAG_PREFIX)


def normalize_review_kind(value: Any, registry: FormatRegistry | None = None) -> str:
    kind = _value(value)
    if kind in registered_review_kinds(registry):
        return kind
    raise ValueError(
        f"review material kind {kind!r} is not registered. "
        f"Register a Format with tag {REVIEW_KIND_TAG_PREFIX}{kind} first."
    )


def normalize_review_tier(value: Any, registry: FormatRegistry | None = None) -> str:
    tier = _value(value)
    if tier in registered_review_tiers(registry):
        return tier
    raise ValueError(
        f"review material tier {tier!r} is not registered. "
        f"Register a Format with tag {REVIEW_TIER_TAG_PREFIX}{tier} first."
    )


def review_kind_format_preconditions(value: Any, registry: FormatRegistry | None = None) -> list[str]:
    """该 review kind 对应 Format 声明的语义前置条件(= 该类材料的审阅格式要求)。

    设施化双保证的"设施"半边: 提交某 kind 材料时, CLI 读这里把要求作为友情提示回给 agent。
    无注册 Format 或无前置条件时返回空列表。
    """
    if registry is None:
        return []
    tag = f"{REVIEW_KIND_TAG_PREFIX}{_value(value)}"
    out: list[str] = []
    for fmt in registry.all_formats():
        if tag in fmt.tags:
            out.extend(fmt.semantic_preconditions)
    return out


def review_material_tags(kind: Any, tier: Any, extra: Iterable[str] | None = None) -> list[str]:
    tags = [
        f"{REVIEW_KIND_TAG_PREFIX}{_value(kind)}",
        f"{REVIEW_TIER_TAG_PREFIX}{_value(tier)}",
    ]
    for tag in extra or ():
        if tag not in tags:
            tags.append(tag)
    return tags


__all__ = [
    "DEFAULT_REVIEW_KINDS",
    "DEFAULT_REVIEW_TIERS",
    "REVIEW_KIND_TAG_PREFIX",
    "REVIEW_TIER_TAG_PREFIX",
    "normalize_review_kind",
    "normalize_review_tier",
    "registered_review_kinds",
    "registered_review_tiers",
    "review_kind_format_preconditions",
    "review_material_tags",
]
