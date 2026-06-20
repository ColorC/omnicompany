# [OMNI] origin=claude-code domain=services/repo_absorption/workers ts=2026-04-25T00:00:00Z type=worker
# [OMNI] material_id="material:learning.repo.absorption.worker.pattern_extractor_agent.py"
"""PatternExtractorWorker — repo_absorption Team Worker #4 (AGENT).

Worker 协议:
  FORMAT_IN  = repo_absorption.module_sources
  FORMAT_OUT = repo_absorption.extraction_results
  FORMAT_IN_MODE = and

职责: 接收 SourceReaderWorker 读取的完整模块源码, 通过 AgentNodeLoop 进行
      多轮 LLM 深度分析, 提取代码模式 (设计模式/反模式/架构特征/错误处理策略),
      生成带 PRO-NNN 标识的结构化改进提案, 每条提案附真实代码锚点 (reference_code),
      产出 extraction_results 供下游 ReportAssemblerWorker 消费.

工具: ReadFile / Grep / Glob / ListDir / SubmitExtractions
可读: 输入 data 中的完整源码 + 文件系统探索
"""
from __future__ import annotations

import json
from typing import Any, ClassVar

from omnicompany.packages.services._core.agent.loop import AgentNodeLoop
from omnicompany.packages.services._core.agent.routers.extract_result import ExtractResultRouter
from omnicompany.packages.services._core.agent.routers.prompt_builder import PromptBuilderRouter
from omnicompany.packages.services._core.agent.routers.single_tool import (
    GlobRouter,
    GrepRouter,
    ListDirRouter,
    ReadFileRouter,
    SingleToolRouter,
    ToolContext,
)
from omnicompany.protocol.anchor import Verdict, VerdictKind


_SYSTEM_PROMPT = """你是 repo_absorption 管线的 PatternExtractorWorker — 一个基于 LLM 的源码深度分析 Agent。

## 职责
读取并分析 Python 模块源码, 提取代码模式, 生成结构化改进提案 (PRO-NNN),
每条提案必须附带真实的 reference_code 锚点 (文件路径+行号+逐字代码片段).

## 输入数据
- repo_path: 被分析的仓库根路径
- module_count: 被读取的模块总数
- modules: 模块列表, 每项含 module_path (相对路径), content (完整源码), line_count, byte_size

## 输出要求
调用 submit_extractions 提交最终结果, 包含:
1. **proposals[]** (minItems=3): 每条提案含
   - id: "PRO-001", "PRO-002", ... 递增不重复
   - title: ≥8 字符
   - problem: ≥30 字符, 描述具体问题
   - proposed_change: ≥30 字符, 说明如何改进
   - reference_code: {file: 相对路径, line_start: 1-indexed 行号, snippet: 逐字代码片段}
   - risk: ≥15 字符, 实施风险评估
2. **source_analysis_context**: {identified_patterns[], module_summaries[]}
3. **analysis_metadata**: {repo_path, files_analyzed, total_lines, top_n}

## 分析维度
1. **设计模式**: Singleton, Factory, Strategy, Observer, Adapter 等
2. **反模式**: 宽泛异常捕获, 神类/神函数, 紧耦合, 魔法数字, 调试残留
3. **架构特征**: 分层结构, 事件驱动, 插件化, 依赖注入
4. **代码质量**: 类型注解完整性, 文档覆盖率, 命名一致性, 错误处理策略
5. **性能/安全**: 低效循环, 未验证输入(SSRF/路径漏洞), 硬编码凭据, SQL/命令注入风险, 线程安全, 资源泄露

## 视角配额铁律 (绝对要求 · 2026-04-26 加)

提案必须**覆盖至少 3 个不同维度**, 不准全集中在"反模式 / 架构层" (实测发现 LLM 默认偏架构层, 漏掉具体安全/资源问题):

- **必含至少 1 条 维度 5 (性能/安全)** — SSRF / 注入 / 超时 / 资源泄露 / 路径漏洞 / 线程安全等
- **必含至少 1 条 维度 4 (代码质量)** — 类型注解 / 文档覆盖 / 命名 / 错误处理策略
- **其余可选** — 设计模式 / 反模式 / 架构特征
- 不许 5 条全 "上帝类 / 异常吞噬 / print 用法" 这种风格

每条 `problem` 字段**必须以 [维度名] 开头**, 例:
- `"[性能/安全] commands.py:148 接受任意 url 调 scrape 缺 SSRF 校验, 可被滥用访问内网"`
- `"[代码质量] base_coder.py:34 大量 hint 注释为空, IDE 类型提示缺失"`
- `"[反模式] commands.py 用 raise SwitchCoder 做控制流, 应改返回值"`

漏掉维度配额 → 信号不全, 你的输出价值受疑.

## F-15 诚实原则 (铁律)
- reference_code.file 必须与某个 module_path 一致 (绝对不要虚构路径!)
- reference_code.snippet 必须逐字出现在对应 content 中
- reference_code.line_start 必须对齐 content.splitlines() 的真实行号 (1-indexed)
- 如果不确定行号, 使用 grep 工具确认后再提交

## 工具
- **read_file**: 读取文件全文或指定范围 (file_path 必须是绝对路径 = repo_path + "/" + module_path)
- **grep**: 搜索代码模式 (如 "except:", "print(", "TODO", "class ", "def ")
- **glob**: 探索目录结构
- **list_dir**: 列出目录内容
- **submit_extractions**: 提交最终分析结果 (结构化 schema, 各字段直接填)

## 操作策略
1. 先看 modules 摘要了解代码库规模
2. 对每个模块, 优先阅读 content (已在输入中提供)
3. 用 grep 辅助定位特定模式 (如异常处理、调试语句)
4. 对大模块可用 read_file 分段阅读
5. 确保每个提案至少 ≥3 条

## 重要约束
- 所有参考代码锚点必须真实存在于输入提供的源码中
- 不要跨模块编造引用
- 提案应当有价值, 不是琐碎的风格建议
- 风险评估应当诚实, 不要低估或高估
- 最终必须调用 submit_extractions 提交结果"""


