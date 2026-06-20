# [OMNI] origin=team_builder domain=services/repo_absorption/formats ts=2026-04-25T00:00:00Z type=config
# [OMNI] material_id="material:learning.repo.absorption.material_definitions.registry.py"
"""repo_absorption Team · Material 定义 (团队 builder 自动产出).

Material description 五要素: 内容语义 / 字段含义 / 上游承诺 / 下游用途 / 最小样例.
"""
from __future__ import annotations

from omnicompany.packages.services._core.omnicompany import Material
from omnicompany.protocol.format import FormatRegistry

M_REPO_ABSORPTION_SCAN_CONFIG = Material(
    id='repo_absorption.scan_config',
    name='repo_absorption.scan_config',
    description="repo_absorption 管线的入口级配置事件，由外部触发器（CLI 或编排层）一次性注入。它不是中间产物，而是整条管线的启动参数——告诉团队「扫哪个仓库」以及「选出前几个关键模块」。作为 source 类 material，它没有 producer Worker，而是由管线调度器或用户直接提供，供第一个 HARD 节点 RepoScannerWorker 读取后驱动后续扫描与筛选。 repo_path (string): 待扫描仓库的本地文件系统根目录绝对路径，例如 '/home/user/repos/some-library'，必须指向一个真实存在且可读的目录。top_n (integer): 经扫描后 ModuleSelectorWorker 需要筛选保留的关键模块数量上限，≥1 的正整数；若 top_n < 3 则触发 ModuleSelectorWorker 的边界阈值兜底逻辑（见 Worker 设计）. 此 material 的 producer 是外部触发器（非 Worker），上游承诺两点：① repo_path 字段必须是合法存在的本地目录路径（不是 URL 或占位符），且该目录下至少包含若干 .py 文件，否则 RepoScannerWorker 将产出空索引并导致管线短路；② top_n 必须是 ≥1 的整数，若为 0 或负数则违反前置约束。两字段均为 required，缺一不可。 RepoScannerWorker 作为首个消费者，读取 repo_path 作为安全遍历的根目录，递归枚举 .py 文件并通过 stat 提取行数与大小，输出结构化文件索引。ModuleSelectorWorker 作为第二个消费者，读取 top_n 作为 LLM 智能筛选的阈值——对 RepoScannerWorker 产出的文件索引按复杂度评分后保留 top_n",
    parent='doc',
    json_schema={'type': 'object', 'properties': {'repo_path': {'type': 'string', 'description': '待扫描仓库的本地根目录路径，必须为存在的目录'}, 'top_n': {'type': 'integer', 'description': '模块筛选数量上限，≥1 的正整数', 'minimum': 1}}, 'required': ['repo_path', 'top_n']},
    tags=['repo_absorption', 'generated', 'kind.source'],
)

