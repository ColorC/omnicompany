# [OMNI] origin=claude-code domain=services/_diagnosis/project_audit ts=2026-06-19T00:00:00Z type=config status=active
# [OMNI] summary="project_audit team 的 material 定义:target(source) / tree·plan_items(internal) / report(sink)"
# [OMNI] why="遍历-审计 team 要把'项目→整树→计划项→完成度报告'四态显式声明,不靠透传"
# [OMNI] material_id="material:services._diagnosis.project_audit.formats"
"""project_audit team · Material 定义(三档:source / internal / sink)。

这个 team 做一件事:**遍历一个项目的真实文件,逐条核对它每个计划里的每一项到底
做没做完——不信报告/说明文件,只认磁盘上的实物**。
"""
from __future__ import annotations

from omnicompany.protocol.format import Format, FormatRegistry

DOMAIN = "project_audit"

# ── source:要审计的项目 ──
M_TARGET = Format(
    id=f"{DOMAIN}.target",
    name="ProjectAuditTarget",
    description=(
        "一个要审计的项目。\n"
        "- name (str, required): 项目名(自有项目可点名)\n"
        "- root (str, required): 项目根目录绝对路径\n"
        "- plan_globs (list[str], optional): 计划文档 glob,默认 ['**/plan*.md','**/plans/**/*.md','**/ROADMAP*.md','**/*ACTIVE*.md','**/journal/**/*.md']\n"
        "- exclude (list[str], optional): 排除目录,默认 ['.git','node_modules','__pycache__','.venv']\n"
        "- max_plans (int, optional): 单次审计计划数上限(防失控;超出如实记录被略过的)"
    ),
)

# ── internal:整树枚举(遍历产物,非抽样)──
M_TREE = Format(
    id=f"{DOMAIN}.tree",
    name="ProjectTree",
    description=(
        "项目真实文件树的完整枚举(os.walk 全量,非 grep 命中)。\n"
        "- root (str): 根目录\n"
        "- total_files (int): 文件总数(去掉 exclude)\n"
        "- by_ext (dict[str,int]): 按扩展名计数\n"
        "- by_top_dir (dict[str,int]): 顶层各目录文件数\n"
        "- all_paths (list[str]): 全部相对路径(供下游逐项核对证据)\n"
        "- plan_files (list[str]): 命中的计划文档相对路径"
    ),
)

# ── internal:抽出的计划项 ──
M_PLAN_ITEMS = Format(
    id=f"{DOMAIN}.plan_items",
    name="PlanItems",
    description=(
        "从项目所有计划文档里抽出的每一条计划项(checklist / 里程碑 / 退出条件)。\n"
        "- items (list[dict]): 每项 {plan_file, raw, claimed: 'done'|'open'|'unknown'}\n"
        "  claimed 只是文档自己宣称的状态(- [x] / - [ ]),**下游必须独立核对,不得采信**\n"
        "- tree (dict): 透传 ProjectTree 供核对\n"
        "- target (dict): 透传 target"
    ),
)

# ── internal:连接态(tree + prompts + code 累积,逐 worker 富化)──
M_ENRICHED = Format(
    id=f"{DOMAIN}.enriched",
    name="ProjectEnriched",
    description=(
        "在 tree 之上累积两类真源证据的连接态(逐节点富化):\n"
        "- (含 tree 全部字段:root/total_files/all_paths/plan_files/target …)\n"
        "- prompts (list[dict]): A 类真源 —— 我在本地 claude/codex 亲口给 agent 的原始 prompt"
        "(PromptHarvester 据 cwd+路径+关键词跨全部会话日志检索)。每项 {text, source, cwd, ts}\n"
        "- prompt_meta (dict): {scanned_files, matched_files, matched_sessions, total_prompts, kept, truncated}\n"
        "- code (list[dict]): B 类真源 —— agent 真写下的关键文件**内容节选**(CodeReader 真读,非路径)。"
        "每项 {path, bytes, head}\n"
        "- code_meta (dict): {files_read, total_bytes, loc_by_lang, selection_note}"
    ),
)

