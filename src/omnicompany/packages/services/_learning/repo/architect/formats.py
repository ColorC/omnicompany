# [OMNI] origin=claude-code domain=repo_architect/formats.py ts=2026-04-09T00:00:00Z
# [OMNI] material_id="material:learning.repo.architect.format_definitions.registry.py"
"""repo_architect formats — 16 Format 定义,覆盖完整 repo 架构分析管线。

这份文件是 workflow-factory 自动生成 (node_planner 截断, 只写出 5/16) 的**人工补齐版本**。
补齐原因见 docs/plans/[2026-04-08]REPO-ABSORPTION-WORKFLOW/08_STAGE_GOAL_AND_DRIFT_LOG.md 和
session 对 workflow-factory 硬截断事故的诊断记录。

Format 链拓扑 (阶段性):
  阶段 1 准备:       input → acquired-repo → scaled-survey → mode-selected
  阶段 2 信息收集:   (mode-selected 分叉) → research-notes / docs-summary / user-focus-profile
  阶段 3 报告骨架:   report-skeleton
  阶段 4 并行深度:   module-draft (leaf) → draft-set
  阶段 5 质量门:     coverage-feedback → validated-drafts → cross-validation
  阶段 6 融合发布:   arch-report + coverage-report → kb-entry
"""

from __future__ import annotations

from omnicompany.protocol.format import Format, FormatRegistry


# ═══════════════════════════════════════════════════════════
# 阶段 1 准备
# ═══════════════════════════════════════════════════════════

REPO_ARCH_INPUT = Format(
    id="repo-architect.input",
    name="RepoArchitectInput",
    description=(
        "管线入口输入。内容语义: 封装用户发起架构分析任务所需的全部参数,"
        "{url 或 local_path}+{可选 focus}+{可选 mode}. 验证标准: url 和 local_path "
        "必须二选一(互斥), url 需符合 https://github.com/ 或 git@github.com: 前缀, "
        "local_path 必须是存在且可读的目录, focus 若提供则为 <= 2000 字符的自然语言字符串, "
        "mode 若提供则为 quick/standard/deep 之一。下游用途: input_validator 做 schema "
        "校验后交给 repo_acquirer 开始真实 clone 或 mount 本地仓库。"
    ),
    parent="requirement",
    tags=["domain.repo_architect", "stage.input", "kind.source"],
    json_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "local_path": {"type": "string"},
            "focus": {"type": "string"},
            "mode": {"type": "string", "enum": ["quick", "standard", "deep"]},
        },
        "required": [],
    },
)

REPO_ARCH_ACQUIRED_REPO = Format(
    id="repo-architect.acquired-repo",
    name="RepoArchitectAcquiredRepo",
    description=(
        "已获取仓库封装。内容语义: repo_acquirer 完成 clone/mount 后得到的可分析仓库状态。"
        "【字段】working_path (绝对路径,仓库根)、repo_name (目录名或 clone URL 末段)、"
        "default_branch、file_tree_summary {file_count, dir_count, max_depth, "
        "languages (后缀→计数 top 8)}。"
        "【值域】working_path 必须是 OS 路径且可读;default_branch ∈ {main, master} "
        "或任意字符串(回落值)。【上游承诺】必须通过 input_validator 的 schema 校验。"
        "【下游用途】repo_identity_anchor 读它提取真实项目身份;scale_surveyor 读它算规模。"
        "【不变量】file_count > 0 且 languages 非空(空项目视为 FAIL)。"
    ),
    parent="repo-architect.input",
    tags=["domain.repo_architect", "stage.acquired", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "working_path": {"type": "string"},
            "repo_name": {"type": "string"},
            "default_branch": {"type": "string"},
            "file_tree_summary": {"type": "object"},
        },
        "required": ["working_path", "repo_name"],
    },
)