M_REPO_ABSORPTION_FILE_INVENTORY = Material(
    id='repo_absorption.file_inventory',
    name='repo_absorption.file_inventory',
    description='RepoScannerWorker 对指定 repo_path 执行安全遍历后产出的 .py 文件结构化索引，是 repo_absorption 管线第一个确定性产物。每条记录包含文件的相对路径、行数和字节体积，下游据此做智能筛选与源码读取规划，不含任何文件内容本身。 repo_path 是扫描根路径（与输入逐字节一致）；top_n 是从输入透传的提案数上限；generated_at 是扫描完成的 ISO8601 时间戳；total_files 是扫描到的 .py 文件总数（等于 files 数组长度）；files 是文件清单数组，每项包含 rel_path（相对于 repo_path 的路径，下游用 Path(repo_path)/rel_path 定位真实文件）、line_count（统计行数，供 ModuleSelectorWorker 评估复杂度）、size_bytes（文件字节体积，供 SourceReaderWorker 判断是否需要分片读取）。 RepoScannerWorker 承诺：仅枚举 .py 文件且已过滤 __pycache__ 等标准忽略项；每个 files 条目的 rel_path 在 repo_path 下真实存在；line_count 通过实际读取或 stat 精确计算；total_files 与 files 数组长度严格一致；若 repo_path 不存在则在进入此节点前已被 upstream 截断并返回 FAIL，不会产出空文件清单。 ModuleSelectorWorker 读取 files 数组按 line_count/size_bytes 评估复杂度与结构特征，结合 top_n 筛选关键模块交给下游；SourceReaderWorker 根据 files[].rel_path 和 size_bytes 决定是否分片读取（>1MB）；',
    parent='requirement',
    json_schema={'type': 'object', 'properties': {'repo_path': {'type': 'string', 'description': '要吸纳的代码仓路径（与用户输入逐字节一致）'}, 'top_n': {'type': 'integer', 'minimum': 1, 'default': 5, 'description': '提案数上限，从输入透传'}, 'generated_at': {'type': 'string', 'description': '扫描完成的 ISO8601 时间戳'}, 'total_files': {'type': 'integer', 'minimum': 0, 'description': '扫描到的 .py 文件总数'}, 'files': {'type': 'array', 'description': '全量 .py 文件清单', 'items': {'type': 'object', 'properties': {'rel_path': {'type': 'string', 'description': '相对于 repo_path 的文件路径（如 core/engine.py）'}, 'line_count': {'type': 'integer', 'minimum': 0, 'description': '文件总行数'}, 'size_bytes': {'type': 'integer', 'minimum': 0, 'description': '文件字节体积'}}, 'required': ['rel_path', 'line_count', 'size_bytes']}}}, 'required': ['repo_path', 'total_files', 'files']},
    tags=['repo_absorption', 'generated', 'kind.internal'],
)

M_REPO_ABSORPTION_SELECTED_MODULES = Material(
    id='repo_absorption.selected_modules',
    name='repo_absorption.selected_modules',
    description="这是 RepoScannerWorker 完成全仓 .py 文件枚举后, ModuleSelectorWorker 基于 LLM 对各文件复杂度与结构特征的综合评估, 从中智能筛选出的 top_n 个最关键模块路径列表。每个条目携带行数/大小/复杂度评分及选中理由, 构成从 '全量扫描索引' 到 '精准深度阅读' 的承上启下枢纽。 repo_path (透传被扫描仓库根路径, 供下游拼接绝对路径); total_files_scanned (RepoScanner 枚举到的 .py 文件总数, 反映筛选基数); selected_modules (数组, 每项含 relative_path 相对路径 + line_count 行数 + size_bytes 字节大小 + complexity_score LLM 复杂度评分 0-100 + selection_reason 选中理由一句话); selection_criteria (筛选策略简述)。selected_modules 数组按 complexity_score 降序排列, 长度受 top_n 上限约束但允许少于 top_n (边界场景)。 ModuleSelectorWorker 承诺: (1) selected_modules 非空 (minItems=1), 即使 top_n 很大也会选出至少 1 个模块; (2) 每条 relative_path 相对于 repo_path 真实存在且为 .py 文件; (3) line_count 和 size_bytes 数值与 RepoScannerWorker 原始扫描结果一致; (4) complexity_score 在 0-100 范围内且数组按该值降序; (5) selection_reason 为非空字符串 (≥10 字符) 说明筛选依据; (6) 若 t",
    parent='doc',
    json_schema={'type': 'object', 'properties': {'repo_path': {'type': 'string', 'description': '被扫描的仓库根路径 (透传自输入, 用于下游定位文件)'}, 'total_files_scanned': {'type': 'integer', 'minimum': 0, 'description': 'RepoScannerWorker 枚举的 .py 文件总数'}, 'selected_modules': {'type': 'array', 'minItems': 1, 'items': {'type': 'object', 'properties': {'relative_path': {'type': 'string', 'description': '模块文件相对于 repo_path 的相对路径, 例如 protocol/format.py'}, 'line_count': {'type': 'integer', 'minimum': 1, 'description': '该文件的总行数 (由 RepoScanner stat 提取)'}, 'size_bytes': {'type': 'integer', 'minimum': 1, 'description': '该文件的字节大小'}, 'complexity_score': {'type': 'integer', 'minimum': 0, 'maximum': 100, 'description': 'LLM 评估的复杂度评分, 用于优先级排序 (越高越关键)'}, 'selection_reason': {'type': 'string', 'minLength': 10, 'description': '一句话说明该模块被选中的理由 (结构性特征或模式价值)'}}, 'required': ['relative_path', 'line_count', 'complexity_score', 'selection_reason']}, 'description': '经 LLM 优先级排序后选中的目标模块列表, 按 complexity_score 降序排列'}, 'selection_criteria': {'type': 'string', 'description': "本次筛选采用的策略简述, 例如 'top_n 优先 + 核心包穿透'"}}, 'required': ['repo_path', 'selected_modules']},
    tags=['repo_absorption', 'generated', 'kind.internal'],
)

