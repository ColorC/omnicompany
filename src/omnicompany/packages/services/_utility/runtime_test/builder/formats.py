# [OMNI] origin=claude-code domain=services/runtime_test_builder/formats ts=2026-04-27T00:00:00Z type=config
# [OMNI] material_id="material:utility.runtime_test.builder.material_definitions.config.py"
"""runtime_test_builder Material 定义 · 真 meta 层 v2 (Phase C 重构).

旧版 (2026-04-26 立, 伪 meta 层 二选一固定模板) 已删:
- runtime_test_builder.test_plan
- runtime_test_builder.inner_portrait_raw
- runtime_test_builder.portrait_forwarded

新版 (2026-04-27 立, 真 meta 层 针对生成假设):
- runtime_test_builder.build_request (entry, 留)
- runtime_test_builder.target_profile (TargetExplorer 产)
- runtime_test_builder.hypothesis_set (HypothesisProposer 产 — 核心创新)
- runtime_test_builder.hypothesis_evidence (VerifierDispatcher 产)
- runtime_test_builder.portrait_with_meta (PortraitAssembler 产 sink)
"""
from __future__ import annotations

from omnicompany.packages.services._core.omnicompany import Material
from omnicompany.protocol.format import FormatRegistry


M_BUILD_REQUEST = Material(
    id="runtime_test_builder.build_request",
    name="runtime_test_builder.build_request",
    description=(
        "真 meta 测试团队构建器入口. 给 target_team_id, builder 自动:\n"
        "1. 深探 target 包 (TargetExplorer)\n"
        "2. 综合 hypothesis_library 当场针对生成假设 (HypothesisProposer)\n"
        "3. 调度每条假设的验证 (HypothesisVerifierDispatcher)\n"
        "4. 装画像 (PortraitAssembler)\n\n"
        "字段: target_team_id (str, required), sample_input_hint (dict, opt 给 LLM 用的 hint).\n\n"
        "⚠️ 旧字段 force_test_team 已删 — 不再二选一固定模板."
    ),
    parent="doc",
    json_schema={
        "type": "object",
        "properties": {
            "target_team_id": {"type": "string", "minLength": 1},
            "sample_input_hint": {"type": "object"},
        },
        "required": ["target_team_id"],
    },
    tags=["runtime_test_builder", "kind.source"],
)


M_TARGET_PROFILE = Material(
    id="runtime_test_builder.target_profile",
    name="runtime_test_builder.target_profile",
    description=(
        "TargetExplorer 深探后的 target 画像. 不是判断'代码 vs 知识'二选一, 是描述产物形态.\n\n"
        "字段:\n"
        "- target_team_id (str)\n"
        "- package_path (str): target 源码目录\n"
        "- output_format_summary (str, 句子, ≥30 字符): target 主要输出 Material 是什么形态 (含 schema 字段类型)\n"
        "- design_purpose (str, 句子, ≥30 字符): target 工作的设计目的, 自然语言\n"
        "- product_kind_signals (list[str], 句子): 探到的产物形态线索 (各角度), 至少 3 条\n"
        "- has_fixtures (bool): tests/teams/<target>/ 或 docs/plans/.../requirements/<target>/ 是否有 expected\n"
        "- has_repo_input (bool): sample_input 是否含 repo_path 类源仓库\n"
        "- has_byte_diffable_output (bool): 输出是否可字节比 (有标杆)\n"
        "- has_external_anchors (bool): 输出是否含 file/line/func 等外部锚点\n"
        "- has_random_or_creative (bool): 输出是否带随机/创意成分 (影响 stable 假设适用)\n"
        "- consumed_input_shape (str, 句子): sample_input/FORMAT_IN schema 简述"
    ),
    parent="doc",
    json_schema={
        "type": "object",
        "properties": {
            "target_team_id": {"type": "string"},
            "package_path": {"type": "string"},
            "output_format_summary": {"type": "string", "minLength": 30},
            "design_purpose": {"type": "string", "minLength": 30},
            "product_kind_signals": {
                "type": "array",
                "items": {"type": "string", "minLength": 10},
                "minItems": 3,
            },
            "has_fixtures": {"type": "boolean"},
            "has_repo_input": {"type": "boolean"},
            "has_byte_diffable_output": {"type": "boolean"},
            "has_external_anchors": {"type": "boolean"},
            "has_random_or_creative": {"type": "boolean"},
            "consumed_input_shape": {"type": "string"},
        },
        "required": [
            "target_team_id",
            "package_path",
            "output_format_summary",
            "design_purpose",
            "product_kind_signals",
        ],
    },
    tags=["runtime_test_builder", "kind.internal"],
)