REPO_ARCH_REPO_IDENTITY = Format(
    id="repo-architect.repo-identity",
    name="RepoArchitectRepoIdentity",
    description=(
        "仓库身份锚。内容语义: 从真实文件 (pyproject.toml / package.json / Cargo.toml / "
        "go.mod / README.md / git remote) 提取的项目官方身份信息, 用于防止 LLM 分析时"
        "因 repo_name 和外部项目同名 (例: OmniCompany 和 voxel_sandbox OmniCompany 模组) "
        "而把外部知识幻觉成项目本身。"
        "【字段】canonical_name (官方名, 从 toml/json/README title 读, 不是目录名), "
        "canonical_description (官方一句话描述), homepage (URL 可空), "
        "git_remote_url (origin URL 可空), primary_language (最多文件的语言), "
        "ecosystem (python/node/rust/go/mixed/unknown), "
        "evidence_sources (实际读取到的文件列表, 证据链), "
        "disambiguation_hint (告诉下游 LLM '这不是 X 也不是 Y, 是这个' 的显式声明)。"
        "【上游承诺】已通过 acquired-repo 的 working_path 真实可访问。"
        "【下游用途】所有 LLM 调用节点 (external_researcher / docs_reader / "
        "module_drafter / report_designer / report_fuser) 在 prompt 开头强制粘贴 "
        "disambiguation_hint + canonical_description, 作为 LLM 的锚定上下文。"
        "【不变量】evidence_sources 非空 (至少一份证据文件), disambiguation_hint 必须是"
        "完整句子且含 'This project is ... and is NOT ...' 格式。"
        "【最小合法样例】{canonical_name: 'OmniCompany', "
        "canonical_description: 'AI-native software factory for multi-domain pipelines', "
        "homepage: '', git_remote_url: '', primary_language: 'python', ecosystem: 'python', "
        "evidence_sources: ['pyproject.toml', 'README.md'], "
        "disambiguation_hint: 'This project is the_company Games internal OmniCompany framework "
        "(Python-based AI pipeline factory). This is NOT the voxel_sandbox OmniCompany modpack "
        "and NOT any other project that shares the name.'}"
    ),
    parent="repo-architect.acquired-repo",
    tags=["domain.repo_architect", "stage.identity", "anti_hallucination", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "canonical_name": {"type": "string"},
            "canonical_description": {"type": "string"},
            "primary_language": {"type": "string"},
            "ecosystem": {"type": "string"},
            "evidence_sources": {"type": "array", "items": {"type": "string"}},
            "disambiguation_hint": {"type": "string"},
        },
        "required": ["canonical_name", "disambiguation_hint", "evidence_sources"],
    },
)

REPO_ARCH_SCALED_SURVEY = Format(
    id="repo-architect.scaled-survey",
    name="RepoArchitectScaledSurvey",
    description=(
        "仓库规模评估 + 模块拓扑产出。"
        "【字段】complexity_score (0-100 整数), scale_level ∈ {quick, standard, deep}, "
        "estimated_modules (int), "
        "code_modules (真实代码模块列表, 每个 {path (相对 working_path), kind "
        "(python_package/js_package/rust_crate/go_module/dir), depth (1-3), "
        "file_count (仅源码), sub_packages (下钻子包名列表 可空), "
        "discovered_via (这个模块是凭哪个真实文件识别出来的, 例如 "
        "'<path>/__init__.py' 或 '<path>/Cargo.toml', 构成证据锚)}), "
        "top_source_root (识别出的主源码根目录, 例: src/omnicompany/ 或 lib/ 或仓库根)。"
        "【值域】scale_level 与 score 区间: <30→quick, 30-70→standard, >70→deep。"
        "code_modules[].kind 枚举来源: 存在 __init__.py=python_package; "
        "package.json=js_package; Cargo.toml=rust_crate; go.mod=go_module; 其他=dir。"
        "【上游承诺】repo_acquirer 已扫完文件树, repo_identity_anchor 已给出 ecosystem。"
        "【下游用途】mode_selector 看 scale_level 决定 mode; "
        "report_designer 读 code_modules 决定 focus_modules (第二层真实代码模块而非顶层目录); "
        "module_drafter 读 code_modules[].path 做深度分析。"
        "【不变量】code_modules 非空 (除非仓库没任何源码), "
        "每个 module 的 path 必须在 working_path 下真实存在。"
        "【反例】code_modules=['config', 'data', 'docs', 'logs', 'scripts', 'src'] "
        "← 只拿顶层目录, 没穿透到真实包。正例: "
        "code_modules=[{path:'src/omnicompany/core', kind:'python_package', depth:3, ...}, "
        "{path:'src/omnicompany/packages/services/knowledge', kind:'python_package', depth:5, ...}]"
    ),
    parent="repo-architect.repo-identity",
    tags=["domain.repo_architect", "stage.survey", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "complexity_score": {"type": "integer"},
            "scale_level": {"type": "string", "enum": ["quick", "standard", "deep"]},
            "code_modules": {"type": "array", "items": {"type": "object"}},
            "top_source_root": {"type": "string"},
        },
        "required": ["scale_level", "code_modules"],
    },
)