M_REPO_ABSORPTION_MODULE_SOURCES = Material(
    id='repo_absorption.module_sources',
    name='repo_absorption.module_sources',
    description="SourceReaderWorker 对 ModuleSelectorWorker 选中模块执行全量读取后的产物，携带每个模块的无截断完整源码（严禁预防性截断）及配套元数据（行数、字节数、相对路径），是 PatternExtractorWorker 进行代码模式分析和 PRO-NNN 改进提案提取的唯一真相来源。 module_count: 成功读取的模块总数（≥1）；modules: 数组，每项含 module_path（相对 repo_path 的文件路径）、content（Path.read_text 全文，禁止 :N 截断）、line_count（换行分割行数）、byte_size（UTF-8 编码字节数）；repo_path: 读取根路径透传，便于下游做真实性校验时拼接完整文件路径。 SourceReaderWorker 承诺：每个 module_path 均源自 ModuleSelectorWorker 的选中列表；content 通过 Path.read_text(encoding='utf-8') 完整读取，遵守铁律 A（无预防性截断，>1MB 才分片）；line_count 由 content.splitlines() 准确计算；若文件读取失败则标记跳过但不伪造内容。 PatternExtractorWorker 遍历 modules 数组，将 content 作为 LLM 分析输入以提炼改进点；reference_code.file 字段必须与某个 module_path 一致；reference_code.snippet 必须能在对应 content 中找到；reference_code.line_start 必须对齐 content.splitlines() 的真实行号。RepoAssemblerWorker 也可能消费此 material 做最终真",
    parent='doc',
    json_schema={'type': 'object', 'properties': {'module_count': {'type': 'integer', 'minimum': 1, 'description': '选中并成功读取的模块总数'}, 'modules': {'type': 'array', 'minItems': 1, 'items': {'type': 'object', 'properties': {'module_path': {'type': 'string', 'description': '模块文件相对 repo_path 的路径'}, 'content': {'type': 'string', 'description': "无截断完整源码，通过 Path.read_text(encoding='utf-8') 读取"}, 'line_count': {'type': 'integer', 'minimum': 1, 'description': '源码总行数（按换行符分割）'}, 'byte_size': {'type': 'integer', 'minimum': 0, 'description': '源码字节数（UTF-8 编码）'}}, 'required': ['module_path', 'content', 'line_count']}}, 'repo_path': {'type': 'string', 'description': '本次读取所依据的代码仓根路径，与输入一致'}}, 'required': ['module_count', 'modules']},
    tags=['repo_absorption', 'generated', 'kind.internal'],
)