M_HYPOTHESIS_SET = Material(
    id="runtime_test_builder.hypothesis_set",
    name="runtime_test_builder.hypothesis_set",
    description=(
        "HypothesisProposer 针对生成的 target 特化假设清单 (核心创新).\n\n"
        "每条假设 = 必要不充分条件, 用来逼近模糊产物质量. LLM 综合 target_profile + hypothesis_library "
        "(通用候选 + 现成模式) 当场产, 不是固定模板套.\n\n"
        "字段:\n"
        "- target_team_id (str)\n"
        "- hypotheses (list[obj], ≥3 ≤10): 每条:\n"
        "  - hypothesis_id (str, snake_case): 唯一 id, 可任意命名 (LLM 自由命名)\n"
        "  - library_match_id (str | null): 此假设对应 hypothesis_library 里哪条登记的 id\n"
        "    - 如果是基于 library 某条变种来的, 填那条登记 id (e.g. 'stable' / 'reference_existence' / 'byte_diff_acceptance' 等)\n"
        "    - 如果是完全 target 特化的新假设 (library 没覆盖), 填 null\n"
        "    - 这是给下游调度员用的 — 它根据 library_match_id 决定调哪个 verifier\n"
        "  - source (str enum: 'universal'|'pattern'|'novel'): 来源类别 (跟 library_match_id 对应: universal/pattern → 应有 match_id; novel → null)\n"
        "  - description (str, 句子, ≥20 字符): 假设主张\n"
        "  - rationale_for_this_target (str, 句子, ≥30 字符): 为什么这条假设对此 target 关键\n"
        "  - verification_recipe (str, 句子, ≥30 字符): 怎么程序化判 (具体到此 target 的工具/数据/流程)\n"
        "  - falsifiability (str, 句子): 什么样的实测结果会证伪此假设\n"
        "  - importance (str enum: 'high'|'medium'|'low'): 对此 target 多重要 (LLM 主观但是粗粒度分类避免打分)\n"
        "- novelty_signals (list[str]): LLM 觉得新颖的角度 (target 特殊的)\n"
        "- skipped_universal_ids (list[str]): 哪些通用假设不适用此 target + 理由"
    ),
    parent="doc",
    json_schema={
        "type": "object",
        "properties": {
            "target_team_id": {"type": "string"},
            "hypotheses": {
                "type": "array",
                "minItems": 3,
                "maxItems": 10,
                "items": {
                    "type": "object",
                    "properties": {
                        "hypothesis_id": {"type": "string", "minLength": 1},
                        "library_match_id": {"type": ["string", "null"]},
                        "source": {"type": "string", "enum": ["universal", "pattern", "novel"]},
                        "description": {"type": "string", "minLength": 20},
                        "rationale_for_this_target": {"type": "string", "minLength": 30},
                        "verification_recipe": {"type": "string", "minLength": 30},
                        "falsifiability": {"type": "string"},
                        "importance": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": [
                        "hypothesis_id",
                        "library_match_id",
                        "source",
                        "description",
                        "rationale_for_this_target",
                        "verification_recipe",
                        "importance",
                    ],
                },
            },
            "novelty_signals": {"type": "array", "items": {"type": "string"}},
            "skipped_universal_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["target_team_id", "hypotheses"],
    },
    tags=["runtime_test_builder", "kind.internal"],
)


M_HYPOTHESIS_EVIDENCE = Material(
    id="runtime_test_builder.hypothesis_evidence",
    name="runtime_test_builder.hypothesis_evidence",
    description=(
        "HypothesisVerifierDispatcher 跑出的每条假设的验证证据.\n\n"
        "字段:\n"
        "- target_team_id (str)\n"
        "- results (list[obj]): 每条 hypothesis 一个 result:\n"
        "  - hypothesis_id (str)\n"
        "  - status (str enum): 'verified_pass' | 'verified_fail' | 'pending_manual' | 'execution_error'\n"
        "  - evidence_excerpt (str): 证据摘要 (跑过的 verifier 给的 diagnosis / 数据)\n"
        "  - signals (list[str], 句子): 跑出的具体信号 (做得好或漏)\n"
        "  - executed_via (str): 跑此假设用的方式 (e.g. 'absorption-runtime-test cross-run path' / 'pending_manual')\n"
        "- pending_count (int): 多少条未实测 (待 Phase D 实施)"
    ),
    parent="doc",
    json_schema={
        "type": "object",
        "properties": {
            "target_team_id": {"type": "string"},
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "hypothesis_id": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": [
                                "verified_pass",
                                "verified_fail",
                                "pending_manual",
                                "execution_error",
                            ],
                        },
                        "evidence_excerpt": {"type": "string"},
                        "signals": {"type": "array", "items": {"type": "string"}},
                        "executed_via": {"type": "string"},
                    },
                    "required": ["hypothesis_id", "status", "executed_via"],
                },
            },
            "pending_count": {"type": "integer", "minimum": 0},
        },
        "required": ["target_team_id", "results"],
    },
    tags=["runtime_test_builder", "kind.internal"],
)


