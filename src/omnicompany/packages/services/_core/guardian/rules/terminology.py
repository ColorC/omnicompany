# [OMNI] origin=claude-code domain=omnicompany/guardian ts=2026-04-19T00:00:00Z type=config
# [OMNI] material_id="material:core.guardian.terminology.legacy_naming_guard.rules.py"
"""Guardian 规则 — 命名迁移反倒退检测 (OMNI-036)。

背景：`docs/standards/terminology.md` (2026-04-19) 启动术语自底向上 ABCD 迁移。
本规则监控"新 module"（白名单路径）内是否仍在用旧命名，给 WARN 防止迁移期回退。

OMNI-036: new-module-legacy-naming

当前 Q0 阶段：`_NEW_MODULE_WHITELIST` 为空 → 规则实装但不触发任何文件。
Phase A 开启时由 L1 填入新 module 路径（如 `src/omnicompany/packages/services/omnicompany/`）。

参考：docs/standards/terminology.md §4 / §五 四把锁（migration plan）
"""
from __future__ import annotations

import re

from ._base import FileContext, GuardianRule, _is_external, _not_graveyard

# ══════════════════════════════════════════════════════════════════════
# 白名单：Phase A 开启时由 L1 填入
# ══════════════════════════════════════════════════════════════════════
_NEW_MODULE_WHITELIST: tuple[str, ...] = (
    # 示例（Phase A 开启时替换）:
    # "src/omnicompany/packages/services/omnicompany/",
)

# ══════════════════════════════════════════════════════════════════════
# 旧命名 identifier / import pattern
# ══════════════════════════════════════════════════════════════════════

# 在源码正文中出现即视为违反（Phase A 开启后扩展）
_LEGACY_IDENTIFIERS = (
    "TeamEdge",
    "TeamSpec",
)

# import 语句 pattern（命中即违反）
_LEGACY_IMPORT_PATTERNS = (
    re.compile(r"\bfrom\s+omnicompany\.protocol\.format\s+import\s+Format\b"),
    re.compile(r"\bfrom\s+omnicompany\.protocol\b.*\bPipelineEdge\b"),
)


# ══════════════════════════════════════════════════════════════════════
# 检测函数
# ══════════════════════════════════════════════════════════════════════


def _in_new_module(ctx: FileContext) -> bool:
    """文件是否在新 module 白名单范围内。"""
    if not _NEW_MODULE_WHITELIST:
        return False
    p = ctx.path.replace("\\", "/")
    return any(p.startswith(w) or f"/{w}" in p for w in _NEW_MODULE_WHITELIST)


def _check_new_module_legacy_naming(ctx: FileContext) -> bool:
    """新 module 内使用旧命名 → WARN。"""
    if not ctx.content:
        return False
    if _is_external(ctx) or not _not_graveyard(ctx):
        return False
    if not _in_new_module(ctx):
        return False

    content = ctx.content
    for identifier in _LEGACY_IDENTIFIERS:
        if identifier in content:
            return True
    for pattern in _LEGACY_IMPORT_PATTERNS:
        if pattern.search(content):
            return True
    return False


# ══════════════════════════════════════════════════════════════════════
# 规则清单
# ══════════════════════════════════════════════════════════════════════


RULES: list[GuardianRule] = [
    GuardianRule(
        id="OMNI-036",
        name="new-module-legacy-naming",
        severity="MEDIUM",
        description=(
            "命名迁移（terminology.md）反倒退检测：新 module 白名单内禁止"
            "使用旧命名（Format / TeamEdge / TeamSpec 等）。"
            "旧代码 grandfathered 不在此规则范围。"
        ),
        check=_check_new_module_legacy_naming,
        disposition=["warn"],
        message_template=(
            "{path}: 新 module 内检出旧命名（legacy identifier 或 import）。"
            "请用新命名：Material / Worker / Team / Stock / Department。"
            "详见 docs/standards/terminology.md。"
        ),
        certainty="absolute",
    ),
]
