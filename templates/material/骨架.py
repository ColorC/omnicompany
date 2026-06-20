# [OMNI] origin=<填写者 origin, 通常 ai-ide, 用户手写则 human> domain=<服务包或领域路径, 例如 services/foo/formats> ts=<填写时间 ISO8601 UTC> type=config status=active agent=<填写者 session 关联标识, 例如 ai-ide-bd9cde92>
# [OMNI] summary="<服务包名> Material 定义"
# [OMNI] why="<这个服务包/团队为什么需要这组 material, 跟主轴/上下游的关系>"
# [OMNI] tags=material,<服务包名或领域名>,formats,config
# [OMNI] material_id="material:template.material.skeleton.py"
"""<服务包或团队的中文名> · Material 定义

本团队消费 <上游 material id 列表>, 产出:
- <自家 material id 1>   <一句话语义>
- <自家 material id 2>   <一句话语义>
- ...

Material description 五要素: 字段语义 / 上游承诺 / 下游用途 / 最小合法样例 / kind 标记.
"""

from __future__ import annotations

from omnicompany.packages.services._core.omnicompany import Material
from omnicompany.protocol.format import FormatRegistry
# ↑ 命名迁移期: 类名用 Material (新), Registry 仍用 FormatRegistry (旧名 grandfathered)

DOMAIN = "<本服务包/领域名>"   # 例如 "csv_to_md" 或 "gameplay_system"


# ──────────────────────────────────────────────────────────────────────
# <概念分组注释 — 例如 "外部输入" / "中间产物" / "终端输出">
# ──────────────────────────────────────────────────────────────────────

M_<UPPER_CASE_NAME> = Material(
    id=f"{DOMAIN}.<dot.separated.id>",
    name="<驼峰命名>",
    description=(
        "<一段文字, 五要素逐项展开>\n\n"

        "【字段语义】\n"
        "- <field_1> (<type>, required/optional, default <值>): <这个字段在业务里到底是什么, 不是写类型>\n"
        "- <field_2> (...): ...\n\n"

        "【上游承诺 — <producer Worker 名> 必守】\n"
        "1. <承诺 1, 例如 '某字段长度 ≥ 1'>\n"
        "2. <承诺 2, 例如 '某字段格式必须符合 ISO8601'>\n"
        "...\n\n"

        "【下游用途 — <consumer Worker 名> 怎么消费】\n"
        "<下游 Worker 拿这份材料具体做什么动作, 哪些字段被用到, 怎么用>\n\n"

        "【最小合法样例】\n"
        "<一份具体 JSON 实例, 所有 required 字段都填好的合法值>\n"
    ),
    parent="<上层 Format id, 例如 'requirement' / 'doc' / 'code' / 'material'>",
    json_schema={
        "type": "object",
        "properties": {
            "<field_1>": {"type": "<json_type>", "description": "<跟 description 字段语义对齐>"},
            "<field_2>": {"type": "<json_type>", "description": "<...>"},
        },
        "required": ["<必填字段名列表>"],
    },
    tags=[
        "kind.<source/internal/sink>",   # 必有 — 三选一, 决定 Q4 诊断行为
        f"domain.{DOMAIN}",               # 必有 — 业务域归属
        "content.<内容性质标>",           # 按需 — 例如 content.tabular_data / content.markdown / content.code_diff
        # ... 其他你需要的 tag
    ],
    examples=[
        # 至少 1 个具体例子, 跟 description 里的"最小合法样例"一致或更丰富
        # <一份具体 JSON, 所有字段填合法值>,
    ],
)


# 重复上面的模式定义本服务包的其他 material:
# M_<NAME_2> = Material(...)
# M_<NAME_3> = Material(...)
# ...


# ──────────────────────────────────────────────────────────────────────
# 注册集合 — 必有
# ──────────────────────────────────────────────────────────────────────

ALL_MATERIALS = [
    M_<UPPER_CASE_NAME>,
    # M_<NAME_2>,
    # M_<NAME_3>,
]


def register_formats(registry: FormatRegistry) -> None:
    """注册本服务包的所有 Material 到 registry."""
    for mat in ALL_MATERIALS:
        if not registry.is_registered(mat.id):
            try:
                registry.register(mat)
            except Exception:
                pass
