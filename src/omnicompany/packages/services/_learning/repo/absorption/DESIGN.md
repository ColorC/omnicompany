
# repo_absorption · 设计文档

## 状态
- **版本**: V1 (design)
- **成熟度**: design
- **下一步**: 完成 5 个 Worker 的源码实现并通过 MaterialDispatcher smoke 验证，使状态升级至 active

## 核心目的

本团队（repo_absorption）解决的核心问题是：给定一个本地 Python 仓库根目录和筛选数量 top_n，安全遍历全部 .py 文件并经由 LLM 智能评估，最终产出一份结构化的"提案集合 + 分析报告"（proposals + report_markdown），供下游模块消费。它不解决代码执行、编译验证或远程拉取问题，仅聚焦本地已有源码的扫描→筛选→读取→模式提取→报告组装这一条单向管线。

团队包含 5 个 Worker（2 HARD + 2 AGENT + 1 HARD），消费 1 个 source Material（scan_config），产出 1 个 sink Material（sink_report），中间经过 file_inventory → selected_modules → module_sources → extraction_results 四步内部流转。整个管线由 MaterialDispatcher 驱动，每 `(job_id, worker_id)` 恰好激活一次（Q1 铁律）。

## 核心接口

以下是团队对外的 Worker 入口与 Material 契约：

- **`RepoScannerWorker.run(input_data)`** — 输入 `scan_config`，执行确定性 Shell 遍历（find/wc/stat），输出 `file_inventory`（全量 .py 路径/行数/体积清单）。[workers/repo_scanner_worker.py](src/omnicompany/packages/services/repo_absorption/workers/repo_scanner_worker.py)
- **`ModuleSelectorWorker.run(input_data)`** — 输入 `file_inventory` + `scan_config.top_n`，通过 LLM 评估文件复杂度并排序，输出 `selected_modules`（top_n 关键模块路径列表）。[workers/module_selector_worker.py](src/omnicompany/packages/services/repo_absorption/workers/module_selector_worker.py)
- **`SourceReaderWorker.run(input_data)`** — 输入 `selected_modules`，执行全量 `Path.read_text()` 无截断读取，>1MB 时按需分片，输出 `module_sources`（完整源码及元数据）。[workers/source_reader_worker.py](src/omnicompany/packages/services/repo_absorption/workers/source_reader_worker.py)
- **`PatternExtractorWorker.run(input_data)`** — 输入 `module_sources`，深度分析代码模式，生成带 PRO-NNN 标识与参考锚点的结构化提案，输出 `extraction_results`。[workers/pattern_extractor_worker.py](src/omnicompany/packages/services/repo_absorption/workers/pattern_extractor_worker.py)
- **`ReportAssemblerWorker.run(input_data)`** — 输入 `extraction_results` + 上下文，校验 JSON Schema 与 reference_code 真实性，组装 proposals 与 ≥500 字 report_markdown（含强制三节），输出 `sink_report`。[workers/report_assembler_worker.py](src/omnicompany/packages/services/repo_absorption/workers/report_assembler_worker.py)

Material 格式定义位于 [formats.py](src/omnicompany/packages/services/repo_absorption/formats.py)，含 6 个 Material（1 source + 4 internal + 1 sink），均通过 `tags` 声明 kind。

## 架构决策

### D1 — HARD / AGENT 混合编排策略
扫描与读取环节（RepoScannerWorker、SourceReaderWorker、ReportAssemblerWorker）采用 HARD 实现——纯规则驱动、确定性遍历、无 LLM 调用，保证可重复性与低成本。筛选与分析环节（ModuleSelectorWorker、PatternExtractorWorker）采用 AGENT 实现——需要 LLM 进行语义评估与模式识别。这种分工使管线在"确定性操作"和"认知判断"之间取得成本/质量平衡，避免过度依赖 LLM。

### D2 — BashBus + DiskBus 替代 subprocess / open 直调
RepoScannerWorker 统一通过 `BashBus.run()` 执行 find/wc/stat 等 Shell 命令，通过 `DiskBus.write()` 持久化中间产物，严禁直调 `subprocess` 或 `open('w')`。这使得所有 I/O 操作可被管线基础设施统一监控、限速、审计，同时为跨平台兼容（Windows PowerShell 回退）提供集中管控点。

### D3 — 铁律 A：无预防性截断 + >1MB 按需分片
SourceReaderWorker 严格遵循"不预防性截断"铁律：只要模块被选中，就必须读取完整源码。唯一例外是单文件 >1MB 时按需分片读取（由 SourceReaderWorker 内部逻辑处理），避免因超大文件耗尽上下文窗口。这一决策确保 PatternExtractorWorker 接收的源码在语义上完整，不被人为裁剪导致误判。

### D4 — ReportAssemblerWorker 双校验机制（Schema + 锚点真实性）
ReportAssemblerWorker 在组装最终报告前执行两道校验：① 对 proposals 进行 JSON Schema 校验确保字段完整性；② 对每条 proposal 的 `reference_code`（逐字参考锚点）做真实性核验，确保锚点文本确实出现在源文件中（遵守 F-15 诚实声明）。若任一校验失败，路由 Verdict(FAIL) 而非静默降级，防止虚假引用污染下游消费。

### D5 — top_n < 3 边界阈值兜底
ModuleSelectorWorker 在 top_n < 3 时触发边界兜底策略：即使 LLM 评估结果不足 3 个模块，也至少保留基础结构模块（如 __init__.py、入口文件、核心模块）。这避免了在 small repo 场景下产出空模块列表导致后续管线短路。

## 数据流 / 拓扑