REPO_ARCH_MODE_SELECTED = Format(
    id="repo-architect.mode-selected",
    name="RepoArchitectModeSelected",
    description=(
        "模式确认输出。内容语义: 汇合规模评估 + 用户 (或 default 兜底) 的模式选择, 含 "
        "mode (quick/standard/deep) + report_style (concise/balanced/detailed) + "
        "research_enabled + focus_areas (字符串列表) + selection_status。验证标准: "
        "mode/report_style 枚举合法, research_enabled 是 bool, focus_areas 非空列表。"
        "下游用途: 这是第二阶段 (信息收集) 的公共输入, fanout 到 external_researcher / "
        "docs_reader / adaptive_interviewer 三个并行分支。"
    ),
    parent="repo-architect.scaled-survey",
    tags=["domain.repo_architect", "stage.mode", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["quick", "standard", "deep"]},
            "report_style": {"type": "string", "enum": ["concise", "balanced", "detailed"]},
            "research_enabled": {"type": "boolean"},
            "focus_areas": {"type": "array", "items": {"type": "string"}},
            "selection_status": {"type": "string"},
        },
        "required": ["mode", "focus_areas"],
    },
)


# ═══════════════════════════════════════════════════════════
# 阶段 2 信息收集 (三条并行分支)
# ═══════════════════════════════════════════════════════════

REPO_ARCH_RESEARCH_NOTES = Format(
    id="repo-architect.research-notes",
    name="RepoArchitectResearchNotes",
    description=(
        "仓库自述调研笔记 (RepoIntrospection, 不是真外部搜索)。"
        "【字段】research_notes (markdown 段落, 概述性文字), "
        "key_findings (要点列表, 每条形如 "
        "{text: '…', source: 'README.md:3-15'} — source 必须指向 working_path 下的"
        "真实文件+行号/段落, 不允许凭空写), "
        "sources (所有用到的文件路径列表, 是 key_findings.source 的去重并集), "
        "research_status (completed/degraded/skipped)。"
        "【上游承诺】repo_identity_anchor 的 canonical_name 已锚定, "
        "repo_introspection 只读 working_path 下文件, 严禁从项目名字推测。"
        "【下游用途】report_designer 读 key_findings 丰富外部视角段落; "
        "report_fuser 在报告中引用每条 finding 时必须带 source 指向原文。"
        "【不变量】若 status=completed, key_findings 非空且每条必须有 source 字段, "
        "source 指向的文件必须在 working_path 下真实存在。"
    ),
    parent="repo-architect.mode-selected",
    tags=["domain.repo_architect", "stage.gather", "branch.research", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "research_notes": {"type": "string"},
            "key_findings": {"type": "array", "items": {"type": "object"}},
            "sources": {"type": "array", "items": {"type": "string"}},
            "research_status": {"type": "string", "enum": ["completed", "degraded", "skipped"]},
        },
        "required": ["research_status"],
    },
)

REPO_ARCH_DOCS_SUMMARY = Format(
    id="repo-architect.docs-summary",
    name="RepoArchitectDocsSummary",
    description=(
        "文档摘要 + 设计决策证据清单。"
        "【字段】docs_summary (概述性文字, 不带内联引用), "
        "design_decisions (要点列表, 每条形如 "
        "{text: '本项目用 MIT 许可证', source: 'LICENSE:1' 或 "
        "'pyproject.toml:12'} — source 必须指向真实文件+行号), "
        "doc_coverage (实际读到的文档文件路径列表), "
        "status (success/no_docs/fallback_no_docs)。"
        "【上游承诺】working_path 可读, 身份锚已就位。"
        "【下游用途】report_designer 把 design_decisions 当报告'作者原意'段种子; "
        "report_fuser 渲染每条决策时必须带 source 指回原文件; "
        "module_drafter 读 docs_summary 辅助模块说明。"
        "【不变量】若 status=success, design_decisions 非空且每条必须有 source, "
        "doc_coverage 至少 1 个文件。"
    ),
    parent="repo-architect.mode-selected",
    tags=["domain.repo_architect", "stage.gather", "branch.docs", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "docs_summary": {"type": "string"},
            "design_decisions": {"type": "array", "items": {"type": "object"}},
            "doc_coverage": {"type": "array", "items": {"type": "string"}},
            "status": {"type": "string", "enum": ["success", "no_docs", "fallback_no_docs"]},
        },
        "required": ["status"],
    },
)