M_REPO_ABSORPTION_EXTRACTION_RESULTS = Material(
    id='repo_absorption.extraction_results',
    name='repo_absorption.extraction_results',
    description="PatternExtractorWorker 深度分析完整源码后的中间分析产物。包含结构化提案数组（每条提案带 PRO-NNN 标识、问题陈述、改进方向、风险评级和逐字参考锚点），以及源码模式识别结果（identified_patterns 和 module_summaries）。这是 '提取真实代码模式，生成带逐字参考锚点与风险评级的提案' 的产物，遵守 F-15 诚实声明（所有 reference_code 必须锚定到真实文件真实行）。 proposals[]: 改进提案列表，每条含 id (PRO-NNN 格式)、title (≥8 字)、problem (≥30 字问题陈述)、proposed_change (≥30 字改进方向)、reference_code {file: 相对路径必须真实存在, line_start: 1-indexed 行号, snippet: 逐字代码片段}、risk (≥15 字风险评估)。source_analysis_context.identified_patterns: 从源码中提取的代码模式描述列表。source_analysis_context.module_summaries[]: 被分析模块的职责摘要 {file_path, role_summary, complexity_note?}。analysis_metadata: 分析元数据 {repo_path, files_analyzed, total_lines?, top_n}。 PatternExtractorWorker 承诺: (1) proposals 数量 ≥ 3 且 ≤ top_n; (2) 每条 proposal 的 reference_code.file 在 repo_path 下真实存在 (is_file); (3) snippet 首行非空且在对应文",
    parent='doc',
    json_schema={'type': 'object', 'properties': {'proposals': {'type': 'array', 'minItems': 3, 'items': {'type': 'object', 'properties': {'id': {'type': 'string', 'pattern': '^PRO-\\d{3}$', 'description': '提案唯一标识, 形如 PRO-001, 递增不重复'}, 'title': {'type': 'string', 'minLength': 8, 'description': '提案标题, 简要概括改进方向'}, 'problem': {'type': 'string', 'minLength': 30, 'description': '问题陈述, 描述当前代码中存在的具体问题'}, 'proposed_change': {'type': 'string', 'minLength': 30, 'description': '改进方向, 说明建议如何修改或优化'}, 'reference_code': {'type': 'object', 'properties': {'file': {'type': 'string', 'description': '引用源码文件的相对路径, 必须真实存在于 repo_path 下'}, 'line_start': {'type': 'integer', 'minimum': 1, 'description': '引用片段起始行号 (1-indexed), 必须落在真实文件范围内'}, 'line_end': {'type': 'integer', 'minimum': 1, 'description': '引用片段结束行号 (1-indexed), 可选但应与 snippet 范围一致'}, 'snippet': {'type': 'string', 'description': '逐字引用代码片段, 首行必须在该文件真实内容中出现'}}, 'required': ['file', 'line_start', 'snippet']}, 'risk': {'type': 'string', 'minLength': 15, 'description': '实施风险评估, 描述改动可能带来的副作用或破坏性'}}, 'required': ['id', 'title', 'problem', 'proposed_change', 'reference_code', 'risk']}}, 'source_analysis_context': {'type': 'object', 'properties': {'identified_patterns': {'type': 'array', 'items': {'type': 'string'}, 'description': '从源码中提取的代码模式描述列表, 如设计模式/反模式/架构特征'}, 'module_summaries': {'type': 'array', 'items': {'type': 'object', 'properties': {'file_path': {'type': 'string', 'description': '模块文件相对路径'}, 'role_summary': {'type': 'string', 'description': '该模块的职责概述'}, 'complexity_note': {'type': 'string', 'description': '复杂度备注, 可选'}}, 'required': ['file_path', 'role_summary']}, 'description': '被分析模块的职责摘要列表'}}, 'required': ['identified_patterns']}, 'analysis_metadata': {'type': 'object', 'properties': {'repo_path': {'type': 'string', 'description': '被分析的仓库路径 (透传自输入)'}, 'files_analyzed': {'type': 'integer', 'minimum': 1, 'description': '实际读取并分析的 .py 文件数量'}, 'total_lines': {'type': 'integer', 'minimum': 0, 'description': '所有被分析文件的总行数'}, 'top_n': {'type': 'integer', 'minimum': 1, 'description': '提案数上限 (透传自输入)'}}, 'required': ['repo_path', 'files_analyzed']}}, 'required': ['proposals', 'source_analysis_context', 'analysis_metadata']},
    tags=['repo_absorption', 'generated', 'kind.internal'],
)