```
  ┌──────────────────────────────────────────────────────────────────┐
  │                        repo_absorption 管线                       │
  └──────────────────────────────────────────────────────────────────┘

  [source] scan_config          kind.source
  {repo_path, top_n}
          │
          │ (consumed by both)
          ├─────────────────────────────────────┐
          │                                     │
          ▼                                     ▼
  ┌───────────────────┐              ┌───────────────────┐
  │ RepoScannerWorker │              │ ModuleSelectorWkr │
  │   (HARD)          │              │   (AGENT)         │
  └────────┬──────────┘              └────────┬──────────┘
           │ PASS                             │ top_n 值
           ▼                                  ▼
  ┌──────────────────────────────────────────────────┐
  │          file_inventory        kind.internal     │
  │  {files: [{path, abs_path, line_count,           │
  │            size_bytes}, ...],                    │
  │   total_files, total_lines, total_bytes}         │
  └──────────────────────┬───────────────────────────┘
                         │ consumed by
                         ▼
              ┌──────────────────────┐
              │ ModuleSelectorWorker │  (LLM 评估 + 排序)
              │   (AGENT)            │
              └──────────┬───────────┘
                         │ PASS
                         ▼
  ┌──────────────────────────────────────────────────┐
  │         selected_modules       kind.internal     │
  │  {module_paths: ["path/to/a.py", ...],           │
  │   total_selected: int}                           │
  └──────────────────────┬───────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │ SourceReaderWorker   │  (Path.read_text, 无截断)
              │   (HARD)             │
              └──────────┬───────────┘
                         │ PASS
                         ▼
  ┌──────────────────────────────────────────────────┐
  │         module_sources         kind.internal     │
  │  {sources: [{path, content, size_bytes,          │
  │              line_count, read_at}, ...]}         │
  └──────────────────────┬───────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │PatternExtractorWorker│  (深度分析 → PRO-NNN 提案)
              │   (AGENT)            │
              └──────────┬───────────┘
                         │ PASS
                         ▼
  ┌──────────────────────────────────────────────────┐
  │       extraction_results       kind.internal     │
  │  {proposals: [{id: "PRO-NNN", reference_code,    │
  │   risk_rating, ...}], context: {...}}            │
  └──────────────────────┬───────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │ReportAssemblerWorker │  (Schema校验+锚点真实性)
              │   (HARD)             │
              └──────────┬───────────┘
                         │ PASS
                         ▼
  ┌──────────────────────────────────────────────────┐
  │          sink_report           kind.sink         │
  │  {proposals: [...],                              │
  │   report_markdown: str (≥500字, 含强制三节)}     │
  └──────────────────────────────────────────────────┘
```

Verdict 路由补充：
- RepoScannerWorker: PASS→next | FAIL→retry(max 2) | PARTIAL→retry(max 1)
- ModuleSelectorWorker: PASS→next | FAIL→retry(max 2)
- SourceReaderWorker: PASS→next | FAIL→retry(max 1)
- PatternExtractorWorker: PASS→next | FAIL→retry(max 2)
- ReportAssemblerWorker: PASS→next(sink) | FAIL→上游诊断

## 已知局限

1. **跨平台 Shell 命令差异** — RepoScannerWorker 依赖 BashBus 执行 find/wc/stat，在 Windows 环境下需回退至 PowerShell Get-Item，行为差异可能导致行数/大小统计偏差或命令失败。未来可考虑引入统一的跨平台文件元数据工具类替代裸命令。

2. **大仓库遍历超时风险** — 当 repo_path 下 .py 文件数 >10000 时，单次 BashBus.run 可能超时或被截断，导致 file_inventory 不完整。当前无分片遍历策略，后续可考虑按子目录分批扫描再聚合。

3. **符号链接跟随问题** — find 默认可能跟随软链接遍历外部目录，产出非预期的文件清单。当前排除列表（__pycache__/、.git/、site-packages/、vendor/、_archive/）未涵盖所有可能的外部挂载点，存在信息泄漏风险。

4. **LLM 评估一致性** — ModuleSelectorWorker 和 PatternExtractorWorker 均依赖 LLM 输出，相同输入在不同调用间可能产生不一致结果（模型温度、token 采样随机性）。当前无评估一致性校验或多次采样投票机制。

5. **source Material 前置约束** — scan_config 要求 repo_path 必须指向本地真实存在的目录且含 .py 文件，不支持远程仓库（URL）扫描。若需支持远程仓库，需增加 git clone / 解包等前置步骤。

## 参考资料

- `docs/standards/design_md_template.md` — DESIGN.md 结构模板与 Guardian OMNI-034 检测规范
- `docs/standards/omni-header.md` — OmniMark 文件头规范
- `docs/standards/worker.md` — Worker 设计与实现标准
- `docs/standards/material.md` — Material / Format 定义标准（含 kind.source/internal/sink）
- `docs/standards/team.md` — Team 编排与 MaterialDispatcher 集成标准
- `docs/standards/llm_first.md` — LLM 调用优先原则
- `docs/standards/information_sufficiency.md` — 信息充分性三层防御
- `docs/standards/agent_tools.md` — Agent 工具调用标准
- `docs/standards/terminology.md` — 术语规范（Worker/Material/Team 命名）
- `docs/standards/distributed-docs.md` — 分布式文档放置规则
- `docs/standards/code.md` — 编码规范
- `src/omnicompany/packages/services/omnicompany/` — Team 金标范本（omnicompany Agent Team 演示）
- `src/omnicompany/packages/services/guardian/workers/` — 类 A 迁移 Worker 参考