REPO_ARCH_USER_FOCUS_PROFILE = Format(
    id="repo-architect.user-focus-profile",
    name="RepoArchitectUserFocusProfile",
    description=(
        "用户焦点画像。内容语义: adaptive_interviewer 通过 UserInquiry 与用户 1-3 轮交互 "
        "(或降级版 interview_defaults 走默认值) 提炼出的细化关注点, 含 interview_responses "
        "(键值对) + refined_focus_areas (列表) + report_detail_preference (技术/业务/执行)。"
        "验证标准: refined_focus_areas 非空, report_detail_preference 枚举合法。下游用途: "
        "report_designer 用它决定报告章节的轻重缓急, 也写入 kb-entry 供以后同类查询匹配。"
    ),
    parent="repo-architect.mode-selected",
    tags=["domain.repo_architect", "stage.gather", "branch.focus", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "refined_focus_areas": {"type": "array", "items": {"type": "string"}},
            "report_detail_preference": {"type": "string"},
            "interview_responses": {"type": "object"},
        },
        "required": ["refined_focus_areas"],
    },
)


# ═══════════════════════════════════════════════════════════
# 阶段 3 报告骨架
# ═══════════════════════════════════════════════════════════

REPO_ARCH_REPORT_SKELETON = Format(
    id="repo-architect.report-skeleton",
    name="RepoArchitectReportSkeleton",
    description=(
        "报告骨架。内容语义: report_designer 综合 (research-notes + docs-summary + "
        "user-focus-profile) 设计出的报告结构模板, 含 sections (章节定义列表 含 "
        "title/required/estimated_length) + focus_modules (待深度分析的模块名列表) + "
        "mermaid_hints (需要生成的图类型)。验证标准: sections 非空 且每条含 title, "
        "focus_modules 非空且每个必须是仓库真实存在的目录/文件名。下游用途: 驱动 "
        "module_scatter 的分发 (focus_modules 决定起多少并行 leaf), 也给 report_fuser "
        "提供最终组装蓝图。"
    ),
    parent="requirement",
    tags=["domain.repo_architect", "stage.design", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "sections": {"type": "array", "items": {"type": "object"}},
            "focus_modules": {"type": "array", "items": {"type": "string"}},
            "mermaid_hints": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["sections", "focus_modules"],
    },
)


# ═══════════════════════════════════════════════════════════
# 阶段 4 并行深度分析 (SCATTER)
# ═══════════════════════════════════════════════════════════