class _PatternExtractorPromptBuilder(PromptBuilderRouter):
    """Custom prompt builder: injects module_sources data into agent's initial task."""

    def build_initial_messages(self, biz_input: dict) -> list[dict]:
        module_count = biz_input.get("module_count", 0)
        repo_path = biz_input.get("repo_path", "")
        modules = biz_input.get("modules", [])
        top_n = biz_input.get("top_n", len(modules) * 2)

        if not isinstance(top_n, int) or top_n < 3:
            top_n = max(3, len(modules) * 2)

        # Build concise metadata summary of all modules
        module_meta = []
        for m in modules:
            module_meta.append({
                "module_path": m.get("module_path", ""),
                "line_count": m.get("line_count", 0),
                "byte_size": m.get("byte_size", 0),
            })

        # For small modules (<~1000 chars), embed content directly
        # For large modules, provide metadata + let agent use read_file
        total_lines = sum(m.get("line_count", 0) for m in modules)

        task = f"""## 任务: 深度分析 {module_count} 个 Python 模块, 提取代码模式并生成改进提案

### 扫描配置
- repo_path: `{repo_path}`
- top_n: {top_n} (提案数上限)
- module_count: {module_count}
- total_lines: {total_lines}

### 模块摘要 (共 {module_count} 个模块)

```json
{json.dumps(module_meta, ensure_ascii=False, indent=2)}
```

### 源码内容"""

        # Embed content for modules ≤ 80KB to give agent immediate context
        embedded_count = 0
        for m in modules:
            content = m.get("content", "")
            mod_path = m.get("module_path", "")
            if len(content) <= 80_000:
                task += f"""

#### 模块: {mod_path} ({m.get('line_count', '?')} 行)

```python
{content}
```"""
                embedded_count += 1
            else:
                task += f"""

#### 模块: {mod_path} ({m.get('line_count', '?')} 行, {m.get('byte_size', '?')} 字节)

> ⚠️ 此模块较大 ({m.get('byte_size', 0):,} 字节), 请使用 `read_file` 工具按需读取.
> 绝对路径: `{repo_path}/{mod_path}`"""

        task += f"""

### 操作流程
1. 阅读上述已嵌入的 {embedded_count} 个模块源码
2. 对未嵌入的大型模块, 使用 `read_file` 工具读取 (绝对路径 = `{repo_path}/` + module_path)
3. 使用 `grep` 搜索特定模式辅助分析 (如 "except", "print(", "TODO", "FIXME")
4. 识别代码模式与反模式, 生成 ≥3 条改进提案
5. 每个提案的 reference_code 必须锚定到真实源码
6. 调用 `submit_extractions` 提交结果

### reference_code 真实性要求
- **file**: 必须与上面模块摘要中的某个 module_path 完全一致
- **line_start**: 1-indexed 行号, 必须 ≤ 对应模块的 line_count
- **snippet**: 必须逐字出现在对应模块的 content 中
- 如果不确定, 先用 `grep` 或 `read_file` 确认

### 提示
- 如果模块数量多, 优先分析 complexity 高 (行数多/结构复杂) 的模块
- 提案应当有实质价值, 不是琐碎的风格建议
- 每个提案的 problem 和 proposed_change 必须 ≥30 字符

请开始分析并提交结果。"""

        return [{"role": "user", "content": task}]


