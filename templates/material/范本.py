# [OMNI] origin=ai-ide domain=omnicompany/templates/material ts=2026-05-01T00:00:00Z type=template status=active agent=ai-ide-bd9cde92
# [OMNI] summary="材料模板范本, 含四档案例覆盖 source/internal/sink 跟结构化/大明文嵌入/指针/混合本体格式"
# [OMNI] why="给将来要新建一份材料的人看到一份合规材料长什么样, 字段全/语义清/kind 标记齐/本体格式覆盖"
# [OMNI] tags=template,material,sample,foundation
# [OMNI] material_id="material:template.material.sample.py"
"""材料范本 — 一份合规 formats.py 文件长什么样

**重要 — 关于这份范本的拼接约定**:

实际项目里一份 formats.py 通常按 team 组织 (一个 team 一份), 不会像本范本这样把
csv_to_md / gameplay_system / voxel_engine 三个 team 的 material 拼在同一个文件里. 本范本拼一起
**只是为了在一份文件里给读者看到不同 kind 跟本体格式的对比**, 实际新建 formats.py 时
请按服务包/领域包独立分文件, 不要照抄拼接.

下面用三段 ════ 分隔线明确标出三个 team 的边界, 让范本作为教学拼接物的同时, 不模糊
"一个 team 一份 formats.py" 的隐性规则.

本范本展示一组完整的 Material 定义, 在两个维度交叉覆盖:

维度一 · kind 三分:
  - kind.source (外部输入入口)
  - kind.internal (Worker 间流转中间产物)
  - kind.sink (终端落盘 / 响应外部)

维度二 · 本体格式 — material 本体可以是任何计算机数据:
  - 结构化数据 (JSON 标量/对象/数组)
  - 大明文嵌入 (markdown / 代码 / SQL 文本嵌入 payload, < 10KB)
  - 指针 (大明文 / 二进制 / 多文件本体走 workspace 文件, payload 含 files_ref 元数据)
  - 混合 (上面几种组合)

  本体甚至可以不可读 (二进制 / 加密 / 混淆) — 不可读的本体仍能作为 material 在系统内
  传递 / 注册 / 跟踪. 但**可读性是优选指标** — 同等条件下选可读形态. 不可读本体必须
  在 description 里解释为什么不能可读, 给出可读替代 (例如反汇编 / 摘要 / 元数据视图).

  **硬规则**: 不论本体可不可读, material 的 schema (description + json_schema + tags
  三个协议层字段) **必须始终是人和机器都能理解的**. schema 是 material 的对外接口,
  整个 omnicompany 系统靠 schema 做协议层操作 (校验 / 路由 / 诊断 / 检索), 不依赖本体可读性.

下面五个案例分别示范不同 kind 跟本体格式组合. 读完知道"我手上要新建的 material 应该长什么样".

这份范本是基于真实代码改的, 不是凭空虚构. 字段值是这种 material 在系统里真出现过的形态.
"""

from __future__ import annotations

from omnicompany.packages.services._core.omnicompany import Material
from omnicompany.protocol.format import FormatRegistry
# ↑ 命名迁移期 (Phase A 完成): 类名用 Material (新), Registry 仍用 FormatRegistry (旧名 grandfathered).
# 跟真业务一致, 例如 services/_diagnosis/semantic_auditor/formats.py 同样形态.

DOMAIN = "your_domain"   # 实际填写时改成你的服务包名 (例如 "csv_to_md") 或领域命名 (例如 "gameplay_system")


# ════════════════════════════════════════════════════════════════════════
# Team 1 / 3 · csv_to_md
# 简单 sink team, 三档 source / internal / sink 全套, 全部档 A 结构化数据型.
# 真实代码: src/omnicompany/packages/services/csv_to_md/formats.py
# ════════════════════════════════════════════════════════════════════════


# ──────────────────────────────────────────────────────────────────────
# 案例 1: kind.source 入口材料
#
# 特征: 系统外部输入, 无 producer Worker, 由 CLI / 外部事件 / 定时器注入.
# Q4 诊断 (孤儿 worker / 疑似冗余 material) 允许它无上游.
#
# 何时用 source: 这份材料是一个团队的"启动信号", 由系统外的人或程序提供.
# 反例: 把上游 Worker 的产出标 source — 那是 internal, 不是 source.
# ──────────────────────────────────────────────────────────────────────