REPO_ARCH_MODULE_DRAFT = Format(
    id="repo-architect.module-draft",
    name="RepoArchitectModuleDraft",
    description=(
        "单模块深度分析草稿,带证据链。"
        "【字段】"
        "module_name (working_path 下真实存在的目录相对路径), "
        "module_kind (python_package/rust_crate/…), "
        "analysis_sections (dict, 四个维度 architecture/responsibility/"
        "dependencies/interfaces, 每维度形如 "
        "{text: '自然语言分析 50-500 字', "
        "evidence_refs: [{file: 'src/foo/bar.py', lines: '12-45', "
        "claim: '此范围支撑了哪条具体断言'}]}), "
        "coverage_status ∈ {complete, partial, insufficient}, "
        "missing_aspects (列表, 每条说明'哪个维度缺什么证据', 例如 "
        "'dependencies: 只扫了 __init__.py 没读 _utils/_transform.py, "
        "可能漏掉 PropertyInfo 的真实出处'), "
        "evidence_files (本次实际读取的源码文件相对路径列表)。"
        "【上游承诺】focus_modules 里的每个 path 都在 code_modules 中存在且真实可读; "
        "disambiguation_hint 已锚定项目身份。"
        "【下游用途】draft_collector 做 schema 透传; "
        "cross_validator 做模块间一致性检查时必须基于 evidence_refs 而不是 text 字面; "
        "report_fuser 在报告每一段断言后渲染 evidence_refs 作为可点击引用, 让读者能回源码。"
        "【不变量】四维度都必须有 text (非空) 且都必须至少有 1 条 evidence_ref; "
        "evidence_refs[].file 必须在 evidence_files 中出现且在 working_path 下真实存在; "
        "missing_aspects 若空 → coverage_status=complete, "
        "若非空但证据还能说明大致轮廓 → partial, "
        "若四维度中有维度完全没 evidence → insufficient。"
        "【反模式】不允许 LLM 给出'coverage_score: 95'这种数值打分,"
        "全部用 status + 明确的 missing_aspects 语义表达。"
    ),
    parent="requirement",
    tags=["domain.repo_architect", "stage.analyze", "scatter.leaf", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "module_name": {"type": "string"},
            "module_kind": {"type": "string"},
            "analysis_sections": {"type": "object"},
            "coverage_status": {"type": "string", "enum": ["complete", "partial", "insufficient"]},
            "evidence_files": {"type": "array", "items": {"type": "string"}},
            "missing_aspects": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["module_name", "coverage_status"],
    },
)

REPO_ARCH_DRAFT_SET = Format(
    id="repo-architect.draft-set",
    name="RepoArchitectDraftSet",
    description=(
        "模块草稿集合。"
        "【字段】total_modules (int), drafts (合法 module-draft 数组, 每条必须含 "
        "evidence_refs 和 coverage_status), failed_modules (分析失败的模块, 每条 "
        "{module, reason}), analysis_status ∈ {all_success, partial, all_failed}。"
        "【不变量】total_modules == len(drafts) + len(failed_modules); "
        "drafts 里每条 module-draft 都必须满足 module-draft Format 的 evidence 不变量。"
        "【下游用途】coverage_gater 基于 drafts[*].coverage_status 决定 retry, "
        "cross_validator 做一致性检查, 两者都禁止依赖数值分数。"
    ),
    parent="requirement",
    tags=["domain.repo_architect", "stage.collect", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "total_modules": {"type": "integer"},
            "drafts": {"type": "array", "items": {"type": "object"}},
            "failed_modules": {"type": "array", "items": {"type": "object"}},
            "analysis_status": {"type": "string", "enum": ["all_success", "partial", "all_failed"]},
        },
        "required": ["total_modules", "analysis_status"],
    },
)


# ═══════════════════════════════════════════════════════════
# 阶段 5 质量门 / 交叉验证
# ═══════════════════════════════════════════════════════════

REPO_ARCH_COVERAGE_FEEDBACK = Format(
    id="repo-architect.coverage-feedback",
    name="RepoArchitectCoverageFeedback",
    description=(
        "覆盖率回环反馈 (基于 status 而非数值)。"
        "【字段】gate_status ∈ {pass, retry, fail} (pass: 所有 draft "
        "coverage_status=complete 或 partial; retry: 有 insufficient 且 retry_count<3; "
        "fail: retry 耗尽仍有 insufficient), "
        "insufficient_modules (status=insufficient 的模块名列表), "
        "partial_modules (status=partial 的模块名列表), "
        "retry_count (<= 3), feedback_message (简要说明为什么 retry 或 fail)。"
        "【不变量】retry 状态必须 insufficient_modules 非空; pass 状态允许 partial_modules 非空。"
        "【下游用途】retry → module_drafter 对 insufficient 模块重跑; "
        "pass → validated-drafts; fail → 整条管线 HALT 上报。"
        "【反模式】禁止输出数值 coverage percentage, 只用 complete/partial/insufficient 三档。"
    ),
    parent="requirement",
    tags=["domain.repo_architect", "stage.gate", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "gate_status": {"type": "string", "enum": ["pass", "retry", "fail"]},
            "insufficient_modules": {"type": "array", "items": {"type": "string"}},
            "partial_modules": {"type": "array", "items": {"type": "string"}},
            "retry_count": {"type": "integer"},
            "feedback_message": {"type": "string"},
        },
        "required": ["gate_status"],
    },
)