class SubmitExtractionsRouter(SingleToolRouter):
    """提交模式提取结果 · 结构化 schema · 替代 FinishRouter + json.loads."""

    TOOL_NAME: ClassVar[str] = "submit_extractions"
    DESCRIPTION: ClassVar[str] = (
        "Submit the final pattern extraction results. Calling this terminates the agent loop. "
        "All fields are validated by API schema; do not embed JSON in plain text."
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "proposals": {
                "type": "array",
                "minItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "pattern": "^PRO-\\d{3}$",
                            "description": "Proposal unique ID, e.g. PRO-001, PRO-002, ...",
                        },
                        "title": {
                            "type": "string",
                            "minLength": 8,
                            "description": "Brief title for the improvement proposal",
                        },
                        "problem": {
                            "type": "string",
                            "minLength": 30,
                            "description": "Problem statement (≥30 chars)",
                        },
                        "proposed_change": {
                            "type": "string",
                            "minLength": 30,
                            "description": "Proposed improvement direction (≥30 chars)",
                        },
                        "reference_code": {
                            "type": "object",
                            "properties": {
                                "file": {
                                    "type": "string",
                                    "description": "Relative path of the referenced source file (must match a real module_path)",
                                },
                                "line_start": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "description": "1-indexed starting line number (must be within file bounds)",
                                },
                                "line_end": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "description": "1-indexed ending line number (optional)",
                                },
                                "snippet": {
                                    "type": "string",
                                    "description": "Verbatim code snippet (must appear literally in the referenced file)",
                                },
                            },
                            "required": ["file", "line_start", "snippet"],
                        },
                        "risk": {
                            "type": "string",
                            "minLength": 15,
                            "description": "Implementation risk assessment (≥15 chars)",
                        },
                    },
                    "required": ["id", "title", "problem", "proposed_change", "reference_code", "risk"],
                },
                "description": "List of improvement proposals with real code anchors",
            },
            "source_analysis_context": {
                "type": "object",
                "properties": {
                    "identified_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of identified code patterns (design patterns, anti-patterns, architecture traits)",
                    },
                    "module_summaries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file_path": {"type": "string"},
                                "role_summary": {"type": "string"},
                                "complexity_note": {"type": "string"},
                            },
                            "required": ["file_path", "role_summary"],
                        },
                        "description": "Per-module role summaries",
                    },
                },
                "required": ["identified_patterns"],
            },
            "analysis_metadata": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "files_analyzed": {"type": "integer", "minimum": 1},
                    "total_lines": {"type": "integer", "minimum": 0},
                    "top_n": {"type": "integer", "minimum": 1},
                },
                "required": ["repo_path", "files_analyzed"],
            },
        },
        "required": ["proposals", "source_analysis_context", "analysis_metadata"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = True
    IS_READONLY: ClassVar[bool] = True

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        proposals = args.get("proposals", [])
        patterns = args.get("source_analysis_context", {}).get("identified_patterns", [])
        return (
            f"submitted: {len(proposals)} proposals, "
            f"{len(patterns)} identified patterns"
        )


class _PatternExtractorExtractResult(ExtractResultRouter):
    """Extract structured submission from messages (no JSON parsing)."""

    def extract(
        self,
        *,
        final_text: str,
        messages: list,
        turn_count: int,
        stop_reason: str,
    ) -> Verdict:
        # Find submit_extractions tool_use · read structured input directly
        result_json: dict | None = None
        for msg in reversed(messages):
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "tool_use"
                        and block.get("name") == "submit_extractions"
                    ):
                        inp = block.get("input", {})
                        if isinstance(inp, dict):
                            result_json = dict(inp)
                            break
            if result_json:
                break

        if not isinstance(result_json, dict):
            return Verdict(
                kind=VerdictKind.FAIL,
                output={"final_text": final_text[:500], "turn_count": turn_count},
                diagnosis=(
                    f"PatternExtractorWorker 未调用 submit_extractions "
                    f"(turns={turn_count}, stop={stop_reason})"
                ),
            )

        # Validate required fields
        proposals = result_json.get("proposals")
        if not proposals or not isinstance(proposals, list) or len(proposals) < 3:
            return Verdict(
                kind=VerdictKind.FAIL,
                output=result_json,
                diagnosis=f"proposals 必须 ≥3 条 (got {len(proposals) if isinstance(proposals, list) else 0})",
            )

        # Build flat output (Verdict.output 顶层平铺)
        output_payload: dict[str, Any] = {
            "proposals": proposals,
            "source_analysis_context": result_json.get("source_analysis_context", {"identified_patterns": []}),
            "analysis_metadata": result_json.get("analysis_metadata", {}),
        }

        # Determine verdict kind
        if stop_reason == "max_turns":
            return Verdict(
                kind=VerdictKind.PARTIAL,
                output=output_payload,
                diagnosis=f"预算耗尽: {turn_count} turns, 已生成 {len(proposals)} 条提案",
            )

        return Verdict(
            kind=VerdictKind.PASS,
            output=output_payload,
            diagnosis=f"成功提取 {len(proposals)} 条改进提案",
            confidence=0.9,
        )