# ── source:项目发现的种子 ──
M_DISCOVER = Format(
    id=f"{DOMAIN}.discover_seed",
    name="DiscoverSeed",
    description=(
        "项目发现的种子。\n"
        "- session_roots (list[str], optional): 会话日志根,默认 ['~/.claude/projects','~/.codex/sessions','~/.codex/archived_sessions']\n"
        "- repo_roots (list[str], optional): 仓库扫描根(找含 .git/pyproject/package.json 的目录),默认 ['/workspace']\n"
        "- min_sessions (int, optional): 一个 cwd 至少出现这么多次会话才算项目(滤噪),默认 1\n"
        "- exclude_open_source (list[str], optional): 归属边界——这些是'我只是用'的开源,枚举时标记 owned=False"
    ),
)

M_PROJECT_LIST = Format(
    id=f"{DOMAIN}.project_list",
    name="ProjectList",
    description=(
        "据真源(会话 cwd + 仓库扫描)发现的'我真做过的项目'清单。\n"
        "- projects (list[dict]): 每项 {name, root, owned: bool, session_count, evidence, note}\n"
        "  owned=True 表示我在本地 claude/codex 指挥 agent 编辑过(归属边界 §1.3);开源依赖 owned=False\n"
        "- summary (str): 发现过程诚实小结(扫了哪些会话根/仓库根,各发现多少)"
    ),
)

# ── source:完整性临界的输入 ──
M_COMPLETENESS_SEED = Format(
    id=f"{DOMAIN}.completeness_seed",
    name="CompletenessSeed",
    description=(
        "完整性临界(plan §四)的输入:把'应覆盖的项目清单 + 已产出的真源全貌档 + 已发布/草稿页'摆齐核对。\n"
        "- owned_projects (list[str], required): ProjectDiscoverer 判 owned=True 的项目名(应逐个覆盖)\n"
        "- reports (dict[str,dict], optional): {项目名: 该项目 project_audit 报告摘要}\n"
        "- pages (dict[str,dict], optional): {项目名: {path, chars, has_image, has_demo, traceable}}\n"
        "- bar_min_chars (int, optional): 单页最低正文字数门槛(防'写太短'),默认 1500"
    ),
)

M_COMPLETENESS = Format(
    id=f"{DOMAIN}.completeness",
    name="CompletenessVerdict",
    description=(
        "完整性临界裁定。\n"
        "- pass (bool): 是否全覆盖、皆全貌非抽样、无遗漏\n"
        "- covered (list[str]): 已到-bar 覆盖的项目\n"
        "- missing (list[dict]): 缺失/不达标项 {project, reason}(reason 如:无报告/无页/页太短/未读 prompt/未读代码/不可追溯)\n"
        "- summary (str): 诚实小结;不全则明确指出还差什么、打回哪里"
    ),
)

# ── sink:诚实的完成度报告 ──
M_REPORT = Format(
    id=f"{DOMAIN}.report",
    name="ProjectAuditReport",
    description=(
        "逐项核对后的诚实完成度报告。\n"
        "- project (str)\n"
        "- real_scale (dict): 真实规模(文件数 / 按目录 / 按类型)\n"
        "- verified (list[dict]): 每项 {plan_file, item, claimed, verdict: 'done'|'partial'|'not_done'|'uncertain', evidence, note}\n"
        "  verdict 是据真实文件独立判断,与 claimed 可能不一致(不一致点是重点)\n"
        "- skipped (list[str]): 因上限被略过的计划(不静默截断)\n"
        "- summary (str): 人读小结(诚实,不夸大)"
    ),
)


def register_formats(registry: FormatRegistry) -> None:
    for f in (M_TARGET, M_TREE, M_PLAN_ITEMS, M_ENRICHED, M_DISCOVER, M_PROJECT_LIST,
              M_COMPLETENESS_SEED, M_COMPLETENESS, M_REPORT):
        registry.register(f, force=True)