M_REPO_ABSORPTION_SINK_REPORT = Material(
    id='repo_absorption.sink_report',
    name='repo_absorption.sink_report',
    description="这是 repo_absorption 管线的终态 Sink 产物，由 ReportAssemblerWorker 将 PatternExtractorWorker 产出的带参考锚点的改进提案与≥500字的综合分析报告组装而成的最终交付物。它严格遵循'真实锚点'铁律——每条提案的 reference_code.file 必须真实存在于被分析的仓库中，reference_code.snippet 必须是从真文件逐字读出的代码片段，绝不虚构。 顶层仅两个字段：(1) report_markdown 是字符串型综合报告，≥500字符，必须包含'## 仓库一览'、'## 关键模式'、'## 提案总览'三个二级章节标题；(2) proposals 是数组，最少3条、最多top_n条，每条包含 id(PRO-NNN格式)、title(≥8字符标题)、problem(≥30字符问题陈述)、proposed_change(≥30字符改进方向)、reference_code(嵌套对象含 file相对路径/line_start起始行号/line_end可选结束行号/snippet代码片段)、risk(≥15字符风险评估)。reference_code 中 file/line_start/snippet 为必填，line_end可选。 ReportAssemblerWorker 承诺：(a) 顶层严格只有 proposals + report_markdown 两个键，无多余字段 (additionalProperties=false)；(b) report_markdown 长度≥500且含三个规定章节；(c) proposals 数量∈[3, top_n]；(d) 每条 proposal 的 reference_code.file 相对于 repo_path 是真实文件路径、snippet 首",
    parent='requirement',
    json_schema={'type': 'object', 'properties': {'report_markdown': {'type': 'string', 'minLength': 500, 'description': "综合 markdown 报告，≥500 字，必须包含 '## 仓库一览'、'## 关键模式'、'## 提案总览' 三个二级章节"}, 'proposals': {'type': 'array', 'minItems': 3, 'items': {'type': 'object', 'properties': {'id': {'type': 'string', 'pattern': '^PRO-\\d{3}$', 'description': '提案编号，形如 PRO-001'}, 'title': {'type': 'string', 'minLength': 8, 'description': '提案标题'}, 'problem': {'type': 'string', 'minLength': 30, 'description': '问题陈述'}, 'proposed_change': {'type': 'string', 'minLength': 30, 'description': '改进方向'}, 'reference_code': {'type': 'object', 'properties': {'file': {'type': 'string', 'description': '相对路径，必须真实存在于 repo_path 下'}, 'line_start': {'type': 'integer', 'minimum': 1, 'description': '引用起始行号 (1-based)'}, 'line_end': {'type': 'integer', 'minimum': 1, 'description': '引用结束行号 (1-based)，可选'}, 'snippet': {'type': 'string', 'description': '引用片段，必须从真实文件中逐字读出'}}, 'required': ['file', 'line_start', 'snippet'], 'description': '真实代码引用锚点，用于验收时逐字比对源码'}, 'risk': {'type': 'string', 'minLength': 15, 'description': '实施风险评估'}}, 'required': ['id', 'title', 'problem', 'proposed_change', 'reference_code', 'risk']}, 'description': '改进提案列表，每条提案必须附带真实代码锚点'}}, 'required': ['report_markdown', 'proposals'], 'additionalProperties': False},
    tags=['repo_absorption', 'generated', 'kind.sink'],
)

ALL_MATERIALS = [M_REPO_ABSORPTION_SCAN_CONFIG, M_REPO_ABSORPTION_FILE_INVENTORY, M_REPO_ABSORPTION_SELECTED_MODULES, M_REPO_ABSORPTION_MODULE_SOURCES, M_REPO_ABSORPTION_EXTRACTION_RESULTS, M_REPO_ABSORPTION_SINK_REPORT]

def register_formats(registry: FormatRegistry) -> None:
    """注册 repo_absorption 所有 Material 到 registry."""
    for mat in ALL_MATERIALS:
        if not registry.is_registered(mat.id):
            try:
                registry.register(mat)
            except Exception:
                pass