M_FILE_INPUT = Material(
    id=f"{DOMAIN}.file_input",
    name="FileInput",
    description=(
        "csv_to_md 管线的入口协议, 声明待解析的 CSV 文件路径与读取编码. "
        "整个 csv_to_md team 的外部触发信号 (kind.source), 无上游 producer Worker, "
        "由 CLI (`omni run csv-to-md -i path=<csv_file> [-i encoding=<enc>]`) 或 "
        "JSON 模式 (`omni run csv-to-md -j '{\"path\":..., \"encoding\":...}'`) 注入.\n\n"

        "【字段语义】\n"
        "- path (string, required): CSV 文件的绝对或相对路径, 指向磁盘上待读取的 .csv 文件.\n"
        "- encoding (string, default 'utf-8'): 读取该 CSV 时使用的字符编码, 常用值 utf-8 / gbk / latin-1.\n\n"

        "【上游承诺】作为 source Material, 无 producer Worker. CLI 入口层承诺: path 字段必须存在且非空字符串; "
        "encoding 若提供则必须是 Python 标准库 codecs 可识别的编码名. 文件本身是否存在 / 编码是否匹配, "
        "交由 CsvReaderWorker 在运行时校验并产出 FAIL Verdict.\n\n"

        "【下游用途】CsvReaderWorker 作为唯一 consumer, 读取 path 指向的文件, 按 encoding 解码, "
        "用 csv 标准库解析表头与数据行, 处理 FileNotFoundError / UnicodeDecodeError 等异常, "
        "输出结构化行数据给下游 MarkdownWriterWorker.\n\n"

        "【最小合法样例】\n"
        '{"path": "/data/users.csv", "encoding": "utf-8"}\n'
    ),
    parent="requirement",
    json_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "CSV 文件绝对或相对路径"},
            "encoding": {"type": "string", "default": "utf-8", "description": "CSV 文件编码"},
        },
        "required": ["path"],
    },
    tags=[
        "kind.source",            # ← 必有 kind 标 (F-19), 三选一: source / internal / sink
        f"domain.{DOMAIN}",       # ← 业务域标
        "content.file_path",      # ← 内容性质标 (按需)
    ],
    examples=[
        {"path": "/data/users.csv", "encoding": "utf-8"},
        {"path": "./reports/q1.csv"},   # encoding 走默认值
    ],
)


# ──────────────────────────────────────────────────────────────────────
# 案例 2: kind.internal 中间材料
#
# 特征: worker 间流转, 必须有完整 producer + consumer 链.
# 系统里大部分材料是这一档.
#
# 何时用 internal: 一个 Worker 产出, 至少一个其他 Worker 消费, 跨 Worker 流转.
# 何时拆出来作 internal 而不是藏在 Worker 内部 (按价值拆分):
# - 人类可读价值 (trace-view 能一眼看懂这是什么)
# - 调试价值 (能独立判定某环节是否健康)
# - 复用价值 (别的管线会消费这份)
# - 检查薄弱性 (需要独立校验的点)
# 任一成立就拆; 都不成立就藏在 Worker 内部走 Signal, 不开新 material.
# ──────────────────────────────────────────────────────────────────────