REPO_ARCH_VALIDATED_DRAFTS = Format(
    id="repo-architect.validated-drafts",
    name="RepoArchitectValidatedDrafts",
    description=(
        "通过质量门的草稿集。"
        "【字段】validated_drafts (coverage_status ∈ {complete, partial} 的 drafts), "
        "overall_status ∈ {complete, mixed} (complete: 全部 draft complete; "
        "mixed: 含 partial), "
        "aggregated_missing_aspects (所有 draft 的 missing_aspects 合并去重, "
        "供 report_fuser 在报告最后'覆盖率缺口'段渲染), "
        "passed_at_retry (第几轮通过 gate)。"
        "【下游用途】cross_validator 做模块间一致性检查; report_fuser 融合成最终报告 "
        "且**必须**渲染 aggregated_missing_aspects 让读者看到哪里不齐全。"
    ),
    parent="repo-architect.draft-set",
    tags=["domain.repo_architect", "stage.gated", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "validated_drafts": {"type": "array", "items": {"type": "object"}},
            "overall_status": {"type": "string", "enum": ["complete", "mixed"]},
            "aggregated_missing_aspects": {"type": "array", "items": {"type": "string"}},
            "passed_at_retry": {"type": "integer"},
        },
        "required": ["overall_status"],
    },
)

REPO_ARCH_CROSS_VALIDATION = Format(
    id="repo-architect.cross-validation",
    name="RepoArchitectCrossValidation",
    description=(
        "模块间交叉验证结果 (每条不一致必须带上游证据链)。"
        "【字段】validation_status ∈ {consistent, warning, inconsistent}, "
        "inconsistencies (列表, 每条 {module_pair: [a_path, b_path], issue_type, "
        "detail, suggestion, evidence_upstream: "
        "[{from_node: 'module_drafter', draft_module: 'src/foo', "
        "section: 'dependencies', quoted_text: '依赖 PropertyInfo 符号', "
        "evidence_ref: {file, lines}}, ...]} — evidence_upstream 把判定所依据的"
        "上游声明**精确链接**回是哪个 draft 的哪段文本 + 它自己的 evidence_ref, "
        "这样下游发现误判时可沿链追溯到责任节点), "
        "cross_reference_map (dict: module_path → [其他被引用的 module_path])。"
        "【不变量】inconsistent/warning 状态时 inconsistencies 必须非空, "
        "且每条 inconsistency 必须有 evidence_upstream 非空 "
        "(空意味着 cross_validator 凭空下结论)。"
        "【下游用途】report_fuser 渲染不一致章节时必须把 evidence_upstream 一起带出, "
        "让读者点击就能跳到 module_drafter 的原始断言。"
    ),
    parent="requirement",
    tags=["domain.repo_architect", "stage.cross_check", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "validation_status": {"type": "string", "enum": ["consistent", "warning", "inconsistent"]},
            "inconsistencies": {"type": "array", "items": {"type": "object"}},
            "cross_reference_map": {"type": "object"},
        },
        "required": ["validation_status"],
    },
)


# ═══════════════════════════════════════════════════════════
# 阶段 6 融合发布
# ═══════════════════════════════════════════════════════════

REPO_ARCH_ARCH_REPORT = Format(
    id="repo-architect.arch-report",
    name="RepoArchitectArchReport",
    description=(
        "最终架构报告 (markdown, 带可追溯证据链)。"
        "【字段】report_path (落到 data/absorption/reports/<id>.md), report_chars, "
        "mermaid_diagrams (数量), sections_fulfilled (章节列表), "
        "overall_status (complete/mixed, 透传自 validated-drafts)。"
        "【报告正文不变量】每一个模块职责段落末尾必须渲染 evidence_refs 为可读脚注 "
        "(例: '— evidence: src/foo/__init__.py:1-20, src/foo/bar.py:44'), "
        "每一条 design_decision 必须带 source 文件引用, "
        "'覆盖率缺口' 段落必须列出 aggregated_missing_aspects, "
        "'一致性问题' 段落每条必须展示 evidence_upstream 让读者回溯。"
        "【反模式】不要写 'overall coverage: 95%' 类数值分数, 只写 complete/mixed。"
    ),
    parent="requirement",
    tags=["domain.repo_architect", "stage.deliver", "output.user_facing", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "report_path": {"type": "string"},
            "report_chars": {"type": "integer"},
            "mermaid_diagrams": {"type": "integer"},
            "sections_fulfilled": {"type": "array", "items": {"type": "string"}},
            "overall_status": {"type": "string", "enum": ["complete", "mixed"]},
        },
        "required": ["report_path", "overall_status"],
    },
)

