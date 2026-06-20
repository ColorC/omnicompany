# [OMNI] origin=claude-code domain=services/repo_learner ts=2026-04-09T12:00:00Z
# [OMNI] material_id="material:learning.repo.learner.format_definitions.registry.py"
"""repo_learner formats — 2 个新 Format, 其余复用 repo_architect 命名空间。

Format 链:
  (复用 repo-architect.input → acquired-repo → repo-identity → scaled-survey)
    → repo-learner.learn-dimensions
    → repo-learner.learning-report  (EMIT)
"""

from __future__ import annotations

from omnicompany.protocol.format import Format, FormatRegistry


REPO_LEARNER_LEARN_DIMENSIONS = Format(
    id="repo-learner.learn-dimensions",
    name="RepoLearnerLearnDimensions",
    description=(
        "观察维度参考清单 (非强制分段)。"
        "【字段】learn_dimensions (list[{name, one_liner}]), "
        "learn_dimensions_note (一句话说明 '这是 agent 的视角参考, 不是 OmniCompany 自画像'), "
        "继承自 scaled-survey 的 code_modules / canonical_name / working_path / "
        "disambiguation_hint 等字段透传。"
        "【上游承诺】scale_surveyor 已扫出真实 code_modules, "
        "repo_identity_anchor 已锁定 canonical_name + disambiguation_hint。"
        "【下游用途】main_learner 把 learn_dimensions 作为 SYSTEM 段的观察视角参考, "
        "agent 可以发现新维度, 也可以不按维度分段输出报告。"
        "【不变量】learn_dimensions 非空且每条含 name 和 one_liner; "
        "learn_dimensions_note 必须显式说明 '不是自画像, agent 若需对照 OmniCompany "
        "应从真实代码/SKILL.md/memory 里读取'。"
        "【反模式】不允许在此 Format 里硬编码 OmniCompany 自身在各维度的状态/做法/立场。"
    ),
    parent="repo-architect.scaled-survey",
    tags=["domain.repo_learner", "stage.reference", "repo-learner", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "learn_dimensions": {"type": "array", "items": {"type": "object"}},
            "learn_dimensions_note": {"type": "string"},
        },
        "required": ["learn_dimensions"],
    },
)


REPO_LEARNER_LEARNING_REPORT = Format(
    id="repo-learner.learning-report",
    name="RepoLearnerLearningReport",
    description=(
        "主 agent 产出的自由格式学习报告 + 进度追踪 ledger。"
        "【字段】"
        "report_path (markdown 落盘路径, data/domains/absorption/learning_reports/<name>.md), "
        "report_chars, "
        "ledger_path (进度追踪 JSON 落盘路径, data/domains/absorption/ledger/<name>.json), "
        "files_read_count (主 agent 通过 ledger_record 记录的文件总数), "
        "spawned_subagents_count (最多 3), "
        "budget_used (主 agent turns + 子 agent turns 估计总和), "
        "notable_locations (list[{file, lines, one_line_why}], agent 通过 finalize_report "
        "显式指定的 '学习位置' 清单, 会同时出现在报告 markdown 的 Learning Locations 段)。"
        "【报告正文不变量】markdown 必须含两段: "
        "(1) `## Learning Value` 段 — agent 自由描述学到了什么 + 为什么值得记; "
        "(2) `## Learning Locations` 段 — 每条 `file:line` + 一句话定位。"
        "报告结构之外的段落由 agent 自主决定 (可以按维度分, 可以按模块分, "
        "可以按 '值得偷' / '值得警惕' 分, 都允许)。"
        "【反模式】"
        "(a) 禁止数值判断: 不允许写 '我们和对方相似度 XX%' 这种; "
        "(b) 禁止无行号引用: 所有文件引用必须带 `file:line`, 否则视为幻觉; "
        "(c) 禁止硬编码 OmniCompany 自画像: agent 需对照时应读真实 src/ + SKILL.md; "
        "(d) 禁止使用训练语料里的同名项目知识。"
    ),
    parent="requirement",
    tags=["domain.repo_learner", "stage.deliver", "output.user_facing", "repo-learner", "kind.sink"],
    json_schema={
        "type": "object",
        "properties": {
            "report_path": {"type": "string"},
            "report_chars": {"type": "integer"},
            "ledger_path": {"type": "string"},
            "files_read_count": {"type": "integer"},
            "notable_locations": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["report_path"],
    },
)


ALL_FORMATS: list[Format] = [
    REPO_LEARNER_LEARN_DIMENSIONS,
    REPO_LEARNER_LEARNING_REPORT,
]


def register_formats(registry: FormatRegistry) -> None:
    """把 repo_learner domain 的 Format 注册到全局 FormatRegistry。"""
    for fmt in ALL_FORMATS:
        if not registry.is_registered(fmt.id):
            registry.register(fmt)