M_PARSED_ROWS = Material(
    id=f"{DOMAIN}.parsed_rows",
    name="ParsedRows",
    description=(
        "csv_to_md 管线的中间产物, 承载 CsvReaderWorker 从原始 CSV 文件解析后剥离出的"
        "结构化表头列表与逐行数据矩阵. 纯数据协议层, 不含任何 Markdown 格式信息, "
        "供下游 Writer 进行 GFM 表格渲染.\n\n"

        "【字段语义】\n"
        "- headers (list[str]): 字符串数组, 按 CSV 首行从左到右顺序记录列名, 已经 CSV 解析器剥离外层引号与转义.\n"
        "- rows (list[list[str]]): 二维字符串数组, 每个子数组代表一行数据, 长度严格等于 len(headers); "
        "空单元格表示为空串 \"\" 而非 None; 字段内原始换行符保留 (未做 <br> 替换, 那是 Writer 职责).\n\n"

        "【上游承诺 — CsvReaderWorker 必守】\n"
        "1. headers 长度 ≥ 1 (空 CSV / 无表头视为解析失败, 走 Verdict.FAIL, 不产出本 Material)\n"
        "2. 每行 rows[i] 的 len 严格等于 len(headers), 不足补空串、多余截断\n"
        "3. 所有字符串值已按指定 encoding 正确解码; CSV 转义已还原为字面值\n"
        "4. rows 保持原始行序, 不做排序 / 过滤 / 去重\n\n"

        "【下游用途 — MarkdownWriterWorker 怎么消费】\n"
        "(1) 用 headers 生成 GFM 表格首行; (2) 生成 | --- | 分隔行; "
        "(3) 遍历 rows 逐行渲染数据, 对每个 cell 执行 GFM 转义 (| → \\|, 换行 → <br>); "
        "(4) 保证末尾仅一个 \\n; (5) 若 rows 为空数组则输出仅含表头+分隔行的两行表格.\n\n"

        "【最小合法样例】\n"
        '{"headers": ["name", "age"], "rows": [["Alice", "30"], ["Bob", "25"]]}\n'
    ),
    parent="doc",
    json_schema={
        "type": "object",
        "properties": {
            "headers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "CSV 表头字段列表, 按原始列序排列",
            },
            "rows": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "description": "逐行数据矩阵, 每行是与 headers 等长的字符串列表",
            },
        },
        "required": ["headers", "rows"],
    },
    tags=[
        "kind.internal",
        f"domain.{DOMAIN}",
        "content.tabular_data",
    ],
    examples=[
        {"headers": ["name", "age"], "rows": [["Alice", "30"], ["Bob", "25"]]},
        {"headers": ["id"], "rows": []},   # 空表格也合法
    ],
)


# ──────────────────────────────────────────────────────────────────────
# 案例 3: kind.sink 终端材料
#
# 特征: 系统最终输出, 落盘 / 响应外部 / 审计. 允许无下游 consumer.
# Q4 诊断对 sink 无消费者豁免 (INFO 级, 不告警).
#
# 何时用 sink: 团队跑完最后落盘的产物 / CLI 返给用户的结果 / 审计日志.
# 反例: sink 不该再被同 team 内别的 Worker 订阅 — 一旦被订阅就破坏"终端"语义.
# ──────────────────────────────────────────────────────────────────────

M_MD_OUTPUT = Material(
    id=f"{DOMAIN}.md_output",
    name="MdOutput",
    description=(
        "csv_to_md team 的最终输出产物 (sink Material): MarkdownWriterWorker 将 CsvReaderWorker "
        "解析的结构化行数据按 GFM 语法规则渲染而成的 Markdown 表格字符串. 该 Material 代表整个 "
        "CSV→Markdown 转换流水线的终局结果, 被 CLI 打印到 stdout 并被验收脚本逐字节比对.\n\n"

        "【字段语义】\n"
        "- content (string, required): GFM 表格的完整 markdown 文本, 严格满足 8 条硬约定 "
        "(表头行 / 分隔符行 / 数据行格式一致、| 转义、\\n→<br>、末尾单换行无 trailing 空白、空字段渲染为空串等)\n"
        "- source_path (string, optional): 原始 CSV 文件路径, 用于追溯溯源\n"
        "- row_count (int, optional): 转换的数据行数\n"
        "- column_count (int, optional): 列数\n\n"

        "【上游承诺 — MarkdownWriterWorker 必守】\n"
        "1. content 字段必须存在且为合法字符串, 不允许 null / None / 缺失\n"
        "2. content 内容为严格 GFM 格式, 逐字节对齐 csv_to_md 需求文档的 8 条规则\n"
        "3. 分隔符行 | --- | 的列数与表头列数一致\n"
        "4. content 末尾有且仅有一个 \\n\n"
        "5. 字段内含 | 必须转义为 \\|; 字段内含换行必须渲染为 <br>\n"
        "6. 整体可复现: 同一 CSV 输入两次输出 byte-identical\n\n"

        "【下游用途】\n"
        "- 验收脚本 (acceptance.py) 通过 verdict.output['content'] 提取该字段, 与 expected/*.md 文件 "
        "byte-identical 比对, 任一不匹配即判定 FAIL\n"
        "- CLI 把 content 直接打印到 stdout 给用户消费\n\n"

        "【最小合法样例】\n"
        '{"content": "| name | age |\\n| --- | --- |\\n| Alice | 30 |\\n", '
        '"source_path": "/data/users.csv", "row_count": 1, "column_count": 2}\n'
    ),
    parent="requirement",
    json_schema={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "GFM 表格 markdown 文本 (逐字节精确)",
            },
            "source_path": {"type": "string", "description": "被转换的 CSV 文件路径"},
            "row_count": {"type": "integer", "description": "数据行数 (不含表头)"},
            "column_count": {"type": "integer", "description": "列数"},
        },
        "required": ["content"],
    },
    tags=[
        "kind.sink",
        f"domain.{DOMAIN}",
        "content.markdown",
    ],
    examples=[
        {
            "content": "| name | age |\n| --- | --- |\n| Alice | 30 |\n",
            "source_path": "/data/users.csv",
            "row_count": 1,
            "column_count": 2,
        },
    ],
)