M_PORTRAIT_WITH_META = Material(
    id="runtime_test_builder.portrait_with_meta",
    name="runtime_test_builder.portrait_with_meta",
    description=(
        "终态画像 sink. 真 meta 层产物 — 含 target_profile + 假设清单 + 假设证据 + 综合 portrait.\n\n"
        "字段:\n"
        "- verdict (str enum): PASS / PARTIAL / FAIL\n"
        "- target_team_id (str)\n"
        "- target_profile_brief (str, 句子): target 探包简述\n"
        "- hypotheses_proposed (list[obj]): 提出的假设清单镜像 (id + description + importance + library_match_id)\n"
        "- hypotheses_evidence (list[obj]): 每条假设的验证状态镜像\n"
        "- portrait_paragraph (str, ≥150 字): 综合自然语言段落\n"
        "- what_target_does_well (list[str]): 做得好的方面 (自 verified_pass 假设)\n"
        "- what_target_misses (list[str]): 漏的方面 (自 verified_fail 假设)\n"
        "- pending_hypotheses (list[str]): 未实测假设清单 (供 L1 决策 / 后续 catalog 接通)\n"
        "- physical_metrics (obj): {hypothesis_count, verified_pass_count, verified_fail_count, pending_count}\n"
        "- markdown_report (str): 完整 markdown 文档 (主输出, 给人直接读). 上面字段是它的索引视图"
    ),
    parent="requirement",
    json_schema={
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["PASS", "PARTIAL", "FAIL"]},
            "target_team_id": {"type": "string"},
            "target_profile_brief": {"type": "string"},
            "hypotheses_proposed": {"type": "array"},
            "hypotheses_evidence": {"type": "array"},
            "portrait_paragraph": {"type": "string", "minLength": 150},
            "what_target_does_well": {"type": "array", "items": {"type": "string"}},
            "what_target_misses": {"type": "array", "items": {"type": "string"}},
            "pending_hypotheses": {"type": "array", "items": {"type": "string"}},
            "physical_metrics": {"type": "object"},
            "markdown_report": {"type": "string", "minLength": 200},
        },
        "required": [
            "verdict",
            "target_team_id",
            "portrait_paragraph",
            "hypotheses_proposed",
            "hypotheses_evidence",
            "markdown_report",
        ],
    },
    tags=["runtime_test_builder", "kind.sink"],
)


ALL_MATERIALS = [
    M_BUILD_REQUEST,
    M_TARGET_PROFILE,
    M_HYPOTHESIS_SET,
    M_HYPOTHESIS_EVIDENCE,
    M_PORTRAIT_WITH_META,
]


def register_formats(registry: FormatRegistry) -> None:
    for mat in ALL_MATERIALS:
        if not registry.is_registered(mat.id):
            try:
                registry.register(mat)
            except Exception:
                pass