class PatternExtractorWorker(AgentNodeLoop):
    """repo_absorption Team Worker #4 · AGENT 源码模式深度分析.

    通过 AgentNodeLoop 多轮探索 (ReadFile / Grep / Glob / ListDir),
    LLM 深度分析模块源码, 提取代码模式与改进提案, 生成带真实 reference_code
    锚点的结构化 extraction_results.

    严格遵守 F-15 诚实原则: 所有参考代码锚点逐字源自实际源码.
    """

    FORMAT_IN: ClassVar[str] = "repo_absorption.module_sources"
    FORMAT_OUT: ClassVar[str] = "repo_absorption.extraction_results"
    FORMAT_IN_MODE: ClassVar[str] = "and"
    DESCRIPTION: ClassVar[str] = (
        "接收 repo_absorption.module_sources, 通过 AgentNodeLoop 进行多轮 LLM 深度分析, "
        "提取代码模式 (设计模式/反模式/架构特征), 生成带 PRO-NNN 标识和真实 reference_code "
        "锚点的结构化改进提案, 产出 repo_absorption.extraction_results."
    )
    ALLOW_NO_BUS: ClassVar[bool] = True
    TOOL_ROUTERS: ClassVar[list] = [
        ReadFileRouter,
        GrepRouter,
        GlobRouter,
        ListDirRouter,
        SubmitExtractionsRouter,
    ]
    NODE_PROMPT: ClassVar[str] = _SYSTEM_PROMPT

    def __init__(self) -> None:
        from omnicompany.bus.memory import MemoryBus

        super().__init__(bus=MemoryBus(), role="runtime_main")

    def build_prompt_builder(self, *, bus: Any) -> _PatternExtractorPromptBuilder:
        return _PatternExtractorPromptBuilder(template=self.NODE_PROMPT, bus=bus)

    def build_extract_result(self, *, bus: Any) -> _PatternExtractorExtractResult:
        return _PatternExtractorExtractResult(bus=bus)