# ════════════════════════════════════════════════════════════════════════
# Team 2 / 3 · gameplay_system (示范用 — 简化自真实 gameplay_system.team_table)
# 大文档型 sink, 档 B 大明文嵌入, 演示 markdown 字段嵌入 payload.
# 真实代码: src/omnicompany/packages/domains/gameplay_system/team_table/formats.py 第 130-280 行
# ════════════════════════════════════════════════════════════════════════


# ──────────────────────────────────────────────────────────────────────
# 案例 4: 大明文嵌入型 material — 本体是 markdown / 代码 / SQL 等大文本
#
# 特征: payload 里有 <content_name>: str 字段嵌入大段非结构化文本.
#       人类直接读这个字段; 机器对该字段不做深度 parse, 用 LLM 抽取语义.
# 何时用: 这份 material 的核心价值是"给人看 + LLM 读" 的大段文档/代码.
#         例如 markdown 表格理解文档 / Python 业务脚本 / SQL 报表查询.
# 跟指针型的边界:
#   - 内容 < 50KB 嵌 payload 方便 (这一档)
#   - 内容 ≥ 50KB 或二进制走指针型 (下一档)
# ──────────────────────────────────────────────────────────────────────

M_TABLE_DOC = Material(
    id=f"{DOMAIN}.table_doc",
    name="TableDoc",
    description=(
        "表格理解文档 — 一张 markdown 文档, 汇总「这张表是干什么的 / 每个字段怎么用 / "
        "规则证据 / 已知局限」四类信息, 供人类 + agent 双向阅读.\n\n"

        "【字段语义】\n"
        "- table_name (string, required): 表名, 例如 'TavernPool'\n"
        "- markdown (string, required): markdown 文档正文 (大明文, 嵌入 payload)\n"
        "- source (string, required): 产出来源, 'qwen-3.6-plus' / 'template' / 'human'\n"
        "-落盘位置 (string, optional): SDK 真实落盘路径, 例如 'docs/tables/TavernPool.md'\n\n"

        "【markdown 正文结构 (Worker 合约 — 四节固定)】\n"
        "1. `# <TableName> · 表格理解文档 (v<version>)` — 一级标题 + 版本号\n"
        "2. `## 业务用途` — 这张表在业务里干什么 (2-3 段)\n"
        "3. `## 字段清单` — 表格列出每个字段 + 类型 + 业务含义 + 规则证据 (xlsm 公式 / FK 关系 / 等)\n"
        "4. `## 已知局限` — 当前理解还不准的字段 / 待补充信息源\n\n"

        "【上游承诺 — TableDocAuthor 必守】\n"
        "1. 四节齐全, 章节标题字面对齐\n"
        "2. 字段清单覆盖 schema 全部字段, 不漏\n"
        "3. 已知局限段非空 (没漏写就显式声明 '暂无')\n"
        "4. markdown 字段不超过 50KB (超就拆 / 走指针)\n\n"

        "【下游用途】\n"
        "- 人类阅读: 团队成员 + L1 直接打开 SDK docs/tables/<table>.md 看\n"
        "- LLM 检索: 字段语义工人通过本 material 抽取字段语义不必重读 xlsm\n"
        "- DocReviewer: 校验四节齐全 + 字段覆盖率\n\n"

        "【最小合法样例】\n"
        '{\n'
        '  "table_name": "TavernPool",\n'
        '  "markdown": "# TavernPool · 表格理解文档 (v1.6.4)\\n\\n## 业务用途\\n酒馆抽gacha_pool配置...\\n",\n'
        '  "source": "qwen-3.6-plus",\n'
        '  "落盘位置": "docs/tables/TavernPool.md"\n'
        '}\n'
    ),
    parent="doc",
    json_schema={
        "type": "object",
        "properties": {
            "table_name": {"type": "string", "description": "表名"},
            "markdown": {
                "type": "string",
                "description": (
                    "markdown 文档正文. 是大明文嵌入字段, schema 只标 type=string, "
                    "正文结构约束在 description 字段语义段说明 (四节固定)"
                ),
            },
            "source": {
                "type": "string",
                "enum": ["qwen-3.6-plus", "template", "human"],
                "description": "产出来源",
            },
            "落盘位置": {
                "type": "string",
                "description": "SDK 真实落盘的相对路径",
            },
        },
        "required": ["table_name", "markdown", "source"],
    },
    tags=[
        "kind.sink",
        f"domain.{DOMAIN}",
        "content.markdown_doc",        # ← 内容性质: markdown 大明文文档
        "body_format.embedded_text",   # ← 本体格式: 嵌入式大明文
    ],
    examples=[
        {
            "table_name": "TavernPool",
            "markdown": "# TavernPool · 表格理解文档 (v1.6.4)\n\n## 业务用途\n酒馆抽gacha_pool配置...\n\n## 字段清单\n...\n\n## 已知局限\n暂无.\n",
            "source": "qwen-3.6-plus",
            "落盘位置": "docs/tables/TavernPool.md",
        },
    ],
)


