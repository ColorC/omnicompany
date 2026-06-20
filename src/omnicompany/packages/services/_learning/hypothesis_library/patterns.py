# [OMNI] origin=claude-code domain=services/hypothesis_library/patterns ts=2026-04-27T00:00:00Z type=data
# [OMNI] material_id="material:services.learning.hypothesis_library.verification_patterns.py"
"""5 条现成验证模式 · 从 OmniCompany 已跑通的现有团队提取.

每条模式记录其源团队 + 适用产物形态 + 验证模板. 真 meta 层用作"现成参考".
"""
from __future__ import annotations

from .hypothesis import Hypothesis


P_BYTE_DIFF_ACCEPTANCE = Hypothesis(
    id="byte_diff_acceptance",
    description=(
        "好的代码产物 (有 ground truth 的) 应当跟标杆字节级一致. byte_diff = 0 是 binary 信号 "
        "(过 = 真过, 不过 = 真不过), 不存在模糊."
    ),
    when_applicable=(
        "代码产物有人写的 / 历史 / 标杆 expected 文件可对标. "
        "csv-to-md / config_table生成 / 翻译 (有 GT) / 测试代码 (有 expected) 都该用. "
        "不适用 LLM 自由文本产物 (没标杆) 或带随机性的产物 (UUID / 时间戳类)."
    ),
    verification_template=(
        "1. 准备 fixtures: input + expected_path 两边对齐 (人工 / 历史快照). "
        "2. 跑 target(input), 拿 actual. "
        "3. 比 actual 和 expected 文件字节: 全等 → PASS, 不等 → FAIL + 报 diff_count + diff_lines. "
        "4. (进阶) 多组 fixtures 算 byte_exact_pct, 阈值视严格度定 (1.0 严要求 / 0.9 容错)."
    ),
    examples=(
        "csv-to-md: tests/teams/csv_to_md/test_contract.py · 6 条契约 · byte_exact_pct=1.0",
        "gameplay_system config_table: SDK process_*.py 跑 csv 跟 MainBranch baseline 字节比",
        "翻译: ts_phase1 跑出 .ts 跟人写 GT 字节比 (lang-rewrite)",
    ),
    category="pattern",
    provenance=(
        "src/omnicompany/packages/services/code_runtime_test/workers/golden_runner.py + "
        "tests/teams/csv_to_md/test_contract.py"
    ),
)


P_REFERENCE_EXISTENCE = Hypothesis(
    id="reference_existence",
    description=(
        "好的提案/报告里所有 file/line/func 引用应当在源仓库真实存在. 这是诚实假设 "
        "(`H_HONEST`) 在 absorption 类工作的具体落地."
    ),
    when_applicable=(
        "凡产物结构含 reference_code.{file, line, snippet} 类引用字段都用. "
        "absorption / repo_architect / 代码 review 报告 / debugger 假设. "
        "不适用纯算法描述 (无文件锚点)."
    ),
    verification_template=(
        "1. 扫产物的 references 字段集合 (e.g. proposals[].reference_code.file). "
        "2. 对每条 ref: Path(repo_path / ref.file).is_file() ? "
        "3. 若有 line: 读那行真在文件里 (1-indexed). "
        "4. 若有 snippet: substring match 是否真在文件那行附近. "
        "5. 命中率高 → 诚实, 低 → LLM 编造."
    ),
    examples=(
        "absorption ReportAssembler: 提案的 reference_code.file 必须 repo 真有",
        "review 报告: 评论的 file:line 必须 PR 真改过",
        "debugger 假设: 假设说'bug 在 X 行' → X 行真存在",
    ),
    category="pattern",
    provenance=(
        "src/omnicompany/packages/services/repo_absorption/workers/report_assembler.py · "
        "P-13 + memory feedback_no_blind_guess_use_eventbus"
    ),
)