REPO_ARCH_COVERAGE_REPORT = Format(
    id="repo-architect.coverage-report",
    name="RepoArchitectCoverageReport",
    description=(
        "覆盖率汇总报告 (语义状态而非百分比)。"
        "【字段】coverage_report_path (落到 data/absorption/coverage/<id>.md), "
        "module_status_table (每模块 {name, status, missing_aspects, evidence_file_count}), "
        "skipped_modules, overall_status (complete/mixed)。"
        "【正文不变量】markdown 表格列是 Module / Status / Missing Aspects / Evidence Files, "
        "禁止出现 0-100 数字打分。"
        "【下游用途】用户可信度参考 + kb_ingester 写入 KB 时作为'证据力度'元数据。"
    ),
    parent="requirement",
    tags=["domain.repo_architect", "stage.deliver", "output.quality_evidence", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "coverage_report_path": {"type": "string"},
            "module_status_table": {"type": "array", "items": {"type": "object"}},
            "skipped_modules": {"type": "array", "items": {"type": "string"}},
            "overall_status": {"type": "string", "enum": ["complete", "mixed"]},
        },
        "required": ["overall_status"],
    },
)

REPO_ARCH_KB_ENTRY = Format(
    id="repo-architect.kb-entry",
    name="RepoArchitectKBEntry",
    description=(
        "OmniKB 知识条目。内容语义: kb_ingester 把最终 arch-report + coverage-report "
        "转成的 KRepoArchitectEntry (OmniKB 中的 krepo 类型), 含 entry_id + "
        "capability_areas (已识别的能力域列表) + omni_parallels (和 OmniCompany 现有"
        "模块的对应关系) + component_index (主要组件 → 文件路径映射)。验证标准: "
        "entry_id 符合 OmniKB ID 规范, capability_areas 非空, omni_parallels 允许空待填。"
        "frontmatter 使用 overall_status (complete/mixed) 而非 overall_coverage 百分比。"
        "下游用途: 写入 data/knowledge/external_repos/<entry_id>.md, 通过 OmniKB 索引"
        "向后续相似 repo 的分析提供跨仓库对齐。这是 absorption 循环的最终沉淀点。"
    ),
    parent="repo-architect.arch-report",
    tags=["domain.repo_architect", "stage.ingest", "output.kb", "kind.sink"],
    json_schema={
        "type": "object",
        "properties": {
            "entry_id": {"type": "string"},
            "capability_areas": {"type": "array", "items": {"type": "string"}},
            "omni_parallels": {"type": "array", "items": {"type": "object"}},
            "component_index": {"type": "object"},
        },
        "required": ["entry_id", "capability_areas"],
    },
)


ALL_FORMATS: list[Format] = [
    REPO_ARCH_INPUT,
    REPO_ARCH_ACQUIRED_REPO,
    REPO_ARCH_REPO_IDENTITY,
    REPO_ARCH_SCALED_SURVEY,
    REPO_ARCH_MODE_SELECTED,
    REPO_ARCH_RESEARCH_NOTES,
    REPO_ARCH_DOCS_SUMMARY,
    REPO_ARCH_USER_FOCUS_PROFILE,
    REPO_ARCH_REPORT_SKELETON,
    REPO_ARCH_MODULE_DRAFT,
    REPO_ARCH_DRAFT_SET,
    REPO_ARCH_COVERAGE_FEEDBACK,
    REPO_ARCH_VALIDATED_DRAFTS,
    REPO_ARCH_CROSS_VALIDATION,
    REPO_ARCH_ARCH_REPORT,
    REPO_ARCH_COVERAGE_REPORT,
    REPO_ARCH_KB_ENTRY,
]


def register_formats(registry: FormatRegistry) -> None:
    """把 repo_architect domain 的 Format 注册到全局 FormatRegistry。"""
    for fmt in ALL_FORMATS:
        if not registry.is_registered(fmt.id):
            registry.register(fmt)