# ════════════════════════════════════════════════════════════════════════
# Team 3 / 3 · voxel_engine (示范用 — 简化自真实 entity build 输出)
# 二进制 sink, 档 C 指针型, 演示 files_ref 走 workspace 文件 (R-22).
# 真实代码风格: src/omnicompany/packages/domains/voxel_engine/formats.py
# ════════════════════════════════════════════════════════════════════════


# ──────────────────────────────────────────────────────────────────────
# 案例 5: 指针型 material — 本体走 workspace 文件, payload 只存指针
#
# 特征: payload 含 files_ref 列表, 大明文 / 二进制 / 多文件本体落盘到 workspace 目录.
#       material 协议层只携带"指向哪些文件" + 元数据 (路径/哈希/大小).
# 何时用 (材料规范 F-17 硬阈值):
#   - 单条 material 内容 ≥ 10 KB: 建议走指针
#   - 单条 ≥ 1 MB: 强制走指针
#   - 二进制 / 多媒体: 强制走指针
#   - 多文件协同 (例如一份打包的 jar 工程): 强制走指针
# 写入规则: 唯一合法入口是 WorkspaceWriterWorker 子类 (工人规范 R-22).
# ──────────────────────────────────────────────────────────────────────

M_BUILT_JAR = Material(
    id=f"{DOMAIN}.built_jar",
    name="BuiltJar",
    description=(
        "voxel_engine 编译产出的 jar 包 + 相关编译产物 — 二进制本体, 走 workspace 文件指针, "
        "不嵌 payload.\n\n"

        "【字段语义】\n"
        "- entity_name (string, required): 编译目标实体名, 例如 'fleeing_rabbit'\n"
        "- files_ref (array, required): 指向 workspace 文件的指针列表, 每条含:\n"
        "    - workspace (string): workspace_id, 例如 'workspace.voxel_engine.entity_build_20260501'\n"
        "    - relpath (string): workspace 内相对路径, 例如 'build/libs/entity-1.0.jar'\n"
        "    - ts (string): 文件生成时间 ISO8601\n"
        "    - hash (string): sha256:<前16位>\n"
        "    - size_bytes (int): 文件大小\n"
        "- compile_log_summary (string, optional): 编译日志摘要 (短文本, 嵌入 payload)\n"
        "- compile_status (string, required): 'success' / 'failed' / 'partial'\n\n"

        "【上游承诺 — JarBuilderWorker (R-22 WorkspaceWriterWorker 子类) 必守】\n"
        "1. files_ref 至少含主 jar (build/libs/*.jar)\n"
        "2. 每条 files_ref 的文件在 workspace 真实存在 (产出时 assert)\n"
        "3. compile_status='success' ⇒ 主 jar 存在且 size > 0\n"
        "4. compile_status='failed' ⇒ files_ref 仍含编译过程产物 (build/reports/) 给诊断用\n"
        "5. hash 字段是真 sha256 计算结果, 可作 replay 一致性验证\n\n"

        "【下游用途】\n"
        "- LoadCheckerWorker: 通过 files_ref 拿 jar 路径, 复制到 server mods/ 启动验证\n"
        "- CompileReportAnalyzer: 编译失败时读 files_ref 里的 build/reports/ 找 javac 错误\n"
        "- 守护扫描: 通过 hash 检测 jar 是否被外部篡改 (重算 hash 对比)\n\n"

        "【最小合法样例】\n"
        '{\n'
        '  "entity_name": "fleeing_rabbit",\n'
        '  "files_ref": [\n'
        '    {\n'
        '      "workspace": "workspace.voxel_engine.entity_build_20260501",\n'
        '      "relpath": "build/libs/eternal-war-1.0.jar",\n'
        '      "ts": "2026-05-01T10:30:00Z",\n'
        '      "hash": "sha256:a3f5b2c1d4e6f7a8",\n'
        '      "size_bytes": 524288\n'
        '    }\n'
        '  ],\n'
        '  "compile_status": "success",\n'
        '  "compile_log_summary": "BUILD SUCCESSFUL in 23s"\n'
        '}\n'
    ),
    parent="material",
    json_schema={
        "type": "object",
        "properties": {
            "entity_name": {"type": "string"},
            "files_ref": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "workspace": {"type": "string"},
                        "relpath": {"type": "string"},
                        "ts": {"type": "string"},
                        "hash": {"type": "string"},
                        "size_bytes": {"type": "integer", "minimum": 0},
                    },
                    "required": ["workspace", "relpath", "ts", "hash", "size_bytes"],
                },
                "minItems": 1,
            },
            "compile_status": {
                "type": "string",
                "enum": ["success", "failed", "partial"],
            },
            "compile_log_summary": {"type": "string"},
        },
        "required": ["entity_name", "files_ref", "compile_status"],
    },
    tags=[
        "kind.sink",
        f"domain.{DOMAIN}",
        "content.binary_artifact",     # ← 内容性质: 二进制构建产物
        "body_format.workspace_pointer",  # ← 本体格式: 指针, 本体走 workspace 文件
    ],
    examples=[
        {
            "entity_name": "fleeing_rabbit",
            "files_ref": [
                {
                    "workspace": "workspace.voxel_engine.entity_build_20260501",
                    "relpath": "build/libs/eternal-war-1.0.jar",
                    "ts": "2026-05-01T10:30:00Z",
                    "hash": "sha256:a3f5b2c1d4e6f7a8",
                    "size_bytes": 524288,
                },
            ],
            "compile_status": "success",
            "compile_log_summary": "BUILD SUCCESSFUL in 23s",
        },
    ],
)


# ──────────────────────────────────────────────────────────────────────
# 注册集合 — 必须有
# ──────────────────────────────────────────────────────────────────────

ALL_MATERIALS = [
    M_FILE_INPUT,        # source · 结构化数据型
    M_PARSED_ROWS,       # internal · 结构化数据型
    M_MD_OUTPUT,         # sink · 结构化数据型 (字段是字符串但是字面 GFM 协议)
    M_TABLE_DOC,         # sink · 大明文嵌入型 (markdown 文档)
    M_BUILT_JAR,         # sink · 指针型 (二进制产物走 workspace 文件)
]


def register_formats(registry: FormatRegistry) -> None:
    """注册本服务包的所有 Material 到 registry."""
    for mat in ALL_MATERIALS:
        if not registry.is_registered(mat.id):
            try:
                registry.register(mat)
            except Exception:
                pass