P_FIVE_ELEMENT_CHECK = Hypothesis(
    id="five_element_check",
    description=(
        "Material 健康度可程序化扫 5 要素: id 命名 / parent 指向 / json_schema 完整 / "
        "description 信息量 / tags 规整. 5 要素全过 = A 级, 缺 1-2 = B-D, 缺核心 = F."
    ),
    when_applicable=(
        "凡产物是 Material 定义 (formats.py 里) 都用. "
        "包括 team_builder 产的 Material / 手写的 Material / 任何注册到 FormatRegistry 的. "
        "不适用非结构化产物 (markdown 报告 / LLM 自由文本)."
    ),
    verification_template=(
        "对每个 Material 实例: "
        "1. id 非空 + 命名规则 (snake_case, domain.name); "
        "2. parent 在已注册 Material set 里; "
        "3. json_schema 是 dict, 含 type/properties/required; "
        "4. description ≥150 字 + 含 '消费' '生产' 关键词; "
        "5. tags 含 kind.* (source / internal / sink) + domain. "
        "5/5 → A; 缺非核心 → B-D; 缺 id/parent → F."
    ),
    examples=(
        "doctor: omni run material-diagnosis --material_id <X> 跑出 grade",
        "Guardian OMNI-027: Material 注册前的 schema 校验 (硬规则)",
        "Material 重命名后扫: 旧 id 应被新 id 顶替, 旧 id 不在 ALL_MATERIALS",
    ),
    category="pattern",
    provenance=(
        "src/omnicompany/packages/services/doctor/ + "
        "memory feedback_static_check_ast_not_string · ast.walk 扫 formats.py"
    ),
)


P_DIRECTORY_HYGIENE = Hypothesis(
    id="directory_hygiene",
    description=(
        "好产物 (代码 / 文档 / 数据) 应符合目录卫生规则: 不在禁区 / 不混入临时文件 / "
        "不污染共享空间. 这是 'observable + organized' 的具体形式."
    ),
    when_applicable=(
        "凡产物在文件系统落地都用 (生成的代码 / 报告 / 落盘的 trace / 临时产物). "
        "项目级铁律: data/domains/ 严禁堆 scratch 杂物 / src/ 禁散文 .md. "
        "不适用纯网络服务产物 (无落地)."
    ),
    verification_template=(
        "Guardian 卫生规则集 (扫码) + 各 OMNI-*** 守: "
        "1. PROGRESS.md 唯一 docs/PROGRESS.md (OMNI-???); "
        "2. src/ 禁 NOTES/TODO 散文; "
        "3. _scratch/ 禁提 scm; "
        "4. 临时跑产物落 e:/tmp/ 不入 repo; "
        "5. data/_runtime/ 必走 EventBus 不直写文件. "
        "全过 → 卫生; 任违 → 失分."
    ),
    examples=(
        "guardian patrol: 一键扫所有规则",
        "memory feedback_directory_hygiene_strict: data/domains 严禁堆杂物",
        "memory feedback_scm_not_personal_scratch: scm 禁交个人 scratch",
    ),
    category="pattern",
    provenance=(
        "src/omnicompany/packages/services/guardian/rules/* + "
        "memory feedback_directory_hygiene_strict"
    ),
)


P_RED_LINE_CHECK = Hypothesis(
    id="red_line_check",
    description=(
        "硬性禁令 (铁律) 的违反应被程序化捕到 — 不是 'LLM 自觉' 不是 'review 后人脑判'. "
        "代码产物撞铁律 = bug, 没有灰区."
    ),
    when_applicable=(
        "凡有铁律的领域 (LLM 不预防截断 / 单模型 qwen3.6-plus / EventBus 必走 / "
        "禁打分标签 / agent loop 必挂 bus / etc.) 都用. 适用代码产物 + Material 定义."
    ),
    verification_template=(
        "对每条铁律, 写 ast.walk 扫具体语法模式: "
        "1. 截断: ast 找 Subscript+Slice (text[:N]) on str/list 喂给 LLM 调用 — 标记; "
        "2. 模型: ast 找 model='claude*' 'opus' 'sonnet' — 标记; "
        "3. EventBus: 找 AgentNodeLoop 子类 ALLOW_NO_BUS=True 但又有 LLM 调用 — 标记; "
        "4. 打分: 找 score / level / tier / kind 字段在 schema — 标记. "
        "0 标记 → 过红线; ≥1 → 报具体违反位置."
    ),
    examples=(
        "lap_auditor: 扫 LAP 六元接口符合度",
        "memory feedback_no_defensive_truncation: 必扫 [:N] 模式",
        "memory feedback_static_check_ast_not_string: 用 AST 扫不用 string substring",
        "Guardian OMNI-034: DESIGN.md 7 节结构硬扫 (active/design 必备)",
    ),
    category="pattern",
    provenance=(
        "src/omnicompany/packages/services/lap_auditor/ + "
        "src/omnicompany/packages/services/guardian/rules/ + "
        "memory feedback_no_defensive_truncation + feedback_static_check_ast_not_string"
    ),
)


PATTERNS: tuple[Hypothesis, ...] = (
    P_BYTE_DIFF_ACCEPTANCE,
    P_REFERENCE_EXISTENCE,
    P_FIVE_ELEMENT_CHECK,
    P_DIRECTORY_HYGIENE,
    P_RED_LINE_CHECK,
)